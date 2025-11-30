#!/usr/bin/env pybricks-micropython
"""
Pybricks Daemon for EV3
-----------------------
Low-latency command daemon for EV3 running Pybricks MicroPython.

Supports multiple input sources:
- stdin (USB Serial connection)
- TCP Socket (WiFi connection)

Protocol:
    Host → EV3:  command [args...]\n
    EV3 → Host:  OK [result]\n  or  ERR: message\n

Commands:
    beep [freq] [dur]     - Play beep (default: 880Hz, 200ms)
    speak <text>          - Text-to-speech
    motor <port> <speed>  - Run motor (-100 to 100)
    motor <port> <speed> <time>  - Run motor for time (ms)
    stop <port>           - Stop motor
    sensor <port>         - Read sensor value
    eyes <expression>     - Show eye expression on display
    display <text>        - Show text on display
    status                - Get battery and motor status
    quit                  - Exit daemon

Deploy to EV3:
    1. Copy this file to EV3 via USB or network
    2. Run: brickrun pybricks_daemon.py

Usage from host:
    python ev3_micropython.py flow
"""

from pybricks.hubs import EV3Brick
from pybricks.ev3devices import Motor, TouchSensor, ColorSensor, UltrasonicSensor, GyroSensor
from pybricks.parameters import Port, Stop, Button
from pybricks.tools import wait, StopWatch
from pybricks.media.ev3dev import Font, SoundFile

import sys
import select

# Optional: TCP socket support (if usocket available)
try:
    import usocket as socket
    SOCKET_AVAILABLE = True
except ImportError:
    try:
        import socket
        SOCKET_AVAILABLE = True
    except ImportError:
        SOCKET_AVAILABLE = False

# =============================================================================
# Configuration
# =============================================================================

TCP_PORT = 9000  # Port for WiFi connections
USE_TCP = True   # Enable TCP for WiFi connections

# Motor port mapping
MOTOR_PORTS = {
    "A": Port.A,
    "B": Port.B,
    "C": Port.C,
    "D": Port.D,
}

# Sensor port mapping
SENSOR_PORTS = {
    "1": Port.S1,
    "2": Port.S2,
    "3": Port.S3,
    "4": Port.S4,
    "S1": Port.S1,
    "S2": Port.S2,
    "S3": Port.S3,
    "S4": Port.S4,
}

# Eye expressions (drawn on 178x128 display)
EYE_EXPRESSIONS = {
    "happy": "happy",
    "sad": "sad",
    "angry": "angry",
    "neutral": "neutral",
    "surprised": "surprised",
    "sleepy": "sleepy",
    "wink": "wink",
}

# =============================================================================
# Hardware Initialization
# =============================================================================

ev3 = EV3Brick()
motors = {}
sensors = {}
stopwatch = StopWatch()


def init_motors():
    """Try to initialize motors on all ports."""
    for name, port in MOTOR_PORTS.items():
        try:
            motors[name] = Motor(port)
        except Exception:
            pass  # Motor not connected


def init_sensors():
    """Try to initialize sensors on all ports."""
    sensor_types = [
        ("touch", TouchSensor),
        ("color", ColorSensor),
        ("ultrasonic", UltrasonicSensor),
        ("gyro", GyroSensor),
    ]
    
    for port_name, port in SENSOR_PORTS.items():
        if port_name.startswith("S"):
            continue  # Skip aliases
        for sensor_type, sensor_class in sensor_types:
            try:
                sensors[port_name] = (sensor_type, sensor_class(port))
                break
            except Exception:
                continue


# =============================================================================
# Command Handlers
# =============================================================================

def cmd_beep(args):
    """beep [freq] [dur] - Play beep."""
    freq = int(args[0]) if len(args) > 0 else 880
    dur = int(args[1]) if len(args) > 1 else 200
    ev3.speaker.beep(frequency=freq, duration=dur)
    return "OK"


def cmd_speak(args):
    """speak <text> - Text-to-speech."""
    if not args:
        return "ERR: speak requires text"
    text = " ".join(args)
    ev3.speaker.say(text)
    return "OK"


def cmd_sound(args):
    """sound <file> - Play sound file (dog_bark, cat_purr, etc.)."""
    if not args:
        return "ERR: sound requires file name"
    
    # Map common names to SoundFile enum
    sound_map = {
        "dog_bark": "DOG_BARK_1",
        "dog_bark_1": "DOG_BARK_1",
        "dog_bark_2": "DOG_BARK_2",
        "dog_growl": "DOG_GROWL",
        "dog_sniff": "DOG_SNIFF",
        "dog_whine": "DOG_WHINE",
        "cat_purr": "CAT_PURR",
        "elephant": "ELEPHANT_CALL",
        "snake_hiss": "SNAKE_HISS",
        "snake_rattle": "SNAKE_RATTLE",
        "t_rex_roar": "T_REX_ROAR",
        "horn_1": "HORN_1",
        "horn_2": "HORN_2",
        "laser": "LASER",
        "sonar": "SONAR",
        "click": "CLICK",
        "confirm": "CONFIRM",
        "general_alert": "GENERAL_ALERT",
        "error": "ERROR",
        "error_alarm": "ERROR_ALARM",
        "start": "START",
        "stop": "STOP",
        "object": "OBJECT",
        "ouch": "OUCH",
        "blip": "BLIP_1",
        "blip_1": "BLIP_1",
        "blip_2": "BLIP_2",
        "blip_3": "BLIP_3",
    }
    
    file_name = args[0].lower()
    
    # Try mapped name first
    if file_name in sound_map:
        try:
            from pybricks.media.ev3dev import SoundFile
            sound_file = getattr(SoundFile, sound_map[file_name])
            ev3.speaker.play_file(sound_file)
            return "OK"
        except Exception as e:
            return "ERR: {}".format(e)
    
    # Try direct SoundFile attribute
    try:
        from pybricks.media.ev3dev import SoundFile
        sound_file = getattr(SoundFile, file_name.upper())
        ev3.speaker.play_file(sound_file)
        return "OK"
    except AttributeError:
        return "ERR: unknown sound: {}".format(file_name)
    except Exception as e:
        return "ERR: {}".format(e)


def cmd_motor(args):
    """motor <port> <speed> [time_ms] - Run motor."""
    if len(args) < 2:
        return "ERR: motor requires port and speed"
    
    port = args[0].upper()
    if port not in motors:
        return "ERR: motor {} not connected".format(port)
    
    motor = motors[port]
    speed = int(args[1])
    
    if len(args) > 2:
        # Run for specific time
        time_ms = int(args[2])
        motor.run_time(speed, time_ms, wait=False)
    else:
        # Run continuously
        motor.run(speed)
    
    return "OK"


def cmd_stop(args):
    """stop <port> - Stop motor."""
    if not args:
        # Stop all motors
        for motor in motors.values():
            motor.stop()
        return "OK"
    
    port = args[0].upper()
    if port not in motors:
        return "ERR: motor {} not connected".format(port)
    
    motors[port].stop()
    return "OK"


def cmd_target(args):
    """target <port> <angle> [speed] - Move motor to target angle (degrees)."""
    if len(args) < 2:
        return "ERR: target requires port and angle"
    
    port = args[0].upper()
    if port not in motors:
        return "ERR: motor {} not connected".format(port)
    
    try:
        motor = motors[port]
        target_angle = int(args[1])
        speed = int(args[2]) if len(args) > 2 else 150
        
        # Calculate relative movement needed
        current = motor.angle()
        delta = target_angle - current
        
        if abs(delta) > 2:
            # Calculate time needed based on speed (deg/s)
            time_ms = abs(delta) * 1000 // speed + 100
            
            # Use run_time - must wait or motor gets interrupted
            direction = 1 if delta > 0 else -1
            motor.run_time(speed * direction, time_ms, wait=True)
        
        return "OK {}->{}".format(current, target_angle)
    except Exception as e:
        return "ERR: {}".format(e)


def cmd_target2(args):
    """target2 <port1> <port2> <angle> [speed] - Move 2 motors simultaneously with verification."""
    if len(args) < 3:
        return "ERR: target2 requires port1, port2, angle"
    
    port1 = args[0].upper()
    port2 = args[1].upper()
    
    if port1 not in motors:
        return "ERR: motor {} not connected".format(port1)
    if port2 not in motors:
        return "ERR: motor {} not connected".format(port2)
    
    try:
        motor1 = motors[port1]
        motor2 = motors[port2]
        target_angle = int(args[2])
        speed = int(args[3]) if len(args) > 3 else 150
        tolerance = 15  # Degrees tolerance for success
        
        # Calculate movements
        current1 = motor1.angle()
        current2 = motor2.angle()
        delta1 = target_angle - current1
        delta2 = target_angle - current2
        
        # Check if already at target
        if abs(delta1) <= 2 and abs(delta2) <= 2:
            return "OK already@{} {}:{} {}:{}".format(target_angle, port1, current1, port2, current2)
        
        # Start both motors (non-blocking)
        moved = False
        if abs(delta1) > 2:
            time_ms1 = abs(delta1) * 1000 // speed + 100
            dir1 = 1 if delta1 > 0 else -1
            motor1.run_time(speed * dir1, time_ms1, wait=False)
            moved = True
        
        if abs(delta2) > 2:
            time_ms2 = abs(delta2) * 1000 // speed + 100
            dir2 = 1 if delta2 > 0 else -1
            motor2.run_time(speed * dir2, time_ms2, wait=False)
            moved = True
        
        if not moved:
            return "OK already@{} {}:{} {}:{}".format(target_angle, port1, current1, port2, current2)
        
        # Wait for the longer movement
        max_time = max(
            abs(delta1) * 1000 // speed if abs(delta1) > 2 else 0,
            abs(delta2) * 1000 // speed if abs(delta2) > 2 else 0
        ) + 300
        wait(max_time)
        
        # Verify final positions
        final1 = motor1.angle()
        final2 = motor2.angle()
        error1 = abs(final1 - target_angle)
        error2 = abs(final2 - target_angle)
        
        if error1 > tolerance or error2 > tolerance:
            return "FAIL {}:{}->{}(err:{}) {}:{}->{}(err:{}) target:{}".format(
                port1, current1, final1, error1, port2, current2, final2, error2, target_angle)
        
        return "OK moved {}:{}->{} {}:{}->{} target:{}".format(
            port1, current1, final1, port2, current2, final2, target_angle)
    except Exception as e:
        return "ERR: {}".format(e)


def cmd_reset(args):
    """reset <port> - Reset motor angle to 0 (current position becomes 0)."""
    if not args:
        # Reset all motors
        for motor in motors.values():
            motor.reset_angle(0)
        return "OK"
    
    port = args[0].upper()
    if port not in motors:
        return "ERR: motor {} not connected".format(port)
    
    motors[port].reset_angle(0)
    return "OK"


def cmd_pos(args):
    """pos [port] - Get motor angle(s) in degrees."""
    try:
        if not args:
            # Get all motor positions
            positions = []
            for port in sorted(motors.keys()):
                angle = motors[port].angle()
                positions.append("{}:{}".format(port, angle))
            return "OK " + " ".join(positions)
        
        port = args[0].upper()
        if port not in motors:
            return "ERR: motor {} not connected".format(port)
        
        angle = motors[port].angle()
        return "OK {}".format(angle)
    except Exception as e:
        return "ERR: {}".format(e)


def cmd_sensor(args):
    """sensor <port> - Read sensor value."""
    if not args:
        return "ERR: sensor requires port"
    
    port = args[0].upper().replace("S", "")
    if port not in sensors:
        return "ERR: sensor {} not connected".format(port)
    
    sensor_type, sensor = sensors[port]
    
    try:
        if sensor_type == "touch":
            value = sensor.pressed()
        elif sensor_type == "color":
            value = sensor.color()
        elif sensor_type == "ultrasonic":
            value = sensor.distance()
        elif sensor_type == "gyro":
            value = sensor.angle()
        else:
            value = "unknown"
        
        return "OK {}".format(value)
    except Exception as e:
        return "ERR: {}".format(e)


def cmd_eyes(args):
    """eyes <expression> - Show eye expression."""
    if not args:
        return "ERR: eyes requires expression"
    
    expr = args[0].lower()
    if expr not in EYE_EXPRESSIONS:
        return "ERR: unknown expression: {}".format(expr)
    
    draw_eyes(expr)
    return "OK"


def cmd_display(args):
    """display <text> - Show text on display."""
    if not args:
        ev3.screen.clear()
        return "OK"
    
    text = " ".join(args)
    ev3.screen.clear()
    ev3.screen.print(text)
    return "OK"


def cmd_status(args):
    """status - Get battery and motor status."""
    battery = ev3.battery.voltage()
    motor_list = list(motors.keys())
    sensor_list = ["{}:{}".format(p, t) for p, (t, _) in sensors.items()]
    
    return "OK bat:{}mV motors:{} sensors:{}".format(
        battery,
        ",".join(motor_list) if motor_list else "none",
        ",".join(sensor_list) if sensor_list else "none"
    )


def cmd_help(args):
    """help - Show available commands."""
    cmds = "beep,speak,sound,motor,stop,target,target2,reset,pos,sensor,eyes,display,status,help,quit"
    return "OK " + cmds


# Command dispatch table
COMMANDS = {
    "beep": cmd_beep,
    "speak": cmd_speak,
    "sound": cmd_sound,
    "motor": cmd_motor,
    "stop": cmd_stop,
    "target": cmd_target,
    "target2": cmd_target2,
    "reset": cmd_reset,
    "pos": cmd_pos,
    "sensor": cmd_sensor,
    "eyes": cmd_eyes,
    "display": cmd_display,
    "status": cmd_status,
    "help": cmd_help,
}


# =============================================================================
# Eye Drawing
# =============================================================================

def thick_line(x1, y1, x2, y2, thickness=3):
    """Draw a thick line by drawing multiple parallel lines."""
    for i in range(-thickness//2, thickness//2 + 1):
        ev3.screen.draw_line(x1, y1+i, x2, y2+i)
        ev3.screen.draw_line(x1+i, y1, x2+i, y2)


def thick_circle(cx, cy, r, thickness=3, fill=False):
    """Draw a thick circle by drawing multiple concentric circles."""
    if fill:
        ev3.screen.draw_circle(cx, cy, r, fill=True)
    else:
        for i in range(thickness):
            ev3.screen.draw_circle(cx, cy, r-i)
            ev3.screen.draw_circle(cx, cy, r+i)


def draw_eyes(expression):
    """Draw eye expression on EV3 display."""
    ev3.screen.clear()
    
    # Display is 178x128 pixels
    # Draw two eyes centered
    cx1, cx2 = 50, 128  # Eye centers
    cy = 64
    
    if expression == "happy":
        # Happy: ^ ^ shaped eyes (thick)
        thick_line(cx1-20, cy+15, cx1, cy-15, 4)
        thick_line(cx1, cy-15, cx1+20, cy+15, 4)
        thick_line(cx2-20, cy+15, cx2, cy-15, 4)
        thick_line(cx2, cy-15, cx2+20, cy+15, 4)
    
    elif expression == "sad":
        # Sad: curved down eyebrows, half-closed eyes
        thick_circle(cx1, cy, 20, 3)
        thick_circle(cx2, cy, 20, 3)
        thick_line(cx1-25, cy-30, cx1+25, cy-18, 3)
        thick_line(cx2-25, cy-18, cx2+25, cy-30, 3)
    
    elif expression == "angry":
        # Angry: V shaped eyebrows
        thick_circle(cx1, cy, 20, 3)
        thick_circle(cx2, cy, 20, 3)
        thick_line(cx1-25, cy-35, cx1+15, cy-18, 4)
        thick_line(cx2-15, cy-18, cx2+25, cy-35, 4)
    
    elif expression == "surprised":
        # Surprised: wide open eyes
        thick_circle(cx1, cy, 30, 3)
        thick_circle(cx2, cy, 30, 3)
        ev3.screen.draw_circle(cx1, cy, 12, fill=True)
        ev3.screen.draw_circle(cx2, cy, 12, fill=True)
    
    elif expression == "sleepy":
        # Sleepy: horizontal lines (thick)
        thick_line(cx1-25, cy, cx1+25, cy, 5)
        thick_line(cx2-25, cy, cx2+25, cy, 5)
    
    elif expression == "wink":
        # Wink: one open, one closed
        thick_circle(cx1, cy, 20, 3)
        thick_line(cx2-20, cy, cx2+20, cy, 5)
    
    elif expression == "love":
        # Love: heart shaped eyes
        # Draw hearts using two circles and a triangle
        for cx in [cx1, cx2]:
            # Two overlapping circles for top of heart
            ev3.screen.draw_circle(cx-10, cy-8, 12, fill=True)
            ev3.screen.draw_circle(cx+10, cy-8, 12, fill=True)
            # Triangle for bottom of heart
            for i in range(25):
                ev3.screen.draw_line(cx-22+i, cy, cx, cy+25)
                ev3.screen.draw_line(cx+22-i, cy, cx, cy+25)
    
    elif expression == "off":
        # Off: blank screen (already cleared)
        pass
    
    else:  # neutral
        # Neutral: simple circles (thick)
        thick_circle(cx1, cy, 20, 3)
        thick_circle(cx2, cy, 20, 3)


# =============================================================================
# Main Loop
# =============================================================================

def process_single_command(parts):
    """Process a single command (already split into parts)."""
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    
    if cmd == "quit" or cmd == "exit":
        return "QUIT"
    
    if cmd in COMMANDS:
        try:
            return COMMANDS[cmd](args)
        except Exception as e:
            return "ERR: {}".format(e)
    else:
        return "ERR: unknown command: {}".format(cmd)


def process_command(line):
    """Process a command line and return response. Supports batch mode."""
    line = line.strip()
    if not line:
        return None
    
    # Batch mode: "|cmd1 arg|cmd2 arg|cmd3" - pipe prefix = batch, minimal latency
    if line[0] == "|":
        batch_cmds = line[1:].split("|")
        errors = []
        last_result = None
        for batch_cmd in batch_cmds:
            batch_cmd = batch_cmd.strip()
            if batch_cmd:
                parts = batch_cmd.split()
                result = process_single_command(parts)
                if result:
                    last_result = result
                    if result.startswith("ERR") or result.startswith("FAIL"):
                        errors.append(result)
                    if result == "QUIT":
                        return "QUIT"
        # Return errors, or last meaningful result (with position info)
        if errors:
            return ";".join(errors)
        elif last_result and ("moved" in last_result or "already@" in last_result or "FAIL" in last_result):
            return last_result  # Return target2 result with position info
        else:
            return "OK batch:{}".format(len(batch_cmds))
    
    parts = line.split()
    return process_single_command(parts)


def run_stdin_mode():
    """Run daemon accepting commands from stdin (USB Serial)."""
    print("READY")
    
    while True:
        # Check for back button to quit
        if Button.CENTER in ev3.buttons.pressed():
            print("QUIT:back_button")
            break
        
        try:
            # Read command from stdin
            line = sys.stdin.readline()
            if not line:
                break
            
            response = process_command(line)
            if response == "QUIT":
                break
            if response:
                print(response)
        
        except EOFError:
            break
        except Exception as e:
            print("ERR: {}".format(e))


def run_tcp_mode():
    """Run daemon accepting commands from TCP socket (WiFi)."""
    if not SOCKET_AVAILABLE:
        print("Socket not available, falling back to stdin")
        return run_stdin_mode()
    
    # MicroPython-compatible socket setup
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # setsockopt with bytes value for MicroPython compatibility
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, b'\x01')
    except (TypeError, OSError):
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except:
            pass  # Skip if not supported
    
    # Bind using getaddrinfo for MicroPython compatibility
    try:
        addr_info = socket.getaddrinfo("0.0.0.0", TCP_PORT)[0][-1]
        server.bind(addr_info)
    except:
        server.bind(("0.0.0.0", TCP_PORT))
    
    server.listen(1)
    
    # Use setblocking instead of settimeout for better compatibility
    server.setblocking(False)
    
    ev3.screen.clear()
    ev3.screen.print("TCP Daemon")
    ev3.screen.print("Port: {}".format(TCP_PORT))
    ev3.screen.print("Waiting...")
    
    print("READY tcp:{}".format(TCP_PORT))
    
    client = None
    
    while True:
        # Check for back button
        if Button.CENTER in ev3.buttons.pressed():
            print("QUIT:back_button")
            break
        
        # Accept new connection
        if client is None:
            try:
                client, addr = server.accept()
                client.setblocking(False)
                ev3.screen.clear()
                ev3.screen.print("Connected!")
                ev3.screen.print(str(addr[0]))
                client.send(b"READY\n")
            except OSError:
                wait(10)  # Small delay when no connection
                continue
        
        # Read from client
        try:
            data = client.recv(1024)
            if not data:
                client.close()
                client = None
                ev3.screen.clear()
                ev3.screen.print("Disconnected")
                ev3.screen.print("Waiting...")
                continue
            
            for line in data.decode().split("\n"):
                response = process_command(line)
                if response == "QUIT":
                    client.send(b"QUIT\n")
                    client.close()
                    server.close()
                    return
                if response:
                    client.send((response + "\n").encode())
        
        except OSError:
            wait(10)  # Small delay when no data
            continue
    
    if client:
        client.close()
    server.close()


def run_hybrid_mode():
    """Run daemon accepting commands from both stdin and TCP."""
    if not SOCKET_AVAILABLE:
        return run_stdin_mode()
    
    # Set up TCP server (MicroPython-compatible)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # setsockopt with bytes value for MicroPython compatibility
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, b'\x01')
    except (TypeError, OSError):
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except:
            pass
    
    # Bind using getaddrinfo for MicroPython compatibility
    try:
        addr_info = socket.getaddrinfo("0.0.0.0", TCP_PORT)[0][-1]
        server.bind(addr_info)
    except:
        server.bind(("0.0.0.0", TCP_PORT))
    
    server.listen(1)
    server.setblocking(False)
    
    ev3.screen.clear()
    ev3.screen.print("Hybrid Daemon")
    ev3.screen.print("TCP: {}".format(TCP_PORT))
    ev3.screen.print("USB: stdin")
    
    print("READY hybrid tcp:{} usb:stdin".format(TCP_PORT))
    
    tcp_client = None
    
    while True:
        # Check for back button
        if Button.CENTER in ev3.buttons.pressed():
            print("QUIT:back_button")
            break
        
        # Check stdin (USB) - use try/except for MicroPython compatibility
        try:
            # Try select if available
            if select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline()
                if line:
                    response = process_command(line)
                    if response == "QUIT":
                        break
                    if response:
                        print(response)
        except:
            pass  # select might not work in all MicroPython environments
        
        # Accept TCP connection
        if tcp_client is None:
            try:
                tcp_client, addr = server.accept()
                tcp_client.setblocking(False)
                tcp_client.send(b"READY\n")
            except OSError:
                pass  # No connection waiting
        
        # Read from TCP client
        if tcp_client:
            try:
                data = tcp_client.recv(1024)
                if not data:
                    tcp_client.close()
                    tcp_client = None
                else:
                    for line in data.decode().split("\n"):
                        response = process_command(line)
                        if response == "QUIT":
                            tcp_client.send(b"QUIT\n")
                            tcp_client.close()
                            tcp_client = None
                            break
                        if response:
                            tcp_client.send((response + "\n").encode())
            except:
                pass
        
        wait(10)  # Small delay to prevent busy-waiting
    
    if tcp_client:
        tcp_client.close()
    server.close()


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point."""
    # Initialize hardware
    init_motors()
    init_sensors()
    
    # Show startup message
    ev3.screen.clear()
    ev3.screen.print("Pybricks Daemon")
    ev3.screen.print("Motors: {}".format(list(motors.keys())))
    ev3.speaker.beep(frequency=880, duration=100)
    
    # Choose mode based on configuration
    if USE_TCP and SOCKET_AVAILABLE:
        run_hybrid_mode()
    else:
        run_stdin_mode()
    
    # Cleanup
    for motor in motors.values():
        try:
            motor.stop()
        except:
            pass
    
    ev3.screen.clear()
    ev3.screen.print("Daemon stopped")
    ev3.speaker.beep(frequency=440, duration=100)


if __name__ == "__main__":
    main()

