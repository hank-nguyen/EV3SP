#!/usr/bin/env python3
"""
Unified Command Registry
------------------------
Platform-agnostic command definitions with platform-specific implementations.

Commands work across EV3 and Spike Prime with automatic translation.

Usage:
    from core.commands import COMMANDS, get_command, execute_command
    
    # Get command info
    cmd = get_command("beep")
    print(cmd.description)
    
    # Execute on specific platform
    result = await execute_command("beep", platform="ev3", args={"freq": 880})
"""

from dataclasses import dataclass, field
from typing import Dict, List, Callable, Any, Optional, Tuple
from enum import Enum


class Platform(Enum):
    EV3 = "ev3"
    SPIKE = "spike_prime"
    ALL = "all"


@dataclass
class CommandArg:
    """Command argument definition."""
    name: str
    type: type = str
    default: Any = None
    description: str = ""
    choices: List[Any] = field(default_factory=list)


@dataclass
class Command:
    """
    Unified command definition.
    
    Each command has:
    - name: Command identifier (e.g., "beep", "display", "status")
    - description: Human-readable description
    - category: Grouping (sound, display, motor, info, etc.)
    - args: List of arguments
    - ev3_action: How to execute on EV3 (daemon command string or callable)
    - spike_action: How to execute on Spike Prime (action name or callable)
    - aliases: Alternative names
    """
    name: str
    description: str
    category: str = "general"
    args: List[CommandArg] = field(default_factory=list)
    ev3_action: Optional[str] = None  # Daemon command or callable
    spike_action: Optional[str] = None  # Fast action name or callable
    aliases: List[str] = field(default_factory=list)
    platforms: List[Platform] = field(default_factory=lambda: [Platform.EV3, Platform.SPIKE])
    
    def supports(self, platform: Platform) -> bool:
        """Check if command supports platform."""
        return platform in self.platforms or Platform.ALL in self.platforms
    
    def get_action(self, platform: Platform) -> Optional[str]:
        """Get platform-specific action."""
        if platform == Platform.EV3:
            return self.ev3_action
        elif platform == Platform.SPIKE:
            return self.spike_action
        return None


# ============================================================
# COMMAND REGISTRY
# ============================================================

COMMANDS: Dict[str, Command] = {}


def register(cmd: Command) -> Command:
    """Register a command."""
    COMMANDS[cmd.name] = cmd
    for alias in cmd.aliases:
        COMMANDS[alias] = cmd
    return cmd


# ============================================================
# SOUND COMMANDS
# ============================================================

register(Command(
    name="beep",
    description="Play a beep sound",
    category="sound",
    args=[
        CommandArg("pitch", str, "high", "Pitch: high, med, low, or frequency in Hz", 
                   choices=["high", "med", "low"]),
        CommandArg("duration", int, 200, "Duration in milliseconds"),
    ],
    ev3_action="beep",  # Maps to daemon "beep" command
    spike_action="beep_high",  # Default, modified by pitch arg
    aliases=["b", "bip"],
))

register(Command(
    name="bark",
    description="Play a bark/woof sound (EV3 only)",
    category="sound",
    ev3_action="bark",
    spike_action=None,  # Not available on Spike
    platforms=[Platform.EV3],
    aliases=["woof"],
))

register(Command(
    name="speak",
    description="Text-to-speech (EV3 only)",
    category="sound",
    args=[
        CommandArg("text", str, "Hello", "Text to speak"),
    ],
    ev3_action="speak",
    platforms=[Platform.EV3],
    aliases=["say", "tts"],
))

register(Command(
    name="melody",
    description="Play a melody sequence",
    category="sound",
    args=[
        CommandArg("name", str, "happy", "Melody name", choices=["happy", "sad", "alert", "success"]),
    ],
    ev3_action="melody",
    spike_action="beep_sequence",
    aliases=["tune", "song"],
))

# ============================================================
# DISPLAY COMMANDS
# ============================================================

register(Command(
    name="display",
    description="Show pattern or text on display",
    category="display",
    args=[
        CommandArg("pattern", str, "happy", "Pattern or text to display",
                   choices=["happy", "sad", "heart", "angry", "surprised", "neutral", "check", "clear"]),
    ],
    ev3_action="eyes",  # EV3 uses "eyes" command
    spike_action="happy",  # Modified by pattern arg
    aliases=["show", "face", "eyes"],
))

register(Command(
    name="clear",
    description="Clear the display",
    category="display",
    ev3_action="eyes neutral",
    spike_action="clear",
    aliases=["cls"],
))

register(Command(
    name="text",
    description="Display text",
    category="display",
    args=[
        CommandArg("message", str, "Hi", "Text to display"),
    ],
    ev3_action="text",
    spike_action="display_text",  # Spike uses light_matrix.write()
))

# ============================================================
# STATUS/INFO COMMANDS
# ============================================================

register(Command(
    name="status",
    description="Get device status",
    category="info",
    ev3_action="status",
    spike_action="status",
    aliases=["stat", "info", "?"],
))

register(Command(
    name="battery",
    description="Get battery level",
    category="info",
    ev3_action="battery",
    spike_action="battery",
    aliases=["bat", "power"],
))

register(Command(
    name="motors",
    description="Get detailed motor positions and speeds",
    category="info",
    ev3_action="motors",
    spike_action=None,
    platforms=[Platform.EV3],
))

register(Command(
    name="sensors",
    description="Get all sensor readings",
    category="info",
    ev3_action="sensors",
    spike_action=None,
    platforms=[Platform.EV3],
))

register(Command(
    name="ping",
    description="Test connection latency",
    category="info",
    ev3_action="status",  # Quick status check
    spike_action="clear",  # Quick display clear
    aliases=["test", "alive"],
))

# ============================================================
# MOTOR COMMANDS
# ============================================================

register(Command(
    name="motor",
    description="Control a motor",
    category="motor",
    args=[
        CommandArg("port", str, "A", "Motor port (A, B, C, D, etc.)"),
        CommandArg("speed", int, 50, "Speed (-100 to 100)"),
        CommandArg("duration", int, 0, "Duration in ms (0 = run forever)"),
    ],
    ev3_action="motor",
    spike_action="motor",
    aliases=["m", "run"],
))

register(Command(
    name="stop",
    description="Stop all motors",
    category="motor",
    ev3_action="stop",
    spike_action="stop",
    aliases=["halt", "brake"],
))

# ============================================================
# ROBOT-SPECIFIC COMMANDS (EV3 Puppy)
# ============================================================

register(Command(
    name="standup",
    description="Stand up (puppy only)",
    category="action",
    ev3_action="standup",
    platforms=[Platform.EV3],
    aliases=["up", "stand"],
))

register(Command(
    name="sitdown",
    description="Sit down (puppy only)",
    category="action",
    ev3_action="sitdown",
    platforms=[Platform.EV3],
    aliases=["down", "sit"],
))

register(Command(
    name="shake",
    description="Shake paw (puppy only)",
    category="action",
    ev3_action="shake",
    platforms=[Platform.EV3],
))

register(Command(
    name="stretch",
    description="Stretch (puppy only)",
    category="action",
    ev3_action="stretch",
    platforms=[Platform.EV3],
))

# ============================================================
# SPECIAL COMMANDS
# ============================================================

register(Command(
    name="quit",
    description="Disconnect and exit",
    category="system",
    ev3_action="quit",
    spike_action="disconnect",
    aliases=["exit", "q", "bye"],
))


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_command(name: str) -> Optional[Command]:
    """Get command by name or alias."""
    return COMMANDS.get(name.lower())


def list_commands(category: str = None) -> List[Command]:
    """List all commands, optionally filtered by category."""
    seen = set()
    result = []
    for cmd in COMMANDS.values():
        if cmd.name not in seen:
            if category is None or cmd.category == category:
                result.append(cmd)
            seen.add(cmd.name)
    return sorted(result, key=lambda c: (c.category, c.name))


def get_categories() -> List[str]:
    """Get all command categories."""
    return sorted(set(cmd.category for cmd in COMMANDS.values()))


def format_command_help(cmd: Command) -> str:
    """Format command help text."""
    lines = [f"{cmd.name}: {cmd.description}"]
    
    if cmd.aliases:
        lines.append(f"  Aliases: {', '.join(cmd.aliases)}")
    
    if cmd.args:
        lines.append("  Arguments:")
        for arg in cmd.args:
            default = f" (default: {arg.default})" if arg.default else ""
            choices = f" [{', '.join(str(c) for c in arg.choices)}]" if arg.choices else ""
            lines.append(f"    {arg.name}{choices}: {arg.description}{default}")
    
    platforms = []
    if cmd.supports(Platform.EV3):
        platforms.append("EV3")
    if cmd.supports(Platform.SPIKE):
        platforms.append("Spike")
    if platforms:
        lines.append(f"  Platforms: {', '.join(platforms)}")
    
    return "\n".join(lines)


def parse_command_line(line: str) -> Tuple[Optional[str], str, Dict[str, Any]]:
    """
    Parse a command line like "ev3 beep high 500" or "sp display heart".
    
    Returns:
        (target, command, args)
        - target: "ev3", "sp", "all", or None (default target)
        - command: Command name
        - args: Dict of parsed arguments
    """
    parts = line.strip().split()
    if not parts:
        return None, "", {}
    
    # Check for target prefix
    target = None
    if parts[0].lower() in ("ev3", "sp", "spike", "all"):
        target = parts[0].lower()
        if target == "spike":
            target = "sp"
        parts = parts[1:]
    
    if not parts:
        return target, "", {}
    
    command = parts[0].lower()
    args_list = parts[1:]
    
    # Get command definition
    cmd = get_command(command)
    if not cmd:
        return target, command, {}
    
    # Parse arguments
    args = {}
    for i, arg_def in enumerate(cmd.args):
        if i < len(args_list):
            value = args_list[i]
            # Type conversion
            if arg_def.type == int:
                try:
                    value = int(value)
                except ValueError:
                    pass
            elif arg_def.type == float:
                try:
                    value = float(value)
                except ValueError:
                    pass
            elif arg_def.type == bool:
                value = value.lower() in ("true", "1", "yes", "on")
            args[arg_def.name] = value
        else:
            args[arg_def.name] = arg_def.default
    
    return target, command, args


def get_ev3_command(cmd_name: str, args: Dict[str, Any]) -> str:
    """
    Build EV3 daemon command string from command and args.
    
    Examples:
        get_ev3_command("beep", {"pitch": "high"}) -> "beep high"
        get_ev3_command("beep", {"pitch": "440", "duration": 500}) -> "beep 440 500"
        get_ev3_command("display", {"pattern": "happy"}) -> "eyes happy"
        get_ev3_command("speak", {"text": "hello"}) -> "speak hello"
    """
    cmd = get_command(cmd_name)
    if not cmd or not cmd.ev3_action:
        return cmd_name  # Fallback to raw command
    
    action = cmd.ev3_action
    
    # Special handling for specific commands
    if cmd_name == "beep":
        pitch = args.get("pitch", "high")
        duration = args.get("duration", 200)
        return "beep {} {}".format(pitch, duration)
    elif cmd_name == "display":
        pattern = args.get("pattern", "happy")
        return "eyes {}".format(pattern)
    elif cmd_name == "speak":
        text = args.get("text", "Hello")
        return "speak {}".format(text)
    elif cmd_name == "text":
        message = args.get("message", "Hi")
        return "text {}".format(message)
    elif cmd_name == "motor":
        port = args.get("port", "A")
        speed = args.get("speed", 50)
        duration = args.get("duration", 0)
        if duration > 0:
            return "motor {} {} {}".format(port, speed, duration)
        return "motor {} {}".format(port, speed)
    elif cmd_name == "melody":
        name = args.get("name", "happy")
        return "melody {}".format(name)
    
    return action


def get_spike_action(cmd_name: str, args: Dict[str, Any]) -> str:
    """
    Get Spike Prime action name from command and args.
    
    Examples:
        get_spike_action("beep", {"pitch": "high"}) -> "beep_high"
        get_spike_action("display", {"pattern": "heart"}) -> "heart"
    """
    cmd = get_command(cmd_name)
    if not cmd or not cmd.spike_action:
        return cmd_name
    
    action = cmd.spike_action
    
    # Special handling
    if cmd_name == "beep":
        pitch = args.get("pitch", "high")
        if pitch in ("high", "med", "low"):
            return f"beep_{pitch}"
        # Custom frequency - will need run_sequence
        return action
    elif cmd_name == "display":
        pattern = args.get("pattern", "happy")
        return pattern  # Spike uses pattern name directly
    
    return action


# ============================================================
# COMMAND COMPLETIONS (for tab completion)
# ============================================================

def get_completions(partial: str, context: str = "") -> List[str]:
    """
    Get tab completions for partial input.
    
    Args:
        partial: Partial command/argument being typed
        context: Previous parts of the command line
    
    Returns:
        List of possible completions
    """
    partial = partial.lower()
    context_parts = context.strip().split()
    
    # If no context, complete targets or commands
    if not context_parts:
        targets = ["ev3", "sp", "all"]
        commands = list(set(cmd.name for cmd in COMMANDS.values()))
        all_options = targets + commands
        return [o for o in all_options if o.startswith(partial)]
    
    # If first word is a target, complete commands
    first = context_parts[0].lower()
    if first in ("ev3", "sp", "spike", "all"):
        if len(context_parts) == 1:
            # Completing command after target
            commands = list(set(cmd.name for cmd in COMMANDS.values()))
            return [c for c in commands if c.startswith(partial)]
        else:
            # Completing args
            cmd_name = context_parts[1].lower()
            return _get_arg_completions(cmd_name, len(context_parts) - 2, partial)
    else:
        # First word is command, complete args
        cmd_name = first
        return _get_arg_completions(cmd_name, len(context_parts) - 1, partial)


def _get_arg_completions(cmd_name: str, arg_index: int, partial: str) -> List[str]:
    """Get completions for a specific argument position."""
    cmd = get_command(cmd_name)
    if not cmd or arg_index >= len(cmd.args):
        return []
    
    arg = cmd.args[arg_index]
    if arg.choices:
        return [str(c) for c in arg.choices if str(c).startswith(partial)]
    
    return []

