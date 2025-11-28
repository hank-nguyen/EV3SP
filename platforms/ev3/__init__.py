"""
EV3 Platform
------------
LEGO MINDSTORMS EV3 implementation.

Default: MicroPython interface (USB Serial / WiFi TCP) - fastest!
Legacy:  ev3dev SSH interface (still available for backward compatibility)

Usage:
    # Default - MicroPython (recommended)
    from platforms.ev3 import EV3MicroPython, EV3Config
    
    async with EV3MicroPython() as ev3:
        await ev3.beep(880, 200)
    
    # With action translation (project-specific)
    from platforms.ev3 import EV3MicroPython, ActionAdapter
    
    async with EV3MicroPython() as ev3:
        ev3.load_actions("projects/puppy/configs/actions.yaml")
        await ev3.execute("sitdown")  # Translates to motor commands
    
    # Legacy - ev3dev SSH (requires paramiko)
    from platforms.ev3 import EV3Interface, EV3DaemonSession
    
    with EV3Interface("ev3dev.local") as ev3:
        ...
"""

# Default: MicroPython interface (fast USB/WiFi) - no external deps
from .ev3_micropython import EV3MicroPython, EV3Config

# Action adapter for high-level command translation
from .action_adapter import ActionAdapter, PUPPY_ACTIONS, get_puppy_adapter

# Alias for convenience
EV3 = EV3MicroPython

# Legacy: ev3dev SSH interface (requires paramiko - optional)
try:
    from .ev3_interface import EV3Interface, EV3DaemonSession
    EV3_SSH_AVAILABLE = True
except ImportError:
    EV3Interface = None
    EV3DaemonSession = None
    EV3_SSH_AVAILABLE = False

__all__ = [
    # Default (MicroPython)
    'EV3MicroPython',
    'EV3Config', 
    'EV3',
    # Action Adapter
    'ActionAdapter',
    'PUPPY_ACTIONS',
    'get_puppy_adapter',
    # Legacy (ev3dev SSH)
    'EV3Interface',
    'EV3DaemonSession',
    'EV3_SSH_AVAILABLE',
]
