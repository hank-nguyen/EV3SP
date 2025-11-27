"""
Platforms - Hardware-specific implementations
---------------------------------------------
Implementations for specific robot hardware.

Platforms:
- ev3: LEGO Mindstorms EV3 (SSH + daemon)
- spike_prime: LEGO Spike Prime (BLE + LEGO protocol)
"""

# Lazy imports to avoid pulling in all dependencies
__all__ = ['ev3', 'spike_prime']

