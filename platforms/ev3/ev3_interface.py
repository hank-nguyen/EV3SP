#!/usr/bin/env python3
"""
EV3 Remote Interface
--------------------
Host-side interface for job submission and sensor/motor streaming from EV3 Brick.
Connects via SSH to ev3dev.
"""

import argparse
import json
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import paramiko


@dataclass
class MotorState:
    position: int = 0
    speed: int = 0


@dataclass
class SensorState:
    type: str = "none"
    value: Optional[any] = None


@dataclass
class EV3State:
    timestamp: float = 0.0
    motors: dict = field(default_factory=lambda: {
        "A": MotorState(), "B": MotorState(),
        "C": MotorState(), "D": MotorState()
    })
    sensors: dict = field(default_factory=lambda: {
        "S1": SensorState(), "S2": SensorState(),
        "S3": SensorState(), "S4": SensorState()
    })


class EV3Interface:
    """Interface for communicating with EV3 Brick via SSH."""

    DEFAULT_HOST = "ev3dev.local"
    DEFAULT_USER = "robot"
    DEFAULT_PASSWORD = "maker"
    DEFAULT_PORT = 22
    STREAM_PORT = 9999
    EV3_WORK_DIR = "/home/robot/ev3"

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        user: str = DEFAULT_USER,
        password: str = DEFAULT_PASSWORD,
        port: int = DEFAULT_PORT,
    ):
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self._ssh: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._streaming = False
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_socket: Optional[socket.socket] = None
        self._callbacks = []  # List[Callable]

    def connect(self) -> None:
        """Establish SSH connection to EV3."""
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                timeout=10,
            )
            self._sftp = self._ssh.open_sftp()
            self._ensure_work_dir()
            # Green color for EV3
            print(f"\033[32m✓ EV3 ({self.host}) - Connected\033[0m")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to EV3: {e}")

    def disconnect(self) -> None:
        """Close SSH connection."""
        self.stop_streaming()
        if self._sftp:
            self._sftp.close()
        if self._ssh:
            self._ssh.close()
        print("✓ Disconnected from EV3")

    def _ensure_work_dir(self) -> None:
        """Ensure working directory exists on EV3."""
        self.execute_command(f"mkdir -p {self.EV3_WORK_DIR}")

    def execute_command(self, cmd: str, timeout: float = 30):
        """Execute command on EV3 and return (stdout, stderr, exit_code)."""
        if not self._ssh:
            self.connect()
        stdin, stdout, stderr = self._ssh.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return stdout.read().decode(), stderr.read().decode(), exit_code

    def upload_file(self, local_path: str, remote_name: Optional[str] = None) -> str:
        """Upload file to EV3. Returns remote path."""
        if not self._sftp:
            self.connect()
        local = Path(local_path)
        if not local.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        remote_name = remote_name or local.name
        remote_path = f"{self.EV3_WORK_DIR}/{remote_name}"
        self._sftp.put(str(local), remote_path)
        self.execute_command(f"chmod +x {remote_path}")
        print(f"✓ Uploaded {local.name} → {remote_path}")
        return remote_path

    def download_file(self, remote_name: str, local_path: str) -> None:
        """Download file from EV3."""
        if not self._sftp:
            self.connect()
        remote_path = f"{self.EV3_WORK_DIR}/{remote_name}"
        self._sftp.get(remote_path, local_path)
        print(f"✓ Downloaded {remote_path} → {local_path}")

    def submit_job(self, script_path: str, background: bool = False):
        """Upload and execute a Python script on EV3."""
        remote_path = self.upload_file(script_path)
        print(f"▶ Running {Path(script_path).name}...")
        if background:
            cmd = f"cd {self.EV3_WORK_DIR} && nohup python3 {remote_path} > /tmp/ev3_job.log 2>&1 &"
            self.execute_command(cmd)
            return "Job started in background", ""
        else:
            stdout, stderr, code = self.execute_command(
                f"cd {self.EV3_WORK_DIR} && python3 {remote_path}",
                timeout=300
            )
            if code != 0:
                print(f"✗ Job failed with exit code {code}")
            else:
                print("✓ Job completed")
            return stdout, stderr

    def stop_job(self) -> None:
        """Stop any running Python job on EV3."""
        self.execute_command("pkill -f 'python3.*ev3'")
        print("✓ Stopped running jobs")

    def motor_command(
        self,
        port: str,
        speed: int,
        duration: Optional[int] = None,
        position: Optional[int] = None,
    ) -> None:
        """
        Send motor command to EV3.
        
        Args:
            port: Motor port (A, B, C, or D)
            speed: Speed in degrees per second (-1000 to 1000)
            duration: Run duration in milliseconds (optional)
            position: Target position in degrees (optional)
        """
        port = port.upper()
        if port not in "ABCD":
            raise ValueError(f"Invalid port: {port}")
        
        # Use ev3dev sysfs interface
        motor_path = f"/sys/class/tacho-motor/motor{ord(port) - ord('A')}"
        
        if position is not None:
            cmd = f"""
echo position_sp > {motor_path}/position_sp
echo {position} > {motor_path}/position_sp
echo {abs(speed)} > {motor_path}/speed_sp
echo run-to-abs-pos > {motor_path}/command
"""
        elif duration is not None:
            cmd = f"""
echo {duration} > {motor_path}/time_sp
echo {abs(speed)} > {motor_path}/speed_sp
echo run-timed > {motor_path}/command
"""
        else:
            cmd = f"""
echo {speed} > {motor_path}/speed_sp
echo run-forever > {motor_path}/command
"""
        self.execute_command(cmd)
        print(f"✓ Motor {port}: speed={speed}" + 
              (f", duration={duration}ms" if duration else "") +
              (f", position={position}°" if position else ""))

    def stop_motor(self, port: str) -> None:
        """Stop a motor."""
        port = port.upper()
        motor_path = f"/sys/class/tacho-motor/motor{ord(port) - ord('A')}"
        self.execute_command(f"echo stop > {motor_path}/command")
        print(f"✓ Motor {port} stopped")

    def read_sensor(self, port: str, sensor_type: str = "auto") -> any:
        """
        Read sensor value from EV3.
        
        Args:
            port: Sensor port (S1, S2, S3, S4 or 1, 2, 3, 4)
            sensor_type: Sensor type (touch, color, ultrasonic, gyro, auto)
        
        Returns:
            Sensor value (type depends on sensor)
        """
        port = port.upper().replace("S", "")
        port_num = int(port) - 1
        
        # Find sensor path
        sensor_path = f"/sys/class/lego-sensor/sensor{port_num}"
        
        stdout, stderr, code = self.execute_command(f"cat {sensor_path}/value0")
        if code != 0:
            return None
        
        value = stdout.strip()
        
        # Parse based on sensor type
        if sensor_type == "touch":
            return value == "1"
        elif sensor_type == "color":
            colors = {0: "none", 1: "black", 2: "blue", 3: "green", 
                     4: "yellow", 5: "red", 6: "white", 7: "brown"}
            return colors.get(int(value), value)
        else:
            try:
                return int(value)
            except ValueError:
                return value

    def start_streaming(
        self,
        callback: Optional[Callable[[dict], None]] = None,
        interval_ms: int = 100,
    ) -> None:
        """
        Start receiving sensor/motor data stream from EV3.
        
        Args:
            callback: Function called with each data packet
            interval_ms: Polling interval in milliseconds
        """
        if callback:
            self._callbacks.append(callback)
        
        if self._streaming:
            return
        
        self._streaming = True
        self._stream_thread = threading.Thread(
            target=self._stream_loop,
            args=(interval_ms,),
            daemon=True
        )
        self._stream_thread.start()
        print(f"✓ Streaming started (interval={interval_ms}ms)")

    def _stream_loop(self, interval_ms: int) -> None:
        """Internal streaming loop."""
        interval_s = interval_ms / 1000.0
        
        while self._streaming:
            try:
                data = self._poll_ev3_state()
                for callback in self._callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        print(f"Callback error: {e}")
            except Exception as e:
                if self._streaming:
                    print(f"Stream error: {e}")
            time.sleep(interval_s)

    def _poll_ev3_state(self) -> dict:
        """Poll current state from EV3."""
        state = {
            "timestamp": time.time(),
            "motors": {},
            "sensors": {}
        }
        
        # Poll motors
        for port in "ABCD":
            try:
                motor_idx = ord(port) - ord('A')
                pos_out, _, _ = self.execute_command(
                    f"cat /sys/class/tacho-motor/motor{motor_idx}/position 2>/dev/null || echo 0"
                )
                speed_out, _, _ = self.execute_command(
                    f"cat /sys/class/tacho-motor/motor{motor_idx}/speed 2>/dev/null || echo 0"
                )
                state["motors"][port] = {
                    "position": int(pos_out.strip() or 0),
                    "speed": int(speed_out.strip() or 0)
                }
            except:
                state["motors"][port] = {"position": 0, "speed": 0}
        
        # Poll sensors
        for i in range(1, 5):
            port = f"S{i}"
            try:
                val_out, _, code = self.execute_command(
                    f"cat /sys/class/lego-sensor/sensor{i-1}/value0 2>/dev/null"
                )
                if code == 0:
                    state["sensors"][port] = {
                        "type": "detected",
                        "value": int(val_out.strip())
                    }
                else:
                    state["sensors"][port] = {"type": "none", "value": None}
            except:
                state["sensors"][port] = {"type": "none", "value": None}
        
        return state

    def stop_streaming(self) -> None:
        """Stop the data stream."""
        if not self._streaming:
            return
        self._streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=2)
        self._callbacks.clear()
        print("✓ Streaming stopped")

    def list_devices(self) -> dict:
        """List all connected motors and sensors on EV3."""
        devices = {"motors": [], "sensors": []}
        
        # List motors
        stdout, _, _ = self.execute_command("ls /sys/class/tacho-motor/ 2>/dev/null || true")
        for line in stdout.strip().split('\n'):
            if line.startswith('motor'):
                idx = int(line.replace('motor', ''))
                port = chr(ord('A') + idx)
                name_out, _, _ = self.execute_command(
                    f"cat /sys/class/tacho-motor/{line}/driver_name"
                )
                devices["motors"].append({
                    "port": port,
                    "driver": name_out.strip()
                })
        
        # List sensors
        stdout, _, _ = self.execute_command("ls /sys/class/lego-sensor/ 2>/dev/null || true")
        for line in stdout.strip().split('\n'):
            if line.startswith('sensor'):
                idx = int(line.replace('sensor', ''))
                port = f"S{idx + 1}"
                name_out, _, _ = self.execute_command(
                    f"cat /sys/class/lego-sensor/{line}/driver_name"
                )
                devices["sensors"].append({
                    "port": port,
                    "driver": name_out.strip()
                })
        
        return devices

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


class EV3DaemonSession:
    """
    Manages a persistent daemon session on EV3 for low-latency commands.
    Reusable base class for robot-specific controllers.
    
    Usage:
        session = EV3DaemonSession(ev3_interface, "my_daemon.py")
        session.start()
        session.send("standup")
        session.flow()  # Interactive mode
        session.stop()
    """
    
    def __init__(self, ev3: EV3Interface, daemon_script: str, sudo_password: str = "maker"):
        self.ev3 = ev3
        self.daemon_script = daemon_script
        self.sudo_password = sudo_password
        self._channel = None
        self._stdin = None
        self._stdout = None
        self._running = False
    
    def start(self, script_content: str = None) -> bool:
        """
        Start daemon on EV3.
        
        Args:
            script_content: Optional script content to upload (injects sudo_password)
        
        Returns:
            True if daemon started successfully
        """
        if not self.ev3._ssh:
            self.ev3.connect()
        
        # Upload script if content provided
        if script_content:
            import tempfile
            content = script_content.replace(
                'SUDO_PASSWORD = "maker"',
                'SUDO_PASSWORD = "' + self.sudo_password + '"'
            )
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(content)
                temp_path = f.name
            self.ev3.upload_file(temp_path, self.daemon_script)
            import os
            os.unlink(temp_path)
        
        # Start daemon via SSH channel
        transport = self.ev3._ssh.get_transport()
        self._channel = transport.open_session()
        self._channel.exec_command(
            "cd %s && python3 -u %s" % (self.ev3.EV3_WORK_DIR, self.daemon_script)
        )
        
        self._stdin = self._channel.makefile_stdin('wb', -1)
        self._stdout = self._channel.makefile('r', -1)
        
        # Wait for READY signal
        response = self._stdout.readline().strip()
        if "READY" in response:
            self._running = True
            print("✓ Daemon ready")
            return True
        else:
            print("✗ Daemon failed: " + response)
            return False
    
    def send(self, cmd: str) -> str:
        """
        Send command to daemon and get response.
        
        Args:
            cmd: Command string
            
        Returns:
            Response string from daemon
            
        Raises:
            OSError: If connection is closed
        """
        if not self._running:
            raise OSError("Daemon not running")
        
        try:
            self._stdin.write((cmd + "\n").encode())
            self._stdin.flush()
            response = self._stdout.readline().strip()
            
            if not response and cmd.lower() not in ("quit", "exit"):
                self._running = False
                raise OSError("Socket is closed")
            
            # Check if daemon quit (back button)
            if response.startswith("QUIT:"):
                self._running = False
                raise OSError(response)
            
            return response
            
        except (OSError, IOError) as e:
            self._running = False
            raise OSError("Connection closed: " + str(e))
    
    def flow(self, prompt: str = "> ", commands_help: str = None) -> None:
        """
        Interactive flow mode - accept commands from user input.
        
        Args:
            prompt: Input prompt string
            commands_help: Help text to show on startup
        """
        print("=" * 50)
        print("EV3 Flow Mode (Low Latency)")
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
                        print("Available: status, stop, eyes <style>, quit")
                    continue
                
                # Send command and measure latency
                t0 = time.time()
                response = self.send(cmd)
                latency = (time.time() - t0) * 1000
                
                print("[EV3] %s (%.0fms)" % (response, latency))
                
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
    
    def stop(self) -> None:
        """Stop daemon and cleanup."""
        if self._running:
            try:
                self.send("quit")
            except:
                pass
        
        self._running = False
        
        if self._stdin:
            try:
                self._stdin.close()
            except:
                pass
        if self._stdout:
            try:
                self._stdout.close()
            except:
                pass
        if self._channel:
            try:
                self._channel.close()
            except:
                pass
        
        self._stdin = None
        self._stdout = None
        self._channel = None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def main():
    parser = argparse.ArgumentParser(description="EV3 Remote Interface")
    parser.add_argument("--host", default=EV3Interface.DEFAULT_HOST, 
                       help="EV3 hostname or IP")
    parser.add_argument("--user", default=EV3Interface.DEFAULT_USER,
                       help="SSH username")
    parser.add_argument("--password", default=EV3Interface.DEFAULT_PASSWORD,
                       help="SSH password")
    
    # Actions
    parser.add_argument("--submit", metavar="SCRIPT", help="Submit job script")
    parser.add_argument("--background", action="store_true", 
                       help="Run job in background")
    parser.add_argument("--stream", action="store_true", 
                       help="Stream sensor/motor data")
    parser.add_argument("--interval", type=int, default=100,
                       help="Stream interval in ms")
    parser.add_argument("--motor", metavar="PORT", help="Motor port (A-D)")
    parser.add_argument("--speed", type=int, default=50, help="Motor speed")
    parser.add_argument("--duration", type=int, help="Motor duration (ms)")
    parser.add_argument("--stop-motor", metavar="PORT", help="Stop motor on port")
    parser.add_argument("--sensor", metavar="PORT", help="Read sensor on port")
    parser.add_argument("--sensor-type", default="auto", 
                       help="Sensor type (touch, color, ultrasonic, gyro)")
    parser.add_argument("--list-devices", action="store_true",
                       help="List connected devices")
    parser.add_argument("--cmd", metavar="COMMAND", help="Execute arbitrary command")
    
    args = parser.parse_args()
    
    with EV3Interface(args.host, args.user, args.password) as ev3:
        if args.submit:
            stdout, stderr = ev3.submit_job(args.submit, background=args.background)
            if stdout:
                print("--- Output ---")
                print(stdout)
            if stderr:
                print("--- Errors ---")
                print(stderr)
        
        elif args.stream:
            print("Streaming data (Ctrl+C to stop)...")
            ev3.start_streaming(
                callback=lambda d: print(json.dumps(d, indent=2)),
                interval_ms=args.interval
            )
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        
        elif args.motor:
            ev3.motor_command(args.motor, args.speed, args.duration)
        
        elif args.stop_motor:
            ev3.stop_motor(args.stop_motor)
        
        elif args.sensor:
            value = ev3.read_sensor(args.sensor, args.sensor_type)
            print(f"Sensor {args.sensor}: {value}")
        
        elif args.list_devices:
            devices = ev3.list_devices()
            print("Motors:")
            for m in devices["motors"]:
                print(f"  Port {m['port']}: {m['driver']}")
            print("Sensors:")
            for s in devices["sensors"]:
                print(f"  Port {s['port']}: {s['driver']}")
        
        elif args.cmd:
            stdout, stderr, code = ev3.execute_command(args.cmd)
            print(stdout)
            if stderr:
                print(stderr)


if __name__ == "__main__":
    main()

