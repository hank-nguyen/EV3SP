#!/usr/bin/env python3
"""
Project Shell - Reusable Interactive Command Shell
---------------------------------------------------
Generic shell utility for any LEGO robotics project.
Provides readline, colors, history, help, and command execution.

Usage:
    from core.project_shell import ProjectShell, Colors, colored
    
    # Define commands
    commands = {
        "bark": ("Make the robot bark", my_bark_function),
        "standup": ("Stand up", my_standup_function),
    }
    
    # Create shell
    shell = ProjectShell(
        name="Puppy",
        commands=commands,
        connect_func=my_connect,
        disconnect_func=my_disconnect,
    )
    
    # Run
    shell.run()  # Blocking interactive loop
"""

import os
import sys
import readline
import time
from typing import Dict, List, Optional, Any, Callable, Tuple, Union
from dataclasses import dataclass, field


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


def format_latency(ms: float) -> str:
    """Format latency with color."""
    return colored(f"{ms:.0f}ms", latency_color(ms))


# ============================================================
# COMMAND DEFINITION
# ============================================================

@dataclass
class ShellCommand:
    """Definition of a shell command."""
    name: str
    description: str
    handler: Callable  # Function to call: handler(args_str) -> str or None
    usage: str = ""    # Usage hint (e.g., "<pattern>")
    aliases: List[str] = field(default_factory=list)


# ============================================================
# PROJECT SHELL
# ============================================================

class ProjectShell:
    """
    Reusable interactive shell for LEGO robotics projects.
    
    Features:
    - Tab completion for commands
    - Command history (saved to ~/.{name}_history)
    - Colored output with latency display
    - Built-in help, history, clear, quit commands
    - Custom connect/disconnect hooks
    - Easy command registration
    """
    
    def __init__(
        self,
        name: str,
        commands: Dict[str, Union[Tuple[str, Callable], ShellCommand]] = None,
        connect_func: Callable = None,
        disconnect_func: Callable = None,
        banner: str = None,
        prompt: str = None,
        history_file: str = None,
    ):
        """
        Initialize project shell.
        
        Args:
            name: Project name (e.g., "Puppy", "Orchestra")
            commands: Dict of {name: (description, handler)} or {name: ShellCommand}
            connect_func: Called at start, should return bool for success
            disconnect_func: Called at exit for cleanup
            banner: Custom ASCII banner (or None for default)
            prompt: Custom prompt string (or None for default "> ")
            history_file: Custom history file path
        """
        self.name = name
        self.connect_func = connect_func
        self.disconnect_func = disconnect_func
        self.custom_banner = banner
        self.custom_prompt = prompt
        
        # Command registry
        self.commands: Dict[str, ShellCommand] = {}
        self._register_builtin_commands()
        if commands:
            self.register_commands(commands)
        
        # State
        self.connected = False
        self.history: List[str] = []
        self._running = False
        self.command_count = 0
        self.last_latency = 0.0
        
        # Setup readline
        self.history_file = history_file or os.path.expanduser(f"~/.{name.lower()}_history")
        self._setup_readline()
    
    def _setup_readline(self):
        """Configure readline for tab completion and history."""
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self._completer)
        readline.set_completer_delims(" \t\n")
        
        # Load history
        try:
            readline.read_history_file(self.history_file)
        except FileNotFoundError:
            pass
        
        # Save history on exit
        import atexit
        atexit.register(readline.write_history_file, self.history_file)
    
    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab completion function."""
        # Get all command names and aliases
        completions = []
        for cmd in self.commands.values():
            if cmd.name.startswith(text.lower()):
                completions.append(cmd.name)
            for alias in cmd.aliases:
                if alias.startswith(text.lower()):
                    completions.append(alias)
        
        completions = sorted(set(completions))
        
        if state < len(completions):
            return completions[state]
        return None
    
    def _register_builtin_commands(self):
        """Register built-in shell commands."""
        self.commands["help"] = ShellCommand(
            name="help",
            description="Show available commands",
            handler=self._cmd_help,
            usage="[command]",
            aliases=["?", "h"],
        )
        self.commands["quit"] = ShellCommand(
            name="quit",
            description="Exit the shell",
            handler=self._cmd_quit,
            aliases=["exit", "q"],
        )
        self.commands["history"] = ShellCommand(
            name="history",
            description="Show command history",
            handler=self._cmd_history,
        )
        self.commands["clear"] = ShellCommand(
            name="clear",
            description="Clear the screen",
            handler=self._cmd_clear,
            aliases=["cls"],
        )
        self.commands["status"] = ShellCommand(
            name="status",
            description="Show connection status",
            handler=self._cmd_status,
        )
    
    def register_commands(self, commands: Dict[str, Union[Tuple[str, Callable], ShellCommand]]):
        """
        Register multiple commands.
        
        Args:
            commands: Dict of either:
                - {name: (description, handler)}
                - {name: ShellCommand}
        """
        for name, value in commands.items():
            if isinstance(value, ShellCommand):
                self.commands[name] = value
            elif isinstance(value, tuple) and len(value) >= 2:
                desc, handler = value[0], value[1]
                usage = value[2] if len(value) > 2 else ""
                aliases = value[3] if len(value) > 3 else []
                self.commands[name] = ShellCommand(
                    name=name,
                    description=desc,
                    handler=handler,
                    usage=usage,
                    aliases=aliases if isinstance(aliases, list) else [aliases],
                )
    
    def register(self, name: str, description: str, usage: str = "", aliases: List[str] = None):
        """
        Decorator to register a command.
        
        Usage:
            @shell.register("bark", "Make the robot bark")
            def bark(args):
                sound.speak("woof")
                return "OK"
        """
        def decorator(handler: Callable):
            self.commands[name] = ShellCommand(
                name=name,
                description=description,
                handler=handler,
                usage=usage,
                aliases=aliases or [],
            )
            return handler
        return decorator
    
    # ============================================================
    # BUILT-IN COMMAND HANDLERS
    # ============================================================
    
    def _cmd_help(self, args: str) -> str:
        """Show help for commands."""
        args = args.strip()
        
        if args:
            # Help for specific command
            cmd = self._find_command(args)
            if cmd:
                lines = [
                    colored(f"Command: {cmd.name}", Colors.BOLD),
                    f"  {cmd.description}",
                ]
                if cmd.usage:
                    lines.append(f"  Usage: {cmd.name} {cmd.usage}")
                if cmd.aliases:
                    lines.append(f"  Aliases: {', '.join(cmd.aliases)}")
                return "\n".join(lines)
            return error(f"Unknown command: {args}")
        
        # Show all commands
        lines = [
            "",
            colored("=" * 50, Colors.DIM),
            colored(f"{self.name.upper()} COMMANDS", Colors.BOLD),
            colored("=" * 50, Colors.DIM),
            "",
        ]
        
        # Group: project commands vs shell commands
        project_cmds = []
        shell_cmds = []
        
        for cmd in self.commands.values():
            if cmd.name in ("help", "quit", "history", "clear", "status"):
                shell_cmds.append(cmd)
            else:
                project_cmds.append(cmd)
        
        if project_cmds:
            lines.append(colored("[ACTIONS]", Colors.MAGENTA))
            for cmd in sorted(project_cmds, key=lambda c: c.name):
                usage = f" {cmd.usage}" if cmd.usage else ""
                lines.append(f"  {colored(cmd.name, Colors.GREEN):20} {cmd.description}")
            lines.append("")
        
        lines.append(colored("[SHELL]", Colors.MAGENTA))
        for cmd in sorted(shell_cmds, key=lambda c: c.name):
            lines.append(f"  {colored(cmd.name, Colors.GREEN):20} {cmd.description}")
        
        lines.append("")
        lines.append(colored("Tip:", Colors.YELLOW) + " Type command name and press Enter")
        
        return "\n".join(lines)
    
    def _cmd_quit(self, args: str) -> str:
        """Exit the shell."""
        self._running = False
        return colored(f"Goodbye from {self.name}! 👋", Colors.MAGENTA)
    
    def _cmd_history(self, args: str) -> str:
        """Show command history."""
        if not self.history:
            return info("No command history yet.")
        
        lines = [colored("Command History:", Colors.BOLD)]
        for i, cmd in enumerate(self.history[-20:], 1):
            lines.append(f"  {i:3}. {cmd}")
        
        return "\n".join(lines)
    
    def _cmd_clear(self, args: str) -> str:
        """Clear the screen."""
        os.system('clear' if os.name == 'posix' else 'cls')
        return None
    
    def _cmd_status(self, args: str) -> str:
        """Show connection status."""
        status = colored("●", Colors.GREEN) if self.connected else colored("○", Colors.RED)
        state = "Connected" if self.connected else "Disconnected"
        
        lines = [
            colored(f"{self.name} Status:", Colors.BOLD),
            f"  {status} {state}",
            f"  Commands executed: {self.command_count}",
        ]
        if self.last_latency > 0:
            lines.append(f"  Last latency: {format_latency(self.last_latency)}")
        
        return "\n".join(lines)
    
    # ============================================================
    # COMMAND EXECUTION
    # ============================================================
    
    def _find_command(self, name: str) -> Optional[ShellCommand]:
        """Find command by name or alias."""
        name = name.lower().strip()
        
        # Direct match
        if name in self.commands:
            return self.commands[name]
        
        # Alias match
        for cmd in self.commands.values():
            if name in cmd.aliases:
                return cmd
        
        return None
    
    def execute(self, line: str) -> Optional[str]:
        """
        Execute a command line.
        
        Args:
            line: User input (e.g., "bark", "eyes happy")
        
        Returns:
            Result string to display, or None
        """
        line = line.strip()
        if not line:
            return None
        
        # Add to history
        self.history.append(line)
        
        # Parse command and args
        parts = line.split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Find command
        cmd = self._find_command(cmd_name)
        if not cmd:
            return error(f"Unknown command: {cmd_name}. Type 'help' for available commands.")
        
        # Execute with timing
        t0 = time.time()
        try:
            result = cmd.handler(args)
            latency = (time.time() - t0) * 1000
            self.last_latency = latency
            self.command_count += 1
            
            # Format result with latency
            if result and result != "OK":
                return f"{result} ({format_latency(latency)})"
            elif result == "OK":
                return success(f"{cmd.name} ({format_latency(latency)})")
            return None
            
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return error(f"{cmd.name} failed: {e} ({format_latency(latency)})")
    
    # ============================================================
    # SHELL LOOP
    # ============================================================
    
    def _default_banner(self) -> str:
        """Generate default banner."""
        width = 50
        name_line = f"  {self.name.upper()} INTERACTIVE SHELL  "
        padding = (width - len(name_line)) // 2
        
        return f"""
{colored("=" * width, Colors.CYAN)}
{" " * padding}{colored(name_line, Colors.BOLD + Colors.CYAN)}
{colored("=" * width, Colors.CYAN)}
"""
    
    def _get_prompt(self) -> str:
        """Get prompt string."""
        if self.custom_prompt:
            return self.custom_prompt
        
        status = colored("●", Colors.GREEN) if self.connected else colored("○", Colors.RED)
        return f"[{self.name}] {status} > "
    
    def run(self) -> None:
        """
        Run interactive shell loop (blocking).
        
        Call this after setup to start the interactive session.
        """
        # Show banner
        banner = self.custom_banner if self.custom_banner else self._default_banner()
        print(banner)
        
        # Connect if function provided
        if self.connect_func:
            try:
                result = self.connect_func()
                self.connected = result if isinstance(result, bool) else True
            except Exception as e:
                print(error(f"Connection failed: {e}"))
                self.connected = False
        else:
            self.connected = True
        
        # Show help hint
        print(info("Type 'help' for commands, 'quit' to exit"))
        print()
        
        self._running = True
        
        while self._running:
            try:
                line = input(self._get_prompt())
                result = self.execute(line)
                if result:
                    print(result)
                
            except KeyboardInterrupt:
                print("\n" + warning("Use 'quit' to exit"))
            except EOFError:
                print()
                self._running = False
            except Exception as e:
                print(error(f"Error: {e}"))
        
        # Disconnect if function provided
        if self.disconnect_func:
            try:
                self.disconnect_func()
            except Exception as e:
                print(error(f"Disconnect error: {e}"))
        
        print(colored(f"\n✨ {self.name} shell closed\n", Colors.MAGENTA))


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def create_shell(
    name: str,
    commands: Dict[str, Tuple[str, Callable]],
    connect: Callable = None,
    disconnect: Callable = None,
    banner: str = None,
) -> ProjectShell:
    """
    Quick helper to create a project shell.
    
    Args:
        name: Project name
        commands: Dict of {name: (description, handler)}
        connect: Connection function
        disconnect: Disconnect function
        banner: Custom banner
    
    Returns:
        Configured ProjectShell
    
    Example:
        shell = create_shell(
            "Puppy",
            {
                "bark": ("Make the robot bark", bark_func),
                "standup": ("Stand up", standup_func),
            },
            connect=my_connect,
            disconnect=my_disconnect,
        )
        shell.run()
    """
    return ProjectShell(
        name=name,
        commands=commands,
        connect_func=connect,
        disconnect_func=disconnect,
        banner=banner,
    )

