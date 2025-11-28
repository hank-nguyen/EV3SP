"""
Abstract Robot Interface
------------------------
Platform-agnostic interface for robot communication.

For EV3 with Pybricks MicroPython (recommended, lowest latency):
    from platforms.ev3 import EV3MicroPython
    
    async with EV3MicroPython() as ev3:
        await ev3.beep(880, 200)  # ~2-5ms via USB!

For legacy ev3dev SSH interface:
    from platforms.ev3 import EV3Interface, EV3DaemonSession
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any
from .types import RobotState, ConnectionConfig


class RobotInterface(ABC):
    """Abstract interface for robot communication."""
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to robot."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection."""
        pass
    
    @abstractmethod
    def upload_file(self, local_path: str, remote_name: str) -> str:
        """Upload file to robot. Returns remote path."""
        pass
    
    @abstractmethod
    def execute_command(self, cmd: str, timeout: float = 30) -> tuple:
        """Execute command on robot. Returns (stdout, stderr, exit_code)."""
        pass
    
    @abstractmethod
    def get_state(self) -> RobotState:
        """Get current robot state."""
        pass
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class DaemonSession(ABC):
    """Abstract daemon session for low-latency control."""
    
    def __init__(self, interface: RobotInterface, daemon_script: str):
        self.interface = interface
        self.daemon_script = daemon_script
        self._running = False
    
    @abstractmethod
    def start(self, script_content: str = None) -> bool:
        """Start daemon. Returns True if successful."""
        pass
    
    @abstractmethod
    def send(self, cmd: str) -> str:
        """Send command and get response."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop daemon."""
        pass
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def flow(self, prompt: str = "> ", commands_help: str = None) -> None:
        """Interactive flow mode."""
        import time
        
        print("=" * 50)
        print("Robot Flow Mode (Low Latency)")
        print("=" * 50)
        
        if commands_help:
            print(commands_help)
        print("Type 'quit' to disconnect, 'help' for commands")
        print("-" * 50)
        
        while self._running:
            try:
                cmd = input("\n" + prompt).strip()
                
                if not cmd:
                    continue
                
                if cmd.lower() in ("quit", "exit", "q"):
                    try:
                        self.send("quit")
                    except:
                        pass
                    print("Goodbye!")
                    break
                
                if cmd.lower() == "help":
                    if commands_help:
                        print(commands_help)
                    else:
                        print("Available: status, stop, quit")
                    continue
                
                t0 = time.time()
                response = self.send(cmd)
                latency = (time.time() - t0) * 1000
                
                print("[Robot] %s (%.0fms)" % (response, latency))
                
            except KeyboardInterrupt:
                print("\n\nInterrupted.")
                try:
                    self.send("quit")
                except:
                    pass
                break
            except EOFError:
                print("\nGoodbye!")
                break
            except OSError as e:
                err = str(e)
                if "closed" in err.lower() or "quit" in err.lower():
                    print("\n[Disconnected] %s" % err)
                else:
                    print("[Error] %s" % err)
                break
            except Exception as e:
                print("[Error] %s" % e)
        
        self._running = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def get_ev3_interface(config: ConnectionConfig):
    """
    Get EV3 interface based on transport config.
    
    Default (MicroPython): Returns EV3MicroPython (async, 1-15ms latency)
    Legacy (SSH): Returns EV3Interface (sync, 30-50ms latency)
    
    Usage:
        # MicroPython (recommended)
        config = ConnectionConfig(platform=Platform.EV3, transport=Transport.AUTO)
        ev3 = get_ev3_interface(config)
        async with ev3:
            await ev3.beep(880, 200)
        
        # Legacy SSH
        config = ConnectionConfig(platform=Platform.EV3, transport=Transport.SSH)
        ev3 = get_ev3_interface(config)
        ev3.connect()
    """
    from .types import Platform, Transport
    
    if config.platform != Platform.EV3:
        raise ValueError(f"Expected EV3 platform, got {config.platform}")
    
    if config.transport == Transport.SSH:
        # Legacy SSH interface
        from platforms.ev3.ev3_interface import EV3Interface
        return EV3Interface(
            host=config.host,
            user=config.user,
            password=config.password,
            port=config.ssh_port,
        )
    else:
        # Default: MicroPython (USB/WiFi/Bluetooth)
        from platforms.ev3.ev3_micropython import EV3MicroPython, EV3Config
        ev3_config = EV3Config(
            wifi_host=config.host,
            wifi_port=config.wifi_port,
            usb_port=config.usb_port,
            usb_baudrate=config.usb_baudrate,
            bt_address=config.bt_address,
            bt_channel=config.bt_channel,
        )
        transport_map = {
            Transport.AUTO: None,
            Transport.USB: "usb",
            Transport.WIFI: "wifi",
            Transport.BLUETOOTH: "bluetooth",
        }
        return EV3MicroPython(
            config=ev3_config,
            transport=transport_map.get(config.transport),
        )


def get_interface(config: ConnectionConfig) -> RobotInterface:
    """
    Factory function to get platform-specific interface.
    
    DEPRECATED for EV3: Use get_ev3_interface() or import EV3MicroPython directly.
    The new MicroPython interface is async and much faster (1-15ms vs 30-50ms).
    """
    from .types import Platform, Transport
    
    if config.platform == Platform.EV3:
        # Check if using legacy SSH transport
        if config.transport == Transport.SSH:
            from platforms.ev3.ev3_interface import EV3Interface
            return EV3Interface(
                host=config.host,
                user=config.user,
                password=config.password,
                port=config.ssh_port,
            )
        else:
            # For non-SSH transports, recommend using get_ev3_interface() or EV3MicroPython directly
            raise NotImplementedError(
                "For EV3 with MicroPython, use:\n"
                "  from platforms.ev3 import EV3MicroPython\n"
                "  async with EV3MicroPython() as ev3: ..."
            )
    elif config.platform == Platform.SPIKE_PRIME:
        # Spike Prime uses async interface - return config for async usage
        from platforms.spike_prime import SpikeInterface
        return SpikeInterface(
            address=getattr(config, 'address', ''),
            name=getattr(config, 'name', 'Spike Prime'),
            slot=getattr(config, 'slot', 19),
        )
    else:
        raise ValueError(f"Unknown platform: {config.platform}")


def get_daemon_session(interface: RobotInterface, daemon_script: str, 
                       sudo_password: str = "maker") -> DaemonSession:
    """
    Factory function to get platform-specific daemon session.
    
    DEPRECATED: EV3MicroPython doesn't need separate daemon sessions.
    Use EV3MicroPython directly for lowest latency.
    
    This function only works with legacy SSH interface (EV3Interface).
    """
    from platforms.ev3.ev3_interface import EV3Interface, EV3DaemonSession
    
    if isinstance(interface, EV3Interface):
        return EV3DaemonSession(interface, daemon_script, sudo_password)
    else:
        raise NotImplementedError(
            "Daemon session not needed for MicroPython interface.\n"
            "Use EV3MicroPython directly: await ev3.send('command')"
        )

