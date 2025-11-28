#!/usr/bin/env python3
"""
EV3 MicroPython Interface
-------------------------
Low-latency communication with EV3 running Pybricks MicroPython.

Supports multiple transports:
- USB Serial: ~1-5ms latency (best)
- WiFi TCP Socket: ~5-15ms latency (no SSH overhead)
- Bluetooth RFCOMM: ~10-20ms latency

Architecture:
    Host (Python) ──► Transport ──► EV3 (Pybricks daemon)
                      │
                      ├── USB Serial (/dev/tty.usbmodem*)
                      ├── TCP Socket (port 9000)
                      └── Bluetooth RFCOMM (channel 1)

Usage:
    # Auto-detect best connection
    async with EV3MicroPython() as ev3:
        await ev3.send("beep")
    
    # Force specific transport
    ev3 = EV3MicroPython(transport="usb")  # or "wifi", "bluetooth"
"""

import asyncio
import glob
import platform
import socket
import struct
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, List, Tuple

# Optional imports
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

try:
    # For Bluetooth RFCOMM on Linux/macOS
    from socket import AF_BLUETOOTH, BTPROTO_RFCOMM, SOCK_STREAM
    BLUETOOTH_AVAILABLE = True
except ImportError:
    BLUETOOTH_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class EV3Config:
    """EV3 connection configuration."""
    # USB Serial
    usb_port: Optional[str] = None  # Auto-detect if None
    usb_baudrate: int = 115200
    
    # WiFi TCP
    wifi_host: str = "ev3dev.local"  # or IP address
    wifi_port: int = 9000
    
    # Bluetooth
    bt_address: Optional[str] = None  # EV3 Bluetooth MAC address
    bt_channel: int = 1  # RFCOMM channel
    
    # SSH (for auto-starting daemon)
    ssh_user: str = "robot"
    ssh_password: str = "maker"
    daemon_path: str = "/home/robot/pybricks_daemon.py"
    auto_start_daemon: bool = True  # Auto-start daemon via SSH if not running
    
    # Protocol
    timeout: float = 2.0
    encoding: str = "utf-8"


# =============================================================================
# Transport Abstraction
# =============================================================================

class Transport(ABC):
    """Abstract base for communication transports."""
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection. Returns True if successful."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass
    
    @abstractmethod
    async def send(self, data: bytes) -> None:
        """Send raw bytes."""
        pass
    
    @abstractmethod
    async def receive(self, timeout: float = 2.0) -> bytes:
        """Receive data with timeout."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Transport name for logging."""
        pass


class USBSerialTransport(Transport):
    """USB Serial connection to EV3."""
    
    def __init__(self, port: Optional[str] = None, baudrate: int = 115200):
        self._port = port
        self._baudrate = baudrate
        self._serial: Optional[serial.Serial] = None
    
    @staticmethod
    def find_ev3_port() -> Optional[str]:
        """Auto-detect EV3 USB serial port."""
        if not SERIAL_AVAILABLE:
            return None
        
        system = platform.system()
        
        # Look for LEGO/EV3 USB devices
        for port in serial.tools.list_ports.comports():
            desc = (port.description or "").lower()
            mfr = (port.manufacturer or "").lower()
            
            # Match LEGO or EV3 identifiers
            if any(x in desc for x in ["lego", "ev3", "mindstorms"]):
                return port.device
            if any(x in mfr for x in ["lego", "ev3"]):
                return port.device
        
        # Fallback: common patterns
        if system == "Darwin":  # macOS
            matches = glob.glob("/dev/tty.usbmodem*") + glob.glob("/dev/cu.usbmodem*")
            if matches:
                return matches[0]
        elif system == "Linux":
            matches = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
            if matches:
                return matches[0]
        elif system == "Windows":
            # Windows COM ports - try common ones
            for i in range(10):
                try:
                    test_port = f"COM{i}"
                    s = serial.Serial(test_port, timeout=0.1)
                    s.close()
                    return test_port
                except:
                    continue
        
        return None
    
    async def connect(self) -> bool:
        if not SERIAL_AVAILABLE:
            print("[USB] pyserial not installed: pip install pyserial")
            return False
        
        port = self._port or self.find_ev3_port()
        if not port:
            print("[USB] No EV3 USB device found")
            return False
        
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=self._baudrate,
                timeout=0.1,
                write_timeout=1.0
            )
            # Clear any buffered data
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            print(f"\033[32m✓ USB Serial ({port}) @ {self._baudrate} baud\033[0m")
            return True
        except Exception as e:
            print(f"[USB] Connection failed: {e}")
            return False
    
    async def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None
    
    async def send(self, data: bytes) -> None:
        if self._serial and self._serial.is_open:
            self._serial.write(data)
            self._serial.flush()
    
    async def receive(self, timeout: float = 2.0) -> bytes:
        if not self._serial or not self._serial.is_open:
            return b""
        
        self._serial.timeout = timeout
        
        # Read until newline
        try:
            line = self._serial.readline()
            return line
        except serial.SerialTimeoutException:
            return b""
    
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open
    
    @property
    def name(self) -> str:
        port = self._serial.port if self._serial else "?"
        return f"USB:{port}"


class WiFiTCPTransport(Transport):
    """WiFi TCP Socket connection to EV3."""
    
    def __init__(self, host: str = "ev3dev.local", port: int = 9000):
        self._host = host
        self._port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
    
    async def connect(self) -> bool:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=5.0
            )
            print(f"\033[32m✓ WiFi TCP ({self._host}:{self._port})\033[0m")
            return True
        except asyncio.TimeoutError:
            print(f"[WiFi] Connection timeout: {self._host}:{self._port}")
            return False
        except Exception as e:
            print(f"[WiFi] Connection failed: {e}")
            return False
    
    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except:
                pass
        self._reader = None
        self._writer = None
    
    async def send(self, data: bytes) -> None:
        if self._writer:
            self._writer.write(data)
            await self._writer.drain()
    
    async def receive(self, timeout: float = 2.0) -> bytes:
        if not self._reader:
            return b""
        
        try:
            line = await asyncio.wait_for(
                self._reader.readline(),
                timeout=timeout
            )
            return line
        except asyncio.TimeoutError:
            return b""
    
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()
    
    @property
    def name(self) -> str:
        return f"WiFi:{self._host}:{self._port}"


class BluetoothRFCOMMTransport(Transport):
    """Bluetooth RFCOMM connection to EV3."""
    
    def __init__(self, address: str, channel: int = 1):
        self._address = address
        self._channel = channel
        self._socket: Optional[socket.socket] = None
    
    async def connect(self) -> bool:
        if not BLUETOOTH_AVAILABLE:
            print("[BT] Bluetooth sockets not available on this platform")
            return False
        
        try:
            self._socket = socket.socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM)
            self._socket.settimeout(5.0)
            
            # Run blocking connect in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._socket.connect((self._address, self._channel))
            )
            
            self._socket.setblocking(False)
            print(f"\033[32m✓ Bluetooth RFCOMM ({self._address})\033[0m")
            return True
        except Exception as e:
            print(f"[BT] Connection failed: {e}")
            if self._socket:
                self._socket.close()
            self._socket = None
            return False
    
    async def disconnect(self) -> None:
        if self._socket:
            self._socket.close()
        self._socket = None
    
    async def send(self, data: bytes) -> None:
        if self._socket:
            loop = asyncio.get_event_loop()
            await loop.sock_sendall(self._socket, data)
    
    async def receive(self, timeout: float = 2.0) -> bytes:
        if not self._socket:
            return b""
        
        try:
            loop = asyncio.get_event_loop()
            data = await asyncio.wait_for(
                loop.sock_recv(self._socket, 1024),
                timeout=timeout
            )
            return data
        except asyncio.TimeoutError:
            return b""
    
    def is_connected(self) -> bool:
        return self._socket is not None
    
    @property
    def name(self) -> str:
        return f"BT:{self._address}"


# =============================================================================
# Main Interface
# =============================================================================

class EV3MicroPython:
    """
    Unified interface for EV3 running Pybricks MicroPython.
    
    Supports USB Serial, WiFi TCP, and Bluetooth RFCOMM with auto-detection.
    
    Latency comparison:
    - USB Serial:   ~1-5ms   (best, requires cable)
    - WiFi TCP:     ~5-15ms  (good, no SSH overhead)
    - Bluetooth:    ~10-20ms (wireless, needs pairing)
    - OLD SSH:      ~30-50ms (previous method)
    
    Usage:
        async with EV3MicroPython() as ev3:
            response = await ev3.send("beep")
            print(response)  # "OK"
    """
    
    def __init__(
        self,
        config: Optional[EV3Config] = None,
        transport: Optional[str] = None,  # "usb", "wifi", "bluetooth", or None for auto
    ):
        self.config = config or EV3Config()
        self._transport_type = transport
        self._transport: Optional[Transport] = None
        self._connected = False
        self._callbacks: List[Callable[[str], None]] = []
    
    async def connect(self) -> bool:
        """
        Connect to EV3 using best available transport.
        
        Priority: USB > WiFi > Bluetooth (unless specified)
        If connection fails and auto_start_daemon is True, attempts to start daemon via SSH.
        """
        # First attempt
        if await self._try_connect():
            return True
        
        # If failed and auto-start enabled, try starting daemon via SSH
        if self.config.auto_start_daemon:
            print("⏳ Daemon not running, attempting to start via SSH...")
            if await self._start_daemon_via_ssh():
                # Retry connection with exponential backoff
                for attempt in range(5):
                    wait_time = 2 + attempt * 2  # 2, 4, 6, 8, 10 seconds
                    print(f"⏳ Waiting {wait_time}s for daemon... (attempt {attempt + 1}/5)")
                    await asyncio.sleep(wait_time)
                    if await self._try_connect():
                        return True
        
        print("❌ Could not connect via USB, WiFi, or Bluetooth")
        return False
    
    async def _try_connect(self) -> bool:
        """Attempt to connect to EV3."""
        if self._transport_type:
            # Use specified transport
            transport = self._create_transport(self._transport_type)
            if transport and await transport.connect():
                self._transport = transport
                self._connected = True
                # Wait for READY
                ready = await self._wait_ready()
                if ready:
                    return True
                await transport.disconnect()
            return False
        
        # Auto-detect: try USB first, then WiFi, then Bluetooth
        for transport_type in ["usb", "wifi", "bluetooth"]:
            transport = self._create_transport(transport_type)
            if transport:
                try:
                    if await transport.connect():
                        self._transport = transport
                        self._connected = True
                        
                        # Wait for READY signal from daemon
                        ready = await self._wait_ready()
                        if ready:
                            return True
                        else:
                            print(f"[{transport.name}] No READY signal - daemon not running?")
                            await transport.disconnect()
                            continue
                except Exception as e:
                    print(f"[{transport_type}] Connection failed: {e}")
                    continue
        
        return False
    
    async def _start_daemon_via_ssh(self) -> bool:
        """Start the pybricks daemon on EV3 via SSH."""
        try:
            import paramiko
        except ImportError:
            print("⚠️ paramiko not installed - cannot auto-start daemon")
            print("  Install with: pip install paramiko")
            print("  Or manually start daemon on EV3: brickrun pybricks_daemon.py")
            return False
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.config.wifi_host,
                username=self.config.ssh_user,
                password=self.config.ssh_password,
                timeout=5
            )
            
            # Kill any existing daemon
            stdin, stdout, stderr = ssh.exec_command('pkill -f pybricks_daemon 2>/dev/null || true')
            stdout.read()
            await asyncio.sleep(1)
            
            # Start daemon in background
            daemon_cmd = f'nohup brickrun {self.config.daemon_path} > /tmp/daemon.log 2>&1 &'
            channel = ssh.get_transport().open_session()
            channel.exec_command(f'bash -c "{daemon_cmd}"')
            
            ssh.close()
            print("✓ Daemon started via SSH")
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to start daemon via SSH: {e}")
            print(f"  Manually start on EV3: brickrun {self.config.daemon_path}")
            return False
    
    def _create_transport(self, transport_type: str) -> Optional[Transport]:
        """Create transport instance by type."""
        if transport_type == "usb":
            if not SERIAL_AVAILABLE:
                return None
            return USBSerialTransport(
                port=self.config.usb_port,
                baudrate=self.config.usb_baudrate
            )
        elif transport_type == "wifi":
            return WiFiTCPTransport(
                host=self.config.wifi_host,
                port=self.config.wifi_port
            )
        elif transport_type == "bluetooth":
            if not BLUETOOTH_AVAILABLE or not self.config.bt_address:
                return None
            return BluetoothRFCOMMTransport(
                address=self.config.bt_address,
                channel=self.config.bt_channel
            )
        return None
    
    async def _wait_ready(self, timeout: float = 3.0) -> bool:
        """Wait for READY signal from EV3 daemon."""
        try:
            data = await self._transport.receive(timeout=timeout)
            response = data.decode(self.config.encoding).strip()
            return "READY" in response
        except:
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from EV3."""
        if self._transport:
            try:
                await self.send("quit", wait_response=False)
            except:
                pass
            await self._transport.disconnect()
        self._transport = None
        self._connected = False
    
    async def send(self, command: str, wait_response: bool = True) -> Tuple[str, float]:
        """
        Send command to EV3 daemon.
        
        Args:
            command: Command string (e.g., "beep", "motor A 50", "status")
            wait_response: If True, wait for response. If False, fire-and-forget.
        
        Returns:
            Tuple of (response_string, latency_ms)
        """
        if not self._transport or not self._connected:
            raise ConnectionError("Not connected to EV3")
        
        t0 = time.time()
        
        # Send command with newline
        data = (command + "\n").encode(self.config.encoding)
        await self._transport.send(data)
        
        if not wait_response:
            return ("", (time.time() - t0) * 1000)
        
        # Wait for response
        response_data = await self._transport.receive(timeout=self.config.timeout)
        latency = (time.time() - t0) * 1000
        
        response = response_data.decode(self.config.encoding).strip()
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(response)
            except:
                pass
        
        return (response, latency)
    
    async def send_fire(self, command: str) -> float:
        """Fire-and-forget command. Returns latency in ms."""
        _, latency = await self.send(command, wait_response=False)
        return latency
    
    # =========================================================================
    # Convenience methods
    # =========================================================================
    
    async def beep(self, frequency: int = 880, duration: int = 200) -> Tuple[str, float]:
        """Play a beep."""
        return await self.send(f"beep {frequency} {duration}")
    
    async def speak(self, text: str) -> Tuple[str, float]:
        """Text-to-speech."""
        return await self.send(f"speak {text}")
    
    async def motor(self, port: str, speed: int, duration: Optional[int] = None) -> Tuple[str, float]:
        """Control motor."""
        cmd = f"motor {port} {speed}"
        if duration:
            cmd += f" {duration}"
        return await self.send(cmd)
    
    async def stop_motor(self, port: str) -> Tuple[str, float]:
        """Stop motor."""
        return await self.send(f"stop {port}")
    
    async def sensor(self, port: str) -> Tuple[str, float]:
        """Read sensor value."""
        return await self.send(f"sensor {port}")
    
    async def status(self) -> Tuple[str, float]:
        """Get EV3 status."""
        return await self.send("status")
    
    async def display(self, text: str) -> Tuple[str, float]:
        """Show text on display."""
        return await self.send(f"display {text}")
    
    async def eyes(self, expression: str) -> Tuple[str, float]:
        """Show eye expression (happy, sad, angry, neutral, etc.)."""
        return await self.send(f"eyes {expression}")
    
    def on_response(self, callback: Callable[[str], None]) -> None:
        """Register callback for responses."""
        self._callbacks.append(callback)
    
    # =========================================================================
    # Action Adapter Support
    # =========================================================================
    
    def load_actions(self, source) -> None:
        """
        Load action definitions for high-level command translation.
        
        Args:
            source: Either:
                - Path to YAML file (str ending in .yaml/.yml)
                - ActionAdapter instance
                - Dict mapping action names to step lists
        
        Example:
            ev3.load_actions("projects/puppy/configs/actions.yaml")
            await ev3.execute("sitdown")  # Translates to motor commands
        """
        from .action_adapter import ActionAdapter
        
        if isinstance(source, ActionAdapter):
            self._action_adapter = source
        elif isinstance(source, str) and source.endswith(('.yaml', '.yml')):
            self._action_adapter = ActionAdapter.from_yaml(source)
        elif isinstance(source, dict):
            self._action_adapter = ActionAdapter(source)
        else:
            raise ValueError("source must be YAML path, ActionAdapter, or dict")
    
    def load_actions_for_project(self, project_name: str) -> bool:
        """
        Auto-load actions for a known project.
        
        Args:
            project_name: Project name (e.g., "puppy")
            
        Returns:
            True if actions loaded successfully
        """
        import os
        
        # Try to find actions.yaml in project configs
        base_paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", "projects", project_name, "configs"),
            os.path.join("projects", project_name, "configs"),
        ]
        
        for base in base_paths:
            yaml_path = os.path.join(base, "actions.yaml")
            if os.path.exists(yaml_path):
                self.load_actions(yaml_path)
                return True
        
        # Fall back to built-in action sets
        from .action_adapter import PUPPY_ACTIONS
        
        builtin_actions = {
            "puppy": PUPPY_ACTIONS,
        }
        
        if project_name in builtin_actions:
            from .action_adapter import ActionAdapter
            self._action_adapter = ActionAdapter(builtin_actions[project_name])
            return True
        
        return False
    
    async def execute(self, action: str, verbose: bool = False) -> Tuple[str, float]:
        """
        Execute an action (with automatic translation if adapter loaded).
        
        If action is in the loaded adapter, translates to command sequence.
        Otherwise, sends directly to daemon.
        
        Args:
            action: Action name (e.g., "sitdown") or direct command
            verbose: Print each translated command
            
        Returns:
            Tuple of (response, total_latency_ms)
        """
        # Check if we have an adapter and it knows this action
        if hasattr(self, '_action_adapter') and self._action_adapter:
            commands = self._action_adapter.translate(action)
            if commands is not None:
                return await self._execute_sequence(commands, verbose)
        
        # No translation needed, send directly
        return await self.send(action)
    
    async def _execute_sequence(
        self, 
        commands: List[Tuple[str, int]], 
        verbose: bool = False
    ) -> Tuple[str, float]:
        """Execute a sequence of commands with delays."""
        total_latency = 0.0
        responses = []
        
        for cmd, delay_ms in commands:
            response, latency = await self.send(cmd)
            responses.append(response)
            total_latency += latency
            
            if verbose:
                print(f"  {cmd} -> {response} ({latency:.1f}ms)")
            
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
        
        # Return combined result
        if all("OK" in r or r.startswith("OK") for r in responses):
            return "OK", total_latency
        else:
            return "; ".join(responses), total_latency
    
    def list_actions(self) -> List[str]:
        """List available translated actions (if adapter loaded)."""
        if hasattr(self, '_action_adapter') and self._action_adapter:
            return self._action_adapter.list_actions()
        return []
    
    def has_action(self, action: str) -> bool:
        """Check if action is available for translation."""
        if hasattr(self, '_action_adapter') and self._action_adapter:
            return self._action_adapter.has_action(action)
        return False
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._transport is not None
    
    @property
    def transport_name(self) -> str:
        return self._transport.name if self._transport else "None"
    
    # =========================================================================
    # Context manager
    # =========================================================================
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


# =============================================================================
# Interactive Flow Mode
# =============================================================================

async def flow_mode(ev3: EV3MicroPython):
    """Interactive command mode."""
    print("=" * 60)
    print("EV3 MICROPYTHON FLOW MODE")
    print(f"Transport: {ev3.transport_name}")
    print("=" * 60)
    print()
    print("Commands:")
    print("  beep [freq] [dur]  - Play beep (default: 880Hz, 200ms)")
    print("  speak <text>       - Text-to-speech")
    print("  motor <port> <spd> - Run motor (A-D, -100 to 100)")
    print("  stop <port>        - Stop motor")
    print("  sensor <port>      - Read sensor (1-4)")
    print("  eyes <expr>        - Show expression (happy, sad, angry)")
    print("  status             - Get EV3 status")
    print("  benchmark          - Run latency benchmark")
    print("  quit               - Exit")
    print("-" * 60)
    
    while ev3.is_connected:
        try:
            cmd = input("\n> ").strip()
            
            if not cmd:
                continue
            
            if cmd.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break
            
            if cmd.lower() == "benchmark":
                await _benchmark(ev3)
                continue
            
            if cmd.lower() == "help":
                print("Commands: beep, speak, motor, stop, sensor, eyes, status, quit")
                continue
            
            # Execute command
            response, latency = await ev3.send(cmd)
            print(f"[EV3] {response} ({latency:.1f}ms)")
            
        except KeyboardInterrupt:
            print("\n\nInterrupted.")
            break
        except EOFError:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"[Error] {e}")


async def _benchmark(ev3: EV3MicroPython, count: int = 10):
    """Run latency benchmark."""
    print(f"\nBenchmark: {count} round-trips...")
    
    latencies = []
    for i in range(count):
        _, latency = await ev3.send("status")
        latencies.append(latency)
        print(f"  {i+1}: {latency:.1f}ms")
        await asyncio.sleep(0.1)
    
    avg = sum(latencies) / len(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)
    
    print()
    print(f"Results ({ev3.transport_name}):")
    print(f"  Average: {avg:.1f}ms")
    print(f"  Min:     {min_lat:.1f}ms")
    print(f"  Max:     {max_lat:.1f}ms")


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="EV3 MicroPython Interface")
    parser.add_argument("--transport", "-t", choices=["usb", "wifi", "bluetooth"],
                       help="Force specific transport")
    parser.add_argument("--host", default="ev3dev.local",
                       help="WiFi host (default: ev3dev.local)")
    parser.add_argument("--port", type=int, default=9000,
                       help="WiFi port (default: 9000)")
    parser.add_argument("--bt-address", help="Bluetooth MAC address")
    parser.add_argument("--usb-port", help="USB serial port (auto-detect if not specified)")
    parser.add_argument("--benchmark", "-b", action="store_true",
                       help="Run latency benchmark")
    parser.add_argument("command", nargs="*", help="Command to send (or 'flow' for interactive)")
    
    args = parser.parse_args()
    
    config = EV3Config(
        wifi_host=args.host,
        wifi_port=args.port,
        bt_address=args.bt_address,
        usb_port=args.usb_port,
    )
    
    ev3 = EV3MicroPython(config=config, transport=args.transport)
    
    if not await ev3.connect():
        print("Failed to connect to EV3")
        sys.exit(1)
    
    try:
        if args.benchmark:
            await _benchmark(ev3)
        elif args.command:
            if args.command[0] == "flow":
                await flow_mode(ev3)
            else:
                cmd = " ".join(args.command)
                response, latency = await ev3.send(cmd)
                print(f"{response} ({latency:.1f}ms)")
        else:
            await flow_mode(ev3)
    finally:
        await ev3.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

