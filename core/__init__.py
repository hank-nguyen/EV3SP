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
- Utilities: Graceful shutdown, async cleanup
"""

from .interface import RobotInterface, DaemonSession
from .types import MotorState, SensorState, RobotState, Platform, ConnectionConfig
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

__all__ = [
    # Interfaces
    'RobotInterface',
    'DaemonSession',
    
    # Types
    'MotorState',
    'SensorState',
    'RobotState',
    'Platform',
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
]

