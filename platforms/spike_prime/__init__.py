"""
Spike Prime Platform
--------------------
LEGO Spike Prime implementation (App 3 firmware).

Key classes:
- SpikeInterface: Full-featured, uploads program per action
- SpikeFastInterface: Pre-uploads programs, batch sequences, signals
"""

from .sp_interface import (
    SpikeInterface,
    SpikeConfig,
    scan_for_hubs,
    PATTERNS,
    MELODIES,
    generate_display_program,
    generate_motor_program,
    generate_beep_program,
    generate_melody_program,
)
from .sp_fast import SpikeFastInterface

__all__ = [
    # Main interfaces
    'SpikeInterface',
    'SpikeFastInterface',
    
    # Config
    'SpikeConfig',
    'scan_for_hubs',
    
    # Patterns & generators
    'PATTERNS',
    'MELODIES',
    'generate_display_program',
    'generate_motor_program',
    'generate_beep_program',
    'generate_melody_program',
]
