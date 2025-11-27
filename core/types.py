"""
Common types for robot control.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class Platform(Enum):
    """Supported robot platforms."""
    EV3 = "ev3"
    SPIKE_PRIME = "spike_prime"


@dataclass
class MotorState:
    """Motor state."""
    position: int = 0
    speed: int = 0
    

@dataclass
class SensorState:
    """Sensor state."""
    type: str = "none"
    value: Any = None


@dataclass
class RobotState:
    """Complete robot state."""
    timestamp: float = 0.0
    motors: Dict[str, MotorState] = field(default_factory=dict)
    sensors: Dict[str, SensorState] = field(default_factory=dict)
    

@dataclass  
class ConnectionConfig:
    """Connection configuration."""
    platform: Platform = Platform.EV3
    host: str = "ev3dev.local"
    user: str = "robot"
    password: str = "maker"
    sudo_password: str = "maker"
    port: int = 22

