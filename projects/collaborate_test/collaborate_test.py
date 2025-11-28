#!/usr/bin/env python3
"""
Collaborate Test - Multi-Device Control
----------------------------------------
Platform-agnostic controller for multiple LEGO robots (EV3 + Spike Prime).

Usage via main.py:
    python main.py collaborate_test           # Interactive flow mode
    python main.py collaborate_test parallel  # Run parallel test
    python main.py collaborate_test sync      # Run synchronized test
    python main.py collaborate_test seq       # Run sequential test

Direct usage:
    from conductor import Conductor
    
    async with Conductor.from_config("configs/config.yaml") as conductor:
        await conductor.parallel(
            ("spike", "beep_high"),
            ("ev3", "bark"),
        )
"""

import os
import sys
import asyncio
import time
import yaml
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

# Add root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)


@dataclass
class DeviceConfig:
    """Device configuration from YAML."""
    name: str
    platform: str
    # EV3 transport: "micropython" (default, fast) or "ssh" (legacy)
    transport: str = "micropython"
    # EV3 settings
    host: str = "ev3dev.local"
    wifi_port: int = 9000  # For MicroPython TCP
    user: str = "robot"
    password: str = "maker"
    sudo_password: str = "maker"
    # Spike Prime settings
    address: str = ""
    hub_name: str = "Spike Prime"


@dataclass
class DeviceState:
    """Runtime state of a connected device."""
    config: DeviceConfig
    project: Optional[str] = None  # Which project runs on this device
    connected: bool = False
    interface: Any = None
    session: Any = None  # For EV3 daemon
    latency_ms: float = 0.0


class Conductor:
    """
    Multi-device orchestrator with lowest latency.
    
    Controls DEVICES (hardware), not projects.
    - EV3 (MicroPython): Uses EV3MicroPython for USB/WiFi TCP (~1-15ms) ⚡
    - EV3 (SSH): Uses EV3DaemonSession for legacy ev3dev (~30-50ms)
    - Spike Prime: Uses SpikeFastInterface with fire-and-forget (~10-30ms)
    
    Default transport is "micropython" for EV3 (fastest).
    Set transport="ssh" in config for legacy ev3dev support.
    """
    
    def __init__(self, latency_mode: str = "ack"):
        """
        Args:
            latency_mode: "fire" (fire-and-forget) or "ack" (wait for acknowledgment)
        """
        self.devices: Dict[str, DeviceState] = {}
        self.projects: Dict[str, str] = {}  # device_name -> project_name
        self.latency_mode = latency_mode
        self._executor = ThreadPoolExecutor(max_workers=10)
        self._daemon_scripts: Dict[str, str] = {}  # project_name -> script content
    
    @classmethod
    def from_config(cls, config_path: str) -> 'Conductor':
        """Create conductor from YAML config file."""
        # Config path is relative to collaborate_test.py location
        if not os.path.isabs(config_path):
            conductor_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(conductor_dir, config_path)
        
        config_dir = os.path.dirname(config_path)
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        # Load devices from separate file (like Hydra defaults)
        devices_path = os.path.join(config_dir, "devices.yaml")
        if os.path.exists(devices_path):
            with open(devices_path) as f:
                devices_config = yaml.safe_load(f)
                if devices_config and "devices" in devices_config:
                    config["devices"] = devices_config["devices"]
        
        # Get latency mode
        latency_mode = config.get("latency_mode", "fire")
        conductor = cls(latency_mode=latency_mode)
        
        # Load project mapping
        projects = config.get("projects", {})
        conductor.projects = {k: v for k, v in projects.items() if v}
        
        # Load devices
        devices = config.get("devices", {})
        for name, settings in devices.items():
            device_config = DeviceConfig(
                name=name,
                platform=settings.get("platform", "ev3"),
                transport=settings.get("transport", "micropython"),  # Default: MicroPython
                host=settings.get("host", "ev3dev.local"),
                wifi_port=settings.get("wifi_port", 9000),
                user=settings.get("user", "robot"),
                password=settings.get("password", "maker"),
                sudo_password=settings.get("sudo_password", "maker"),
                address=settings.get("address", ""),
                hub_name=settings.get("name", "Spike Prime"),
            )
            state = DeviceState(config=device_config)
            state.project = conductor.projects.get(name)
            conductor.devices[name] = state
        
        return conductor
    
    def add_ev3(self, name: str, host: str = "ev3dev.local", 
                project: str = None, **kwargs) -> 'Conductor':
        """Add an EV3 device."""
        config = DeviceConfig(
            name=name,
            platform="ev3",
            host=host,
            **kwargs
        )
        state = DeviceState(config=config)
        state.project = project
        self.devices[name] = state
        if project:
            self.projects[name] = project
        print(f"[Conductor] Registered EV3: {name} ({host})")
        return self
    
    def add_spike(self, name: str, address: str, hub_name: str = "Spike") -> 'Conductor':
        """Add a Spike Prime device."""
        config = DeviceConfig(
            name=name,
            platform="spike_prime",
            address=address,
            hub_name=hub_name,
        )
        self.devices[name] = DeviceState(config=config)
        print(f"[Conductor] Registered Spike: {name} ({hub_name})")
        return self
    
    async def connect_all(self) -> bool:
        """Connect to all devices in parallel. EV3 has higher priority (starts first)."""
        print("[Conductor] Connecting to all devices in parallel...")
        
        # Separate by platform: EV3 first (higher priority - slower, start early)
        ev3_names = [n for n, s in self.devices.items() if s.config.platform == "ev3"]
        other_names = [n for n, s in self.devices.items() if s.config.platform != "ev3"]
        
        # Start EV3 connections first, then others
        ev3_tasks = [self._connect_device(name) for name in ev3_names]
        other_tasks = [self._connect_device(name) for name in other_names]
        
        # Run all in parallel (EV3 tasks created first = started first)
        all_tasks = ev3_tasks + other_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        success_count = sum(1 for d in self.devices.values() if d.connected)
        print(f"[Conductor] Connected: {success_count}/{len(self.devices)}")
        
        return success_count == len(self.devices)
    
    async def _connect_device(self, name: str) -> bool:
        """Connect to a single device."""
        state = self.devices[name]
        config = state.config
        
        try:
            if config.platform == "ev3":
                return await self._connect_ev3(state)
            elif config.platform == "spike_prime":
                return await self._connect_spike(state)
            else:
                print(f"  ✗ {name}: Unknown platform {config.platform}")
                return False
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            return False
    
    async def _connect_ev3(self, state: DeviceState) -> bool:
        """Connect to EV3 using MicroPython (default) or legacy SSH."""
        config = state.config
        
        # Use MicroPython interface by default (faster!)
        if config.transport == "micropython":
            return await self._connect_ev3_micropython(state)
        else:
            return await self._connect_ev3_ssh(state)
    
    async def _connect_ev3_micropython(self, state: DeviceState) -> bool:
        """Connect to EV3 using MicroPython interface (USB/WiFi TCP)."""
        from platforms.ev3.ev3_micropython import EV3MicroPython, EV3Config
        
        config = state.config
        
        ev3_config = EV3Config(
            wifi_host=config.host,
            wifi_port=config.wifi_port,
        )
        
        interface = EV3MicroPython(config=ev3_config, transport="wifi")
        connected = await interface.connect()
        
        if not connected:
            print(f"  ✗ {config.name}: MicroPython connection failed")
            print(f"      Make sure pybricks_daemon.py is running on EV3")
            return False
        
        state.interface = interface
        state.connected = True
        
        print(f"  ✓ {config.name} (EV3 MicroPython) connected")
        print(f"      transport: {interface.transport_name}")
        return True
    
    async def _connect_ev3_ssh(self, state: DeviceState) -> bool:
        """Connect to EV3 using legacy SSH (ev3dev)."""
        from platforms.ev3.ev3_interface import EV3Interface, EV3DaemonSession
        
        config = state.config
        loop = asyncio.get_event_loop()
        
        # Connect (sync, run in executor)
        interface = EV3Interface(
            host=config.host,
            user=config.user,
            password=config.password,
        )
        await loop.run_in_executor(self._executor, interface.connect)
        state.interface = interface
        
        # Load daemon script based on project
        project = state.project
        if not project:
            print(f"  ✗ {config.name}: No project specified for EV3 device")
            print(f"      Add to config: projects: {{ ev3: <project_name> }}")
            return False
        
        if project not in self._daemon_scripts:
            # "collaborate_test" uses local daemon, others use project folder
            if project == "collaborate_test":
                daemon_path = os.path.join(os.path.dirname(__file__), "collaborate_test_daemon.py")
                daemon_name = "collaborate_test_daemon.py"
            else:
                daemon_path = os.path.join(ROOT_DIR, f"projects/{project}/{project}_daemon.py")
                daemon_name = f"{project}_daemon.py"
            with open(daemon_path) as f:
                self._daemon_scripts[project] = (f.read(), daemon_name)
        
        script_content, daemon_name = self._daemon_scripts[project]
        
        # Start daemon session
        session = EV3DaemonSession(interface, daemon_name, config.sudo_password)
        await loop.run_in_executor(
            self._executor,
            lambda: session.start(script_content)
        )
        state.session = session
        state.connected = True
        
        print(f"  ✓ {config.name} (EV3 SSH) connected")
        print(f"      daemon: {daemon_name}")
        return True
    
    async def _connect_spike(self, state: DeviceState) -> bool:
        """Connect to Spike Prime with fast interface."""
        from platforms.spike_prime.sp_fast import SpikeFastInterface
        
        config = state.config
        
        # Create fast interface WITHOUT pre-upload (minimizes melodies)
        interface = SpikeFastInterface(config.address, config.hub_name)
        await interface.connect(preload=False)  # No pre-upload = no melody at connect
        
        state.interface = interface
        state.connected = True
        
        print(f"  ✓ {config.name} (Spike) connected")
        print(f"      (no pre-upload = no melody yet)")
        return True
    
    async def disconnect_all(self) -> None:
        """Disconnect from all devices."""
        print("[Conductor] Disconnecting all...")
        
        for name, state in self.devices.items():
            if state.connected:
                try:
                    await self._disconnect_device(state)
                except Exception as e:
                    print(f"  ✗ {name}: {e}")
        
        print("[Conductor] All disconnected")
    
    async def _disconnect_device(self, state: DeviceState) -> None:
        """Disconnect a single device."""
        config = state.config
        
        if config.platform == "ev3":
            if config.transport == "micropython":
                # MicroPython interface (async)
                if state.interface:
                    await state.interface.disconnect()
            else:
                # Legacy SSH daemon (sync)
                loop = asyncio.get_event_loop()
                if state.session:
                    await loop.run_in_executor(self._executor, state.session.stop)
                if state.interface:
                    await loop.run_in_executor(self._executor, state.interface.disconnect)
        elif config.platform == "spike_prime":
            if state.interface:
                await state.interface.disconnect()
        
        state.connected = False
    
    async def send(self, device_name: str, action: str) -> Tuple[bool, float]:
        """
        Send action to a device.
        
        Returns:
            (success, latency_ms)
        """
        if device_name not in self.devices:
            return False, 0.0
        
        state = self.devices[device_name]
        if not state.connected:
            return False, 0.0
        
        t0 = time.time()
        
        try:
            if state.config.platform == "ev3":
                await self._send_ev3(state, action)
            elif state.config.platform == "spike_prime":
                await self._send_spike(state, action)
            
            latency = (time.time() - t0) * 1000
            state.latency_ms = latency
            return True, latency
            
        except Exception as e:
            print(f"[{device_name}] Error: {e}")
            return False, 0.0
    
    async def _send_ev3(self, state: DeviceState, action: str) -> None:
        """Send action to EV3 via MicroPython or SSH daemon."""
        config = state.config
        
        if config.transport == "micropython":
            # MicroPython interface (async)
            response, latency = await state.interface.send(action)
        else:
            # Legacy SSH daemon (sync, run in executor)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                state.session.send,
                action
            )
    
    async def _send_spike(self, state: DeviceState, action: str) -> None:
        """Send action to Spike Prime via fast interface."""
        wait = self.latency_mode == "ack"
        await state.interface.fast_action(action, wait_response=wait)
    
    async def spike_beep_sequence(self, device_name: str, count: int = 3, 
                                   freq: int = 880, dur: int = 200, delay_ms: int = 300) -> float:
        """
        Run multiple beeps on Spike as ONE program (only ONE startup melody).
        
        Args:
            device_name: Spike device name
            count: Number of beeps
            freq: Frequency in Hz
            dur: Duration per beep in ms
            delay_ms: Delay between beeps
        
        Returns:
            Total latency in ms
        """
        if device_name not in self.devices:
            return 0.0
        
        state = self.devices[device_name]
        if not state.connected or state.config.platform != "spike_prime":
            return 0.0
        
        return await state.interface.beep_sequence(count, freq, dur, delay_ms)
    
    async def parallel(self, *commands: Tuple[str, str]) -> Dict[str, Tuple[bool, float]]:
        """
        Send commands to multiple devices in parallel.
        
        Args:
            commands: Tuples of (device_name, action)
            
        Returns:
            Dict of {device_name: (success, latency_ms)}
        """
        t0 = time.time()
        
        tasks = [self.send(device, action) for device, action in commands]
        results = await asyncio.gather(*tasks)
        
        total = (time.time() - t0) * 1000
        
        output = {}
        for (device, action), (success, latency) in zip(commands, results):
            output[device] = (success, latency)
        
        return output
    
    async def sequence(self, *commands: Tuple[str, str], delay_ms: int = 300) -> None:
        """
        Execute commands in sequence with delay.
        
        Args:
            commands: Tuples of (device_name, action)
            delay_ms: Delay between commands in milliseconds
        """
        for device, action in commands:
            success, latency = await self.send(device, action)
            print(f"  [{device}] {action}: {latency:.0f}ms")
            await asyncio.sleep(delay_ms / 1000)
    
    # Context manager
    async def __aenter__(self):
        await self.connect_all()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Always cleanup, even on exception/interrupt
        if exc_type == KeyboardInterrupt:
            print("\n[Conductor] Interrupted, cleaning up...")
        await self.disconnect_all()
        # Don't suppress the exception
        return False


# ============================================================
# Controller class for main.py compatibility
# ============================================================

class Controller:
    """
    Wrapper for Conductor that provides main.py compatible interface.
    
    main.py expects:
        - flow() method for interactive mode
        - execute_action(action) method
        - disconnect() method
    """
    
    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), "configs/config.yaml")
        self.conductor = None
        self._loop = None
    
    def _get_loop(self):
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop
    
    def _run(self, coro):
        """Run async coroutine."""
        loop = self._get_loop()
        return loop.run_until_complete(coro)
    
    def connect(self):
        """Connect to all devices."""
        self.conductor = Conductor.from_config(self.config_path)
        return self._run(self.conductor.connect_all())
    
    def disconnect(self):
        """Disconnect from all devices."""
        if self.conductor:
            self._run(self.conductor.disconnect_all())
    
    def execute_action(self, action: str) -> dict:
        """
        Execute an action.
        
        Supported actions:
            - parallel: Run parallel test (SP beep + EV3 woof)
            - sync: Run synchronized test
            - seq: Run sequential test
            - ev3:<cmd>: Send command to EV3 (e.g., ev3:bark)
            - spike:<cmd>: Send command to Spike (e.g., spike:beep_high)
        """
        if not self.conductor:
            self.connect()
        
        try:
            if action == "parallel":
                self._run(self._test_parallel())
                return {"success": True}
            elif action == "sync":
                self._run(self._test_synchronized())
                return {"success": True}
            elif action == "seq":
                self._run(self._test_sequential())
                return {"success": True}
            elif action.startswith("ev3:"):
                cmd = action[4:]
                success, latency = self._run(self.conductor.send("ev3", cmd))
                return {"success": success, "latency_ms": latency}
            elif action.startswith("spike:"):
                cmd = action[6:]
                success, latency = self._run(self.conductor.send("spike", cmd))
                return {"success": success, "latency_ms": latency}
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _test_parallel(self):
        """Run parallel beep + woof test."""
        print("=" * 60)
        print("COLLABORATE TEST: Parallel SP beep + EV3 woof")
        print("=" * 60)
        
        results = await self.conductor.parallel(
            ("spike", "beep_high"),
            ("ev3", "bark"),
        )
        
        for device, (success, latency) in results.items():
            status = "✓" if success else "✗"
            print(f"  {status} {device}: {latency:.0f}ms")
    
    async def _test_synchronized(self):
        """
        Run synchronized test (1 melody only!).
        
        ALL Spike beeps in ONE program = 1 melody total.
        EV3 barks run in parallel via daemon.
        """
        print("=" * 60)
        print("COLLABORATE TEST: Synchronized beep + woof (1 melody!)")
        print("=" * 60)
        print("Strategy: ALL Spike beeps in ONE program = 1 melody")
        print("-" * 60)
        
        conductor = self.conductor
        
        async def spike_all_beeps():
            """Run all Spike beeps as ONE program."""
            state = conductor.devices.get("spike")
            if state and state.connected:
                actions = [
                    ("beep", 880, 200),
                    ("delay", 300),
                    ("beep", 880, 200),
                    ("delay", 300),
                    ("beep", 880, 200),
                ]
                print("  [Spike] Running 3 beeps as ONE program...")
                latency = await state.interface.run_sequence(actions, delay_ms=0)
                print(f"  ✓ [Spike] All beeps done: {latency:.0f}ms (1 melody!)")
        
        async def ev3_all_barks():
            """Run all EV3 barks via daemon."""
            for i in range(3):
                success, latency = await conductor.send("ev3", "bark")
                status = "✓" if success else "✗"
                print(f"  {status} [EV3] bark {i+1}/3: {latency:.0f}ms")
                await asyncio.sleep(0.5)
        
        # Run both in parallel
        await asyncio.gather(spike_all_beeps(), ev3_all_barks())
        
        print("-" * 60)
        print("✓ Complete: 1 melody only!")
    
    async def _test_sequential(self):
        """
        Run sequential test with TRUE alternation (1 melody only!).
        
        Uses run_interactive_sequence:
        - All Spike beeps in ONE program = 1 melody
        - Spike signals completion via print("DONE:N")
        - Host receives signal, triggers EV3 bark
        - Result: beep→bark→beep→bark with only 1 startup melody
        """
        print("=" * 60)
        print("COLLABORATE TEST: Sequential beep/woof (1 melody!)")
        print("=" * 60)
        print("Strategy: Spike signals completion → Host triggers EV3")
        print("-" * 60)
        
        conductor = self.conductor
        beep_count = [0]
        
        async def on_beep_done(n):
            """Called after each Spike beep completes."""
            beep_count[0] = n
            print(f"  [Spike] Beep {n} done, triggering EV3...")
            success, latency = await conductor.send("ev3", "bark")
            status = "✓" if success else "✗"
            print(f"  {status} [EV3] bark: {latency:.0f}ms")
        
        # Get Spike interface for interactive sequence
        state = conductor.devices.get("spike")
        if state and state.connected:
            actions = [
                ("beep", 880, 200),  # beep_high
                ("beep", 220, 200),  # beep_low
            ]
            latency = await state.interface.run_interactive_sequence(actions, on_beep_done)
            print("-" * 60)
            print(f"✓ Complete: {beep_count[0]} alternations, 1 melody only!")
        else:
            print("✗ Spike not connected")
    
    def flow(self):
        """Interactive flow mode."""
        if not self.conductor:
            self.connect()
        
        print("\n" + "=" * 60)
        print("COLLABORATE TEST - Interactive Mode")
        print("=" * 60)
        print("\nCommands:")
        print("  parallel   - Run parallel test (beep + woof)")
        print("  sync       - Run synchronized test (3 rounds)")
        print("  seq        - Run sequential test")
        print("  ev3:<cmd>  - Send to EV3 (e.g., ev3:bark, ev3:beep)")
        print("  spike:<cmd>- Send to Spike (e.g., spike:beep_high)")
        print("  status     - Show device status")
        print("  quit       - Exit")
        print()
        
        while True:
            try:
                cmd = input("> ").strip()
                if not cmd:
                    continue
                
                if cmd in ("quit", "exit", "q"):
                    break
                
                if cmd == "status":
                    self._print_status()
                    continue
                
                result = self.execute_action(cmd)
                if not result.get("success") and "error" in result:
                    print(f"Error: {result['error']}")
                elif "latency_ms" in result:
                    print(f"OK ({result['latency_ms']:.0f}ms)")
                    
            except KeyboardInterrupt:
                print("\nInterrupted")
                break
            except EOFError:
                break
    
    def _print_status(self):
        """Print device status."""
        print("\nDevices:")
        for name, state in self.conductor.devices.items():
            status = "✓" if state.connected else "✗"
            platform = state.config.platform
            print(f"  {status} {name} ({platform})")
            if state.latency_ms > 0:
                print(f"      last latency: {state.latency_ms:.0f}ms")
        print()


# ============================================================
# Direct run
# ============================================================

async def quick_test():
    """Quick test with default config."""
    config_path = os.path.join(os.path.dirname(__file__), "configs/config.yaml")
    
    async with Conductor.from_config(config_path) as conductor:
        print("\n[Test] Parallel beep + bark...")
        
        results = await conductor.parallel(
            ("spike", "beep_high"),
            ("ev3", "bark"),
        )
        
        for device, (success, latency) in results.items():
            status = "✓" if success else "✗"
            print(f"  {status} {device}: {latency:.0f}ms")


if __name__ == "__main__":
    asyncio.run(quick_test())

