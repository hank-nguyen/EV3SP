#!/usr/bin/env python3
"""
Orchestra Interactive Shell
---------------------------
IPython-like terminal for controlling EV3 and Spike Prime robots.

Features:
- Unified commands: "ev3 beep", "sp display heart", "all status"
- Tab completion for commands and arguments
- Command history
- Color output with latency display
- Parallel execution support

Usage:
    from core.shell import OrchestraShell
    
    shell = OrchestraShell()
    await shell.connect()
    await shell.run()  # Interactive loop
"""

import os
import sys
import asyncio
import time
import readline
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

# Add root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from core.commands import (
    COMMANDS, get_command, list_commands, get_categories,
    format_command_help, parse_command_line,
    get_ev3_command, get_spike_action, get_completions,
    Platform, Command
)


# ============================================================
# ANSI COLORS
# ============================================================

class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Standard colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    
    # Background
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"


def colored(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{color}{text}{Colors.RESET}"


def success(text: str) -> str:
    return colored(f"✓ {text}", Colors.GREEN)


def error(text: str) -> str:
    return colored(f"✗ {text}", Colors.RED)


def warning(text: str) -> str:
    return colored(f"⚠ {text}", Colors.YELLOW)


def info(text: str) -> str:
    return colored(f"ℹ {text}", Colors.CYAN)


def latency_color(ms: float) -> str:
    """Get color for latency value."""
    if ms < 50:
        return Colors.GREEN
    elif ms < 200:
        return Colors.YELLOW
    else:
        return Colors.RED


# ============================================================
# DEVICE STATE
# ============================================================

@dataclass
class DeviceInfo:
    """Connected device information."""
    name: str
    platform: Platform
    connected: bool = False
    interface: Any = None
    session: Any = None  # EV3 daemon session
    last_latency: float = 0.0
    command_count: int = 0


# ============================================================
# ORCHESTRA SHELL
# ============================================================

class OrchestraShell:
    """
    Interactive shell for controlling multiple LEGO robots.
    
    Commands:
        ev3 <command> [args...]   - Send to EV3
        sp <command> [args...]    - Send to Spike Prime
        all <command> [args...]   - Send to all devices
        <command> [args...]       - Send to default device
        
        help [command]            - Show help
        devices                   - List connected devices
        history                   - Show command history
        quit                      - Exit shell
    """
    
    BANNER = r"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ██████╗ ██████╗  ██████╗██╗  ██╗███████╗███████╗████████╗   ║
║  ██╔═══██╗██╔══██╗██╔════╝██║  ██║██╔════╝██╔════╝╚══██╔══╝   ║
║  ██║   ██║██████╔╝██║     ███████║█████╗  ███████╗   ██║      ║
║  ██║   ██║██╔══██╗██║     ██╔══██║██╔══╝  ╚════██║   ██║      ║
║  ╚██████╔╝██║  ██║╚██████╗██║  ██║███████╗███████║   ██║      ║
║   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝      ║
║                                                               ║
║              LEGO Robotics Orchestra Shell                    ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize Orchestra Shell.
        
        Args:
            config_path: Path to config.yaml (optional)
        """
        self.config_path = config_path
        self.devices: Dict[str, DeviceInfo] = {}
        self.default_target = "all"
        self.history: List[str] = []
        self._running = False
        self._conductor = None
        
        # Setup readline for tab completion and history
        self._setup_readline()
    
    def _setup_readline(self):
        """Configure readline for tab completion and history."""
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self._completer)
        
        # History file
        history_file = os.path.expanduser("~/.orchestra_history")
        try:
            readline.read_history_file(history_file)
        except FileNotFoundError:
            pass
        
        import atexit
        atexit.register(readline.write_history_file, history_file)
    
    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab completion function for readline."""
        line = readline.get_line_buffer()
        
        # Get the part before cursor for context
        cursor = readline.get_begidx()
        context = line[:cursor]
        
        completions = get_completions(text, context)
        
        # Add internal commands
        internal = ["help", "devices", "history", "connect", "disconnect", "quit", "exit"]
        if not context.strip():
            completions.extend([c for c in internal if c.startswith(text.lower())])
        
        if state < len(completions):
            return completions[state]
        return None
    
    async def connect(self, ev3_host: str = None, spike_address: str = None,
                      spike_name: str = None) -> bool:
        """
        Connect to robots in parallel.
        
        Args:
            ev3_host: EV3 hostname or IP (None to skip)
            spike_address: Spike Prime BLE address (None to skip)
            spike_name: Spike Prime hub name
        
        Returns:
            True if at least one device connected
        """
        print(colored("\n[Orchestra] Connecting to devices in parallel...", Colors.CYAN))
        
        # Build list of connection tasks
        tasks = []
        task_names = []
        
        if ev3_host:
            tasks.append(self._connect_ev3_safe(ev3_host))
            task_names.append(f"EV3 ({ev3_host})")
        
        if spike_address:
            tasks.append(self._connect_spike_safe(spike_address, spike_name or "Spike Prime"))
            task_names.append(f"Spike ({spike_name or 'Spike Prime'})")
        
        if not tasks:
            print(warning("No devices specified. Use 'connect' command to add devices."))
            return False
        
        # Run all connections in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        connected = 0
        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                print(error(f"{name}: {result}"))
            elif result:
                connected += 1
        
        if connected > 0:
            print(success(f"Connected to {connected} device(s)"))
        else:
            print(warning("No devices connected. Use 'connect' command to add devices."))
        
        return connected > 0
    
    async def _connect_ev3_safe(self, host: str, user: str = "robot",
                                password: str = "maker") -> bool:
        """Connect to EV3 with exception handling."""
        try:
            await self._connect_ev3(host, user, password)
            return True
        except Exception as e:
            print(error(f"EV3 ({host}): {e}"))
            return False
    
    async def _connect_spike_safe(self, address: str, name: str) -> bool:
        """Connect to Spike Prime with exception handling."""
        try:
            await self._connect_spike(address, name)
            return True
        except Exception as e:
            print(error(f"Spike ({name}): {e}"))
            return False
    
    async def _connect_ev3(self, host: str, user: str = "robot", 
                           password: str = "maker") -> None:
        """Connect to EV3 and start generic daemon."""
        from platforms.ev3.ev3_interface import EV3Interface, EV3DaemonSession
        from concurrent.futures import ThreadPoolExecutor
        
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=2)
        
        # Connect
        interface = EV3Interface(host, user, password)
        await loop.run_in_executor(executor, interface.connect)
        
        # Load and start universal daemon
        daemon_path = os.path.join(ROOT_DIR, "platforms/ev3/universal_daemon.py")
        if os.path.exists(daemon_path):
            with open(daemon_path) as f:
                script_content = f.read()
        else:
            # Fallback to orchestra daemon
            daemon_path = os.path.join(ROOT_DIR, "projects/orchestra/ev3_orchestra_daemon.py")
            with open(daemon_path) as f:
                script_content = f.read()
        
        session = EV3DaemonSession(interface, "universal_daemon.py", password)
        await loop.run_in_executor(executor, lambda: session.start(script_content))
        
        # Register device
        self.devices["ev3"] = DeviceInfo(
            name="ev3",
            platform=Platform.EV3,
            connected=True,
            interface=interface,
            session=session,
        )
        
        print(success(f"EV3 ({host}) - Daemon ready"))
    
    async def _connect_spike(self, address: str, name: str) -> None:
        """Connect to Spike Prime."""
        from platforms.spike_prime.sp_fast import SpikeFastInterface
        
        interface = SpikeFastInterface(address, name)
        await interface.connect(preload=False)  # No pre-upload = no melody
        
        self.devices["sp"] = DeviceInfo(
            name="sp",
            platform=Platform.SPIKE,
            connected=True,
            interface=interface,
        )
        
        # Cyan color for Spike Prime
        print(colored(f"✓ Spike Prime ({name}) - Connected", Colors.CYAN))
    
    async def disconnect(self) -> None:
        """Disconnect all devices."""
        print(colored("[Orchestra] Disconnecting...", Colors.CYAN))
        
        for name, device in self.devices.items():
            if device.connected:
                try:
                    if device.platform == Platform.EV3:
                        if device.session:
                            device.session.stop()
                        if device.interface:
                            device.interface.disconnect()
                    elif device.platform == Platform.SPIKE:
                        if device.interface:
                            await device.interface.disconnect()
                    device.connected = False
                    print(success(f"Disconnected {name}"))
                except Exception as e:
                    print(error(f"Error disconnecting {name}: {e}"))
        
        self.devices.clear()
    
    async def execute(self, line: str) -> Optional[str]:
        """
        Execute a command line.
        
        Args:
            line: Command line (e.g., "ev3 beep high", "all status")
        
        Returns:
            Result string or None
        """
        line = line.strip()
        if not line:
            return None
        
        # Add to history
        self.history.append(line)
        
        # Parse command
        target, cmd_name, args = parse_command_line(line)
        
        # Handle internal commands
        internal_result = await self._handle_internal(cmd_name, args, line)
        if internal_result is not None:
            return internal_result
        
        # Get command definition
        cmd = get_command(cmd_name)
        if not cmd:
            return error(f"Unknown command: {cmd_name}. Type 'help' for available commands.")
        
        # Determine target devices
        targets = self._get_targets(target, cmd)
        if not targets:
            return warning(f"No connected devices support '{cmd_name}'")
        
        # Execute on targets
        results = await self._execute_on_targets(cmd, args, targets)
        
        return self._format_results(results)
    
    async def _handle_internal(self, cmd: str, args: Dict, full_line: str) -> Optional[str]:
        """Handle internal shell commands."""
        cmd = cmd.lower()
        
        if cmd in ("quit", "exit", "q"):
            self._running = False
            return colored("Goodbye! 👋", Colors.MAGENTA)
        
        if cmd == "help":
            return self._show_help(args.get("pattern") or (full_line.split()[1] if len(full_line.split()) > 1 else None))
        
        if cmd == "devices":
            return self._show_devices()
        
        if cmd == "history":
            return self._show_history()
        
        if cmd == "connect":
            # Parse: connect ev3 192.168.68.111 or connect sp E1BD...
            parts = full_line.split()
            if len(parts) >= 3:
                device_type = parts[1].lower()
                if device_type == "ev3":
                    await self._connect_ev3(parts[2])
                    return success(f"Connected to EV3 at {parts[2]}")
                elif device_type in ("sp", "spike"):
                    name = parts[3] if len(parts) > 3 else "Spike Prime"
                    await self._connect_spike(parts[2], name)
                    return success(f"Connected to Spike Prime ({name})")
            return info("Usage: connect ev3 <host> | connect sp <address> [name]")
        
        if cmd == "disconnect":
            await self.disconnect()
            return success("All devices disconnected")
        
        if cmd == "clear":
            os.system('clear' if os.name == 'posix' else 'cls')
            return None
        
        # Not an internal command
        return None
    
    def _get_targets(self, target: Optional[str], cmd: Command) -> List[DeviceInfo]:
        """Get list of target devices for a command."""
        targets = []
        
        if target == "all" or target is None:
            # Send to all compatible connected devices
            for device in self.devices.values():
                if device.connected and cmd.supports(device.platform):
                    targets.append(device)
        elif target == "ev3":
            if "ev3" in self.devices and self.devices["ev3"].connected:
                if cmd.supports(Platform.EV3):
                    targets.append(self.devices["ev3"])
        elif target == "sp":
            if "sp" in self.devices and self.devices["sp"].connected:
                if cmd.supports(Platform.SPIKE):
                    targets.append(self.devices["sp"])
        
        return targets
    
    async def _execute_on_targets(self, cmd: Command, args: Dict, 
                                   targets: List[DeviceInfo]) -> List[Tuple[str, bool, float, str]]:
        """
        Execute command on target devices.
        
        Returns:
            List of (device_name, success, latency_ms, response)
        """
        async def execute_single(device: DeviceInfo):
            t0 = time.time()
            try:
                if device.platform == Platform.EV3:
                    response = await self._execute_ev3(device, cmd, args)
                elif device.platform == Platform.SPIKE:
                    response = await self._execute_spike(device, cmd, args)
                else:
                    response = "Unknown platform"
                
                latency = (time.time() - t0) * 1000
                device.last_latency = latency
                device.command_count += 1
                return (device.name, True, latency, response)
            except Exception as e:
                latency = (time.time() - t0) * 1000
                return (device.name, False, latency, str(e))
        
        # Execute in parallel
        tasks = [execute_single(device) for device in targets]
        results = await asyncio.gather(*tasks)
        
        return list(results)
    
    async def _execute_ev3(self, device: DeviceInfo, cmd: Command, args: Dict) -> str:
        """Execute command on EV3."""
        from concurrent.futures import ThreadPoolExecutor
        
        # Build daemon command
        daemon_cmd = get_ev3_command(cmd.name, args)
        
        # Send to daemon
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=1)
        response = await loop.run_in_executor(executor, device.session.send, daemon_cmd)
        
        return response
    
    async def _execute_spike(self, device: DeviceInfo, cmd: Command, args: Dict) -> str:
        """Execute command on Spike Prime."""
        action = get_spike_action(cmd.name, args)
        
        # Special handling for certain commands
        if cmd.name == "beep":
            pitch = args.get("pitch", "high")
            duration = args.get("duration", 200)
            
            if pitch in ("high", "med", "low"):
                await device.interface.fast_action(f"beep_{pitch}", wait_response=False)
            else:
                # Custom frequency
                try:
                    freq = int(pitch)
                    await device.interface.run_sequence([("beep", freq, duration)])
                except ValueError:
                    await device.interface.fast_action("beep_high", wait_response=False)
            return "OK"
        
        elif cmd.name == "display":
            pattern = args.get("pattern", "happy")
            await device.interface.fast_action(pattern, wait_response=False)
            return "OK"
        
        elif cmd.name == "status":
            return f"connected, actions: {device.command_count}"
        
        else:
            # Generic action
            await device.interface.fast_action(action, wait_response=False)
            return "OK"
    
    def _format_results(self, results: List[Tuple[str, bool, float, str]]) -> str:
        """Format execution results for display."""
        lines = []
        
        for device_name, succeeded, latency, response in results:
            lat_color = latency_color(latency)
            lat_str = colored(f"{latency:.0f}ms", lat_color)
            
            if succeeded:
                lines.append(f"  {colored(device_name, Colors.CYAN)}: {response} ({lat_str})")
            else:
                lines.append(f"  {colored(device_name, Colors.RED)}: {error(response)} ({lat_str})")
        
        return "\n".join(lines)
    
    def _show_help(self, cmd_name: str = None) -> str:
        """Show help for commands."""
        if cmd_name:
            cmd = get_command(cmd_name)
            if cmd:
                return format_command_help(cmd)
            return error(f"Unknown command: {cmd_name}")
        
        lines = [
            colored("━" * 60, Colors.DIM),
            colored("ORCHESTRA COMMANDS", Colors.BOLD),
            colored("━" * 60, Colors.DIM),
            "",
            colored("Usage:", Colors.YELLOW),
            "  <target> <command> [args...]",
            "  Targets: ev3, sp, all (or omit for all)",
            "",
        ]
        
        # Group by category
        for category in get_categories():
            lines.append(colored(f"[{category.upper()}]", Colors.MAGENTA))
            for cmd in list_commands(category):
                platforms = []
                if cmd.supports(Platform.EV3):
                    platforms.append("EV3")
                if cmd.supports(Platform.SPIKE):
                    platforms.append("SP")
                plat_str = colored(f"[{','.join(platforms)}]", Colors.DIM)
                lines.append(f"  {colored(cmd.name, Colors.GREEN):15} {cmd.description} {plat_str}")
            lines.append("")
        
        lines.extend([
            colored("[SHELL]", Colors.MAGENTA),
            f"  {colored('help', Colors.GREEN):15} Show this help",
            f"  {colored('help <cmd>', Colors.GREEN):15} Show command details",
            f"  {colored('devices', Colors.GREEN):15} List connected devices",
            f"  {colored('history', Colors.GREEN):15} Show command history",
            f"  {colored('clear', Colors.GREEN):15} Clear screen",
            f"  {colored('quit', Colors.GREEN):15} Exit shell",
            "",
            colored("Examples:", Colors.YELLOW),
            "  ev3 beep           - Beep on EV3",
            "  sp display heart   - Show heart on Spike Prime",
            "  all status         - Get status from all devices",
            "  beep high 500      - Beep on all (high pitch, 500ms)",
        ])
        
        return "\n".join(lines)
    
    def _show_devices(self) -> str:
        """Show connected devices."""
        if not self.devices:
            return warning("No devices connected. Use 'connect' command.")
        
        lines = [colored("Connected Devices:", Colors.BOLD)]
        
        for name, device in self.devices.items():
            status = colored("●", Colors.GREEN) if device.connected else colored("○", Colors.RED)
            platform = "EV3" if device.platform == Platform.EV3 else "Spike Prime"
            lat = f" (last: {device.last_latency:.0f}ms)" if device.last_latency > 0 else ""
            lines.append(f"  {status} {colored(name, Colors.CYAN)}: {platform}{lat}")
        
        return "\n".join(lines)
    
    def _show_history(self) -> str:
        """Show command history."""
        if not self.history:
            return info("No command history yet.")
        
        lines = [colored("Command History:", Colors.BOLD)]
        for i, cmd in enumerate(self.history[-20:], 1):
            lines.append(f"  {i:3}. {cmd}")
        
        return "\n".join(lines)
    
    def _prompt(self) -> str:
        """Generate prompt string."""
        # Show connected devices in prompt
        connected = []
        for name, device in self.devices.items():
            if device.connected:
                color = Colors.GREEN if device.platform == Platform.EV3 else Colors.BLUE
                connected.append(colored(name, color))
        
        if connected:
            devices_str = " ".join(connected)
            return f"[{devices_str}] ⚡ "
        else:
            return colored("[no devices] ", Colors.DIM) + "⚡ "
    
    async def run(self) -> None:
        """Run interactive shell loop."""
        print(colored(self.BANNER, Colors.CYAN))
        print(info("Type 'help' for commands, 'quit' to exit"))
        print()
        
        self._running = True
        
        while self._running:
            try:
                line = input(self._prompt())
                result = await self.execute(line)
                if result:
                    print(result)
                
            except KeyboardInterrupt:
                print("\n" + warning("Use 'quit' to exit"))
            except EOFError:
                print()
                self._running = False
            except Exception as e:
                print(error(f"Error: {e}"))
        
        # Cleanup
        await self.disconnect()
        print(colored("\n✨ Orchestra shell closed\n", Colors.MAGENTA))


# ============================================================
# MAIN ENTRY POINT
# ============================================================

async def main():
    """Run Orchestra Shell with config or manual connection."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Orchestra Interactive Shell")
    parser.add_argument("--config", "-c", help="Path to config.yaml")
    parser.add_argument("--ev3", help="EV3 host (e.g., 192.168.68.111)")
    parser.add_argument("--spike", help="Spike Prime BLE address")
    parser.add_argument("--spike-name", default="Spike Prime", help="Spike Prime hub name")
    
    args = parser.parse_args()
    
    shell = OrchestraShell(args.config)
    
    # Connect to specified devices
    if args.ev3 or args.spike:
        await shell.connect(
            ev3_host=args.ev3,
            spike_address=args.spike,
            spike_name=args.spike_name,
        )
    
    # Run interactive loop
    await shell.run()


if __name__ == "__main__":
    from core.utils import run_async_with_cleanup
    run_async_with_cleanup(main())

