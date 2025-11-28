"""
Core - Abstract Robot Interface Layer
-------------------------------------
Platform-agnostic abstractions for robot control.

Key components:
- RobotInterface: Base class for platform-specific implementations
- DaemonSession: Low-latency control via persistent connection
- Collaboration patterns: Signal-based, choreographed, parallel
- Commands: Unified command registry for all platforms
- Shell: Interactive terminal interface
- ProjectShell: Reusable shell utility for any project
- Utilities: Graceful shutdown, async cleanup
"""

from .interface import RobotInterface, DaemonSession
from .types import MotorState, SensorState, RobotState, Platform, Transport, ConnectionConfig
from .collaboration import (
    Signal,
    SignalQueue,
    CollaborationPattern,
    ParallelPattern,
    ChoreographedPattern,
    SignalBasedPattern,
    create_batched_program,
)
from .commands import (
    Command,
    CommandArg,
    COMMANDS,
    get_command,
    list_commands,
    get_categories,
    parse_command_line,
    get_ev3_command,
    get_spike_action,
)
from .project_shell import (
    ProjectShell,
    ShellCommand,
    Colors,
    colored,
    success,
    error,
    warning,
    info,
    create_shell,
)

__all__ = [
    # Interfaces
    'RobotInterface',
    'DaemonSession',
    
    # Types
    'MotorState',
    'SensorState',
    'RobotState',
    'Platform',
    'Transport',
    'ConnectionConfig',
    
    # Collaboration
    'Signal',
    'SignalQueue',
    'CollaborationPattern',
    'ParallelPattern',
    'ChoreographedPattern',
    'SignalBasedPattern',
    'create_batched_program',
    
    # Commands
    'Command',
    'CommandArg',
    'COMMANDS',
    'get_command',
    'list_commands',
    'get_categories',
    'parse_command_line',
    'get_ev3_command',
    'get_spike_action',
    
    # Project Shell
    'ProjectShell',
    'ShellCommand',
    'Colors',
    'colored',
    'success',
    'error',
    'warning',
    'info',
    'create_shell',
]

