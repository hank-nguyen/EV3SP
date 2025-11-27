"""
Abstract Robot Interface
------------------------
Platform-agnostic interface for robot communication.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any
from .types import RobotState, ConnectionConfig


class RobotInterface(ABC):
    """Abstract interface for robot communication."""
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to robot."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection."""
        pass
    
    @abstractmethod
    def upload_file(self, local_path: str, remote_name: str) -> str:
        """Upload file to robot. Returns remote path."""
        pass
    
    @abstractmethod
    def execute_command(self, cmd: str, timeout: float = 30) -> tuple:
        """Execute command on robot. Returns (stdout, stderr, exit_code)."""
        pass
    
    @abstractmethod
    def get_state(self) -> RobotState:
        """Get current robot state."""
        pass
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class DaemonSession(ABC):
    """Abstract daemon session for low-latency control."""
    
    def __init__(self, interface: RobotInterface, daemon_script: str):
        self.interface = interface
        self.daemon_script = daemon_script
        self._running = False
    
    @abstractmethod
    def start(self, script_content: str = None) -> bool:
        """Start daemon. Returns True if successful."""
        pass
    
    @abstractmethod
    def send(self, cmd: str) -> str:
        """Send command and get response."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop daemon."""
        pass
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def flow(self, prompt: str = "> ", commands_help: str = None) -> None:
        """Interactive flow mode."""
        import time
        
        print("=" * 50)
        print("Robot Flow Mode (Low Latency)")
        print("=" * 50)
        
        if commands_help:
            print(commands_help)
        print("Type 'quit' to disconnect, 'help' for commands")
        print("-" * 50)
        
        while self._running:
            try:
                cmd = input("\n" + prompt).strip()
                
                if not cmd:
                    continue
                
                if cmd.lower() in ("quit", "exit", "q"):
                    try:
                        self.send("quit")
                    except:
                        pass
                    print("Goodbye!")
                    break
                
                if cmd.lower() == "help":
                    if commands_help:
                        print(commands_help)
                    else:
                        print("Available: status, stop, quit")
                    continue
                
                t0 = time.time()
                response = self.send(cmd)
                latency = (time.time() - t0) * 1000
                
                print("[Robot] %s (%.0fms)" % (response, latency))
                
            except KeyboardInterrupt:
                print("\n\nInterrupted.")
                try:
                    self.send("quit")
                except:
                    pass
                break
            except EOFError:
                print("\nGoodbye!")
                break
            except OSError as e:
                err = str(e)
                if "closed" in err.lower() or "quit" in err.lower():
                    print("\n[Disconnected] %s" % err)
                else:
                    print("[Error] %s" % err)
                break
            except Exception as e:
                print("[Error] %s" % e)
        
        self._running = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def get_interface(config: ConnectionConfig) -> RobotInterface:
    """Factory function to get platform-specific interface."""
    from .types import Platform
    
    if config.platform == Platform.EV3:
        from platforms.ev3.ev3_interface import EV3Interface
        return EV3Interface(
            host=config.host,
            user=config.user,
            password=config.password,
            port=config.port,
        )
    elif config.platform == Platform.SPIKE_PRIME:
        # Spike Prime uses async interface - return config for async usage
        from platforms.spike_prime import SpikeInterface
        return SpikeInterface(
            address=getattr(config, 'address', ''),
            name=getattr(config, 'name', 'Spike Prime'),
            slot=getattr(config, 'slot', 19),
        )
    else:
        raise ValueError(f"Unknown platform: {config.platform}")


def get_daemon_session(interface: RobotInterface, daemon_script: str, 
                       sudo_password: str = "maker") -> DaemonSession:
    """Factory function to get platform-specific daemon session."""
    from platforms.ev3.ev3_interface import EV3Interface, EV3DaemonSession
    
    if isinstance(interface, EV3Interface):
        return EV3DaemonSession(interface, daemon_script, sudo_password)
    else:
        raise NotImplementedError("Daemon session not implemented for this platform")

