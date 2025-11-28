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


class Transport(Enum):
    """Connection transport types for EV3."""
    AUTO = "auto"           # Auto-detect best transport (default)
    USB = "usb"             # USB Serial (~1-5ms) - fastest
    WIFI = "wifi"           # WiFi TCP Socket (~5-15ms)
    BLUETOOTH = "bluetooth" # Bluetooth RFCOMM (~10-20ms)
    SSH = "ssh"             # Legacy SSH via Paramiko (~30-50ms)


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
    transport: Transport = Transport.AUTO  # Default: auto-detect best transport
    
    # WiFi/SSH settings
    host: str = "ev3dev.local"
    wifi_port: int = 9000  # TCP socket port for MicroPython
    
    # SSH settings (legacy ev3dev)
    ssh_port: int = 22
    user: str = "robot"
    password: str = "maker"
    sudo_password: str = "maker"
    
    # USB Serial settings
    usb_port: Optional[str] = None  # Auto-detect if None
    usb_baudrate: int = 115200
    
    # Bluetooth settings
    bt_address: Optional[str] = None
    bt_channel: int = 1
    
    # Backward compatibility
    @property
    def port(self) -> int:
        """Legacy port property (SSH port)."""
        return self.ssh_port

