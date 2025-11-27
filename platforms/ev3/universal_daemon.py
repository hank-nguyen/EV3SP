#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EV3 Universal Daemon
--------------------
Generic daemon that supports all Orchestra shell commands.

Runs on EV3 (ev3dev), accepts commands via stdin, responds via stdout.

NOTE: EV3 runs Python 3.4 - NO f-strings, use .format() or %

Supported commands:
- Sound: beep, bark, speak, melody
- Display: eyes, text, clear
- Motor: motor, stop
- Info: status, battery
- Control: quit

Protocol:
    Host -> EV3:  <command> [args...]
    EV3 -> Host:  OK [result]  or  ERR: message
"""

from __future__ import print_function  # Python 2/3 compatibility
import sys
import time
import subprocess

# ev3dev2 imports
try:
    from ev3dev2.motor import LargeMotor, MediumMotor, OUTPUT_A, OUTPUT_B, OUTPUT_C, OUTPUT_D
    from ev3dev2.sound import Sound
    from ev3dev2.display import Display
    from ev3dev2.led import Leds
    from ev3dev2.button import Button
    from ev3dev2.power import PowerSupply
except ImportError:
    print("ERR: ev3dev2 not available")
    sys.exit(1)

# Password for sudo commands (brickman control)
SUDO_PASSWORD = "maker"

# ============================================================
# INITIALIZATION
# ============================================================

sound = Sound()
display = Display()
leds = Leds()
button = Button()
power = PowerSupply()

# Motor port mapping
MOTOR_PORTS = {
    'A': OUTPUT_A,
    'B': OUTPUT_B,
    'C': OUTPUT_C,
    'D': OUTPUT_D,
}

motors = {}  # Lazy initialization

# ============================================================
# DISPLAY PATTERNS (EV3 screen: 178x128 pixels)
# ============================================================

def draw_eyes(style="happy"):
    """
    Draw eye patterns on EV3 display.
    
    EV3 LCD color scheme:
    - 'black' = pixels ON = visible (dark)
    - 'white' = pixels OFF = invisible (light background)
    - display.clear() = all white (light)
    """
    display.clear()
    
    # Screen dimensions: 178x128 pixels
    # Screen center and eye positions
    cx, cy = 89, 64  # Center of screen
    lx, ly = 50, 64   # Left eye center
    rx, ry = 128, 64  # Right eye center
    
    if style == "happy":
        # Happy eyes - filled circles with smile below
        display.draw.ellipse((lx-20, ly-20, lx+20, ly+20), fill='black')
        display.draw.ellipse((rx-20, ry-20, rx+20, ry+20), fill='black')
        # Smile arcs below eyes
        display.draw.arc((lx-15, ly+10, lx+15, ly+35), 0, 180, fill='black')
        display.draw.arc((rx-15, ry+10, rx+15, ry+35), 0, 180, fill='black')
    
    elif style == "sad":
        # Sad eyes - filled circles with frown
        display.draw.ellipse((lx-20, ly-15, lx+20, ly+15), fill='black')
        display.draw.ellipse((rx-20, ry-15, rx+20, ry+15), fill='black')
        # Sad eyebrows slanting down
        display.draw.polygon([(lx-20, ly-25), (lx+15, ly-35), (lx+15, ly-30), (lx-20, ly-20)], fill='black')
        display.draw.polygon([(rx-15, ry-35), (rx+20, ry-25), (rx+20, ry-20), (rx-15, ry-30)], fill='black')
    
    elif style == "angry":
        # Angry eyes - rectangles with angry eyebrows
        display.draw.rectangle((lx-20, ly-10, lx+20, ly+10), fill='black')
        display.draw.rectangle((rx-20, ry-10, rx+20, ry+10), fill='black')
        # Angry V eyebrows
        display.draw.polygon([(lx-25, ly-20), (lx+20, ly-35), (lx+20, ly-28), (lx-25, ly-13)], fill='black')
        display.draw.polygon([(rx-20, ry-35), (rx+25, ry-20), (rx+25, ry-13), (rx-20, ry-28)], fill='black')
    
    elif style == "surprised":
        # Surprised eyes - big circles with small pupils
        display.draw.ellipse((lx-25, ly-25, lx+25, ly+25), fill='black')
        display.draw.ellipse((lx-8, ly-8, lx+8, ly+8), fill='white')  # White pupil hole
        display.draw.ellipse((rx-25, ry-25, rx+25, ry+25), fill='black')
        display.draw.ellipse((rx-8, ry-8, rx+8, ry+8), fill='white')  # White pupil hole
    
    elif style == "heart":
        # Heart shape in center
        # Two circles for top bumps
        display.draw.ellipse((cx-28, cy-25, cx-3, cy), fill='black')
        display.draw.ellipse((cx+3, cy-25, cx+28, cy), fill='black')
        # Triangle for bottom point
        display.draw.polygon([(cx-28, cy-10), (cx+28, cy-10), (cx, cy+30)], fill='black')
    
    elif style == "neutral":
        # Neutral - simple filled rectangles
        display.draw.rectangle((lx-20, ly-12, lx+20, ly+12), fill='black')
        display.draw.rectangle((rx-20, ry-12, rx+20, ry+12), fill='black')
    
    elif style == "sleeping":
        # Sleeping - horizontal lines (thick)
        display.draw.rectangle((lx-25, ly-4, lx+25, ly+4), fill='black')
        display.draw.rectangle((rx-25, ry-4, rx+25, ry+4), fill='black')
    
    elif style == "check":
        # Checkmark in center - thick
        display.draw.polygon([
            (cx-35, cy), (cx-10, cy+25), (cx+40, cy-30),
            (cx+40, cy-20), (cx-10, cy+35), (cx-35, cy+10)
        ], fill='black')
    
    elif style == "x":
        # X mark in center
        display.draw.polygon([(cx-30, cy-30), (cx-20, cy-30), (cx+30, cy+20), (cx+30, cy+30), (cx+20, cy+30), (cx-30, cy-20)], fill='black')
        display.draw.polygon([(cx+20, cy-30), (cx+30, cy-30), (cx+30, cy-20), (cx-20, cy+30), (cx-30, cy+30), (cx-30, cy+20)], fill='black')
    
    elif style == "clear":
        # Just clear, no drawing
        pass
    
    elif style == "test":
        # Test pattern - border and text
        display.draw.rectangle((5, 5, 172, 122), fill='black')
        display.draw.rectangle((15, 15, 162, 112), fill='white')
        display.draw.text((55, 55), "TEST OK", fill='black')
    
    else:
        # Unknown style - show text in center
        display.draw.rectangle((15, 45, 162, 83), fill='black')
        display.draw.text((25, 55), str(style), fill='white')
    
    display.update()
    return "OK: {}".format(style)


def show_text(text):
    """Show text on display."""
    display.clear()
    display.draw.text((10, 50), str(text), fill='white')
    display.update()
    return "OK"


# ============================================================
# SOUND FUNCTIONS
# ============================================================

def play_tone(freq, duration_ms):
    """Play a tone using ev3dev2's tone() method."""
    # tone() takes list of (frequency, duration_ms, delay_ms) tuples
    sound.tone([(freq, duration_ms, 0)])


def do_beep(args):
    """Play a beep. Args: [freq/pitch] [duration]"""
    freq = 880
    duration = 200
    
    if len(args) >= 1:
        # Handle pitch names
        pitch = args[0].lower()
        if pitch == "high":
            freq = 880
        elif pitch == "med" or pitch == "medium":
            freq = 440
        elif pitch == "low":
            freq = 220
        elif pitch == "c":
            freq = 523
        elif pitch == "d":
            freq = 587
        elif pitch == "e":
            freq = 659
        elif pitch == "f":
            freq = 698
        elif pitch == "g":
            freq = 784
        elif pitch == "a":
            freq = 880
        elif pitch == "b":
            freq = 988
        else:
            try:
                freq = int(pitch)
            except ValueError:
                freq = 880
    
    if len(args) >= 2:
        try:
            duration = int(args[1])
        except ValueError:
            pass
    
    play_tone(freq, duration)
    return "OK freq={} dur={}".format(freq, duration)


def do_bark(args):
    """Play bark sound (quick beeps)."""
    draw_eyes("happy")
    play_tone(880, 100)
    time.sleep(0.05)
    play_tone(700, 150)
    return "OK"


def do_speak(args):
    """Text-to-speech. Args: <text>"""
    text = " ".join(args) if args else "Hello"
    sound.speak(text)
    return "OK"


def do_melody(args):
    """Play a melody. Args: [name]"""
    name = args[0].lower() if args else "happy"
    
    melodies = {
        "happy": [(523, 200), (659, 200), (784, 400)],  # C-E-G
        "sad": [(784, 200), (659, 200), (523, 400)],    # G-E-C
        "alert": [(880, 100), (880, 100), (880, 100)],
        "success": [(523, 150), (659, 150), (784, 150), (1047, 300)],
    }
    
    notes = melodies.get(name, melodies["happy"])
    
    # Play all notes using tone() - can pass entire sequence
    tone_sequence = [(freq, dur, 50) for freq, dur in notes]  # 50ms gap between notes
    sound.tone(tone_sequence)
    
    return "OK"


# ============================================================
# MOTOR FUNCTIONS
# ============================================================

def get_motor(port):
    """Get or create motor for port."""
    port = port.upper()
    if port not in motors:
        try:
            motors[port] = LargeMotor(MOTOR_PORTS[port])
        except Exception:
            try:
                motors[port] = MediumMotor(MOTOR_PORTS[port])
            except Exception:
                return None
    return motors.get(port)


def do_motor(args):
    """Run motor. Args: <port> [speed] [duration_ms]"""
    if not args:
        return "ERR: Usage: motor <port> [speed] [duration]"
    
    port = args[0].upper()
    speed = 50
    duration = 0
    
    if len(args) >= 2:
        try:
            speed = int(args[1])
        except ValueError:
            pass
    
    if len(args) >= 3:
        try:
            duration = int(args[2])
        except ValueError:
            pass
    
    m = get_motor(port)
    if not m:
        return "ERR: Motor not found on port " + port
    
    if duration > 0:
        m.on_for_seconds(speed, duration / 1000.0)
    else:
        m.on(speed)
    
    return "OK"


def do_stop(args):
    """Stop all motors."""
    for m in motors.values():
        try:
            m.off()
        except Exception:
            pass
    return "OK"


# ============================================================
# SENSOR FUNCTIONS
# ============================================================

# Sensor cache (lazy initialization)
sensors = {}

def get_sensor(port_num):
    """Get sensor on port (1-4)."""
    if port_num not in sensors:
        try:
            # Try different sensor types
            from ev3dev2.sensor.lego import TouchSensor, ColorSensor, UltrasonicSensor, GyroSensor, InfraredSensor
            from ev3dev2.sensor import INPUT_1, INPUT_2, INPUT_3, INPUT_4
            
            input_ports = {1: INPUT_1, 2: INPUT_2, 3: INPUT_3, 4: INPUT_4}
            port = input_ports.get(port_num)
            if not port:
                return None
            
            # Try each sensor type
            for sensor_class in [TouchSensor, ColorSensor, UltrasonicSensor, GyroSensor, InfraredSensor]:
                try:
                    sensors[port_num] = sensor_class(port)
                    return sensors[port_num]
                except Exception:
                    continue
            return None
        except Exception:
            return None
    return sensors.get(port_num)


def read_sensor_value(port_num):
    """Read sensor value and return (type, value) tuple."""
    s = get_sensor(port_num)
    if not s:
        return None, None
    
    try:
        driver = s.driver_name
        
        if "touch" in driver:
            return "touch", s.is_pressed
        elif "color" in driver:
            # Return color name and RGB
            colors = {0: "none", 1: "black", 2: "blue", 3: "green", 
                     4: "yellow", 5: "red", 6: "white", 7: "brown"}
            color_id = s.color
            return "color", colors.get(color_id, str(color_id))
        elif "ultrasonic" in driver or "us" in driver:
            return "dist", s.distance_centimeters
        elif "gyro" in driver:
            return "gyro", s.angle
        elif "infrared" in driver or "ir" in driver:
            return "ir", s.proximity
        else:
            return driver, s.value()
    except Exception:
        return "unknown", None


# ============================================================
# STATUS FUNCTIONS
# ============================================================

def do_status(args):
    """Get comprehensive device status including motor/sensor values."""
    parts = []
    
    # Battery
    try:
        voltage = power.measured_voltage / 1000000.0
        parts.append("bat:{:.1f}V".format(voltage))
    except Exception:
        pass
    
    # Motors - show position and speed for each
    motor_info = []
    for port in "ABCD":
        m = get_motor(port)
        if m:
            try:
                pos = m.position
                spd = m.speed
                motor_info.append("{}:p{}s{}".format(port, pos, spd))
            except Exception:
                motor_info.append("{}:err".format(port))
    if motor_info:
        parts.append("M[" + " ".join(motor_info) + "]")
    
    # Sensors - show type and value for each
    sensor_info = []
    for port_num in range(1, 5):
        sensor_type, value = read_sensor_value(port_num)
        if sensor_type:
            if value is not None:
                sensor_info.append("S{}:{}={}".format(port_num, sensor_type, value))
            else:
                sensor_info.append("S{}:{}".format(port_num, sensor_type))
    if sensor_info:
        parts.append("S[" + " ".join(sensor_info) + "]")
    
    return " ".join(parts) if parts else "OK"


def do_battery(args):
    """Get battery voltage."""
    try:
        voltage = power.measured_voltage / 1000000.0
        return "{:.2f}V".format(voltage)
    except Exception:
        return "ERR: Cannot read battery"


def do_motors(args):
    """Get detailed motor status."""
    parts = []
    for port in "ABCD":
        m = get_motor(port)
        if m:
            try:
                parts.append("{}: pos={} speed={} duty={}".format(
                    port, m.position, m.speed, m.duty_cycle
                ))
            except Exception as e:
                parts.append("{}: error={}".format(port, str(e)))
    return "\n".join(parts) if parts else "No motors connected"


def do_sensors(args):
    """Get detailed sensor status."""
    parts = []
    for port_num in range(1, 5):
        sensor_type, value = read_sensor_value(port_num)
        if sensor_type:
            parts.append("S{}: {}={}".format(port_num, sensor_type, value))
    return "\n".join(parts) if parts else "No sensors connected"


# ============================================================
# DISPLAY COMMANDS
# ============================================================

def do_eyes(args):
    """Show eyes pattern. Args: [style]"""
    style = args[0].lower() if args else "happy"
    return draw_eyes(style)


def do_display(args):
    """Show pattern (alias for eyes). Args: [style]"""
    return do_eyes(args)


def do_text(args):
    """Show text on display. Args: <text>"""
    text = " ".join(args) if args else "Hi"
    return show_text(text)


def do_clear(args):
    """Clear the display."""
    display.clear()
    display.update()
    return "OK"


# ============================================================
# BRICKMAN CONTROL
# ============================================================

def stop_brickman():
    """Stop brickman to free the display."""
    try:
        proc = subprocess.Popen(
            ["sudo", "-S", "systemctl", "stop", "brickman"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        proc.communicate(input=(SUDO_PASSWORD + "\n").encode())
    except Exception:
        pass


def start_brickman():
    """Start brickman (restore menu)."""
    try:
        proc = subprocess.Popen(
            ["sudo", "-S", "systemctl", "start", "brickman"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        proc.communicate(input=(SUDO_PASSWORD + "\n").encode())
    except Exception:
        pass


# ============================================================
# COMMAND DISPATCHER
# ============================================================

COMMANDS = {
    # Sound
    "beep": do_beep,
    "bark": do_bark,
    "woof": do_bark,
    "speak": do_speak,
    "say": do_speak,
    "melody": do_melody,
    
    # Display
    "eyes": do_eyes,
    "display": do_display,
    "text": do_text,
    "clear": do_clear,
    
    # Motor
    "motor": do_motor,
    "stop": do_stop,
    
    # Info
    "status": do_status,
    "battery": do_battery,
    "bat": do_battery,
    "motors": do_motors,
    "sensors": do_sensors,
}


def process_command(line):
    """Process a command line and return response."""
    parts = line.strip().split()
    if not parts:
        return "OK"
    
    cmd = parts[0].lower()
    args = parts[1:]
    
    if cmd in ("quit", "exit"):
        return "QUIT"
    
    if cmd in COMMANDS:
        try:
            result = COMMANDS[cmd](args)
            return result
        except Exception as e:
            return "ERR: " + str(e)
    else:
        return "ERR: Unknown command: " + cmd


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    """Main daemon loop."""
    # Stop brickman to take over display
    stop_brickman()
    
    # Initialize display
    draw_eyes("neutral")
    
    # Signal ready
    print("READY")
    sys.stdout.flush()
    
    try:
        while True:
            try:
                # Check for back button (quit)
                if button.backspace:
                    print("QUIT: Back button pressed")
                    sys.stdout.flush()
                    break
                
                # Read command
                line = sys.stdin.readline()
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Process command
                response = process_command(line)
                
                if response == "QUIT":
                    print("QUIT: Requested")
                    sys.stdout.flush()
                    break
                
                print(response)
                sys.stdout.flush()
                
            except EOFError:
                break
            except Exception as e:
                print("ERR: " + str(e))
                sys.stdout.flush()
    
    finally:
        # Cleanup
        do_stop([])
        display.clear()
        display.update()
        start_brickman()


if __name__ == "__main__":
    main()
