#!/usr/bin/env python3
"""
EV3 Daemon Base
---------------
Reusable daemon framework for EV3 robots.
Runs on EV3 brick, accepts commands via stdin, controls motors/sensors/display.

Python 3.4+ compatible (no f-strings).

Usage on EV3:
    python3 ev3_daemon.py

Features:
    - Motor control (Large/Medium motors on ports A-D)
    - Sensor reading (Touch, Color, Ultrasonic, Gyro on ports S1-S4)
    - Display with eye expressions
    - Sound (beep, speak)
    - Stops brickman for display control
    - Low-latency stdin command interface
    - Back button to quit daemon
"""

import sys
import time
import json
import select
import subprocess

# ev3dev2 imports
from ev3dev2.motor import LargeMotor, MediumMotor, OUTPUT_A, OUTPUT_B, OUTPUT_C, OUTPUT_D
from ev3dev2.sensor.lego import TouchSensor, ColorSensor, UltrasonicSensor, GyroSensor
from ev3dev2.sensor import INPUT_1, INPUT_2, INPUT_3, INPUT_4
from ev3dev2.sound import Sound
from ev3dev2.display import Display
from ev3dev2.button import Button

# PIL for drawing eyes
from PIL import Image, ImageDraw

# ==============================================================================
# Configuration - Override these for your robot
# ==============================================================================

# Motor port assignments (set to None if not used)
MOTOR_CONFIG = {
    "left_leg": {"port": OUTPUT_D, "type": "large"},
    "right_leg": {"port": OUTPUT_A, "type": "large"},
    "head": {"port": OUTPUT_C, "type": "medium"},
}

# Sensor port assignments
SENSOR_CONFIG = {
    "touch": {"port": INPUT_1, "type": "touch"},
    "color": {"port": INPUT_4, "type": "color"},
}

# Sudo password for stopping brickman
SUDO_PASSWORD = "maker"

# ==============================================================================
# Hardware Initialization
# ==============================================================================

sound = Sound()
lcd = Display()
buttons = Button()
motors = {}
sensors = {}


def init_hardware():
    """Initialize motors and sensors based on config."""
    global motors, sensors
    
    # Initialize motors
    for name, cfg in MOTOR_CONFIG.items():
        try:
            if cfg["type"] == "large":
                motors[name] = LargeMotor(cfg["port"])
            elif cfg["type"] == "medium":
                motors[name] = MediumMotor(cfg["port"])
            debug("Motor " + name + " OK")
        except Exception as e:
            debug("Motor " + name + " error: " + str(e))
    
    # Initialize sensors
    for name, cfg in SENSOR_CONFIG.items():
        try:
            if cfg["type"] == "touch":
                sensors[name] = TouchSensor(cfg["port"])
            elif cfg["type"] == "color":
                sensors[name] = ColorSensor(cfg["port"])
            elif cfg["type"] == "ultrasonic":
                sensors[name] = UltrasonicSensor(cfg["port"])
            elif cfg["type"] == "gyro":
                sensors[name] = GyroSensor(cfg["port"])
            debug("Sensor " + name + " OK")
        except Exception as e:
            debug("Sensor " + name + " error: " + str(e))


def debug(msg):
    """Print debug message to stderr."""
    sys.stderr.write("[daemon] " + msg + "\n")
    sys.stderr.flush()


# ==============================================================================
# Display - Eye Expressions
# ==============================================================================

def draw_eyes(style="neutral"):
    """Draw eye expression on EV3 screen."""
    img = Image.new("1", (178, 128), color=0)
    draw = ImageDraw.Draw(img)
    
    cx1, cx2 = 45, 133  # eye centers
    cy = 64
    
    if style == "neutral":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-10, cy-10, cx1+10, cy+10], fill=0)
        draw.ellipse([cx2-10, cy-10, cx2+10, cy+10], fill=0)
    
    elif style == "happy":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.arc([cx1-15, cy-15, cx1+15, cy+15], 0, 180, fill=0)
        draw.arc([cx2-15, cy-15, cx2+15, cy+15], 0, 180, fill=0)
        draw.arc([cx1-14, cy-14, cx1+14, cy+14], 0, 180, fill=0)
        draw.arc([cx2-14, cy-14, cx2+14, cy+14], 0, 180, fill=0)
    
    elif style == "angry":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-8, cy-3, cx1+12, cy+17], fill=0)
        draw.ellipse([cx2-12, cy-3, cx2+8, cy+17], fill=0)
        draw.polygon([(cx1-20, cy-30), (cx1+15, cy-20), (cx1+15, cy-16), (cx1-20, cy-26)], fill=0)
        draw.polygon([(cx2+20, cy-30), (cx2-15, cy-20), (cx2-15, cy-16), (cx2+20, cy-26)], fill=0)
    
    elif style == "sleepy":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.rectangle([cx1-26, cy-26, cx1+26, cy-5], fill=0)
        draw.rectangle([cx2-26, cy-26, cx2+26, cy-5], fill=0)
        draw.ellipse([cx1-6, cy, cx1+6, cy+12], fill=0)
        draw.ellipse([cx2-6, cy, cx2+6, cy+12], fill=0)
    
    elif style == "surprised":
        draw.ellipse([cx1-30, cy-30, cx1+30, cy+30], fill=1)
        draw.ellipse([cx2-30, cy-30, cx2+30, cy+30], fill=1)
        draw.ellipse([cx1-15, cy-15, cx1+15, cy+15], fill=0)
        draw.ellipse([cx2-15, cy-15, cx2+15, cy+15], fill=0)
        draw.ellipse([cx1-12, cy-12, cx1-4, cy-4], fill=1)
        draw.ellipse([cx2-12, cy-12, cx2-4, cy-4], fill=1)
    
    elif style == "love":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-12, cy-10, cx1, cy+2], fill=0)
        draw.ellipse([cx1, cy-10, cx1+12, cy+2], fill=0)
        draw.polygon([(cx1-10, cy-2), (cx1, cy+12), (cx1+10, cy-2)], fill=0)
        draw.ellipse([cx2-12, cy-10, cx2, cy+2], fill=0)
        draw.ellipse([cx2, cy-10, cx2+12, cy+2], fill=0)
        draw.polygon([(cx2-10, cy-2), (cx2, cy+12), (cx2+10, cy-2)], fill=0)
    
    elif style == "wink":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-10, cy-10, cx1+10, cy+10], fill=0)
        draw.rectangle([cx2-18, cy-2, cx2+18, cy+2], fill=0)
    
    elif style == "off":
        pass
    
    else:  # default neutral
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-10, cy-10, cx1+10, cy+10], fill=0)
        draw.ellipse([cx2-10, cy-10, cx2+10, cy+10], fill=0)
    
    lcd.image.paste(img, (0, 0))
    lcd.update()


EYE_STYLES = ["neutral", "happy", "angry", "sleepy", "surprised", "love", "wink", "off"]


# ==============================================================================
# System Control
# ==============================================================================

def stop_brickman():
    """Stop brickman to take control of display."""
    import subprocess
    try:
        cmd = "echo " + SUDO_PASSWORD + " | sudo -S systemctl stop brickman 2>/dev/null"
        subprocess.call(cmd, shell=True)
        time.sleep(0.5)
    except:
        pass


def start_brickman():
    """Restart brickman."""
    import subprocess
    try:
        cmd = "echo " + SUDO_PASSWORD + " | sudo -S systemctl start brickman 2>/dev/null"
        subprocess.call(cmd, shell=True)
    except:
        pass


# ==============================================================================
# Motor Actions
# ==============================================================================

def motor_on(name, speed):
    """Turn motor on at speed."""
    if name in motors:
        motors[name].on(speed=speed)
        return "OK"
    return "ERR: motor " + name

def motor_off(name, brake=False):
    """Turn motor off."""
    if name in motors:
        motors[name].off(brake=brake)
        return "OK"
    return "ERR: motor " + name

def motor_run_degrees(name, speed, degrees, block=True):
    """Run motor for degrees."""
    if name in motors:
        motors[name].on_for_degrees(speed=speed, degrees=degrees, block=block)
        return "OK"
    return "ERR: motor " + name

def motor_position(name):
    """Get motor position."""
    if name in motors:
        return motors[name].position
    return 0

def stop_all_motors():
    """Stop all motors."""
    for m in motors.values():
        try:
            m.off()
        except:
            pass
    return "OK"


# ==============================================================================
# Sensor Reading
# ==============================================================================

def read_sensor(name):
    """Read sensor value."""
    if name not in sensors:
        return None
    s = sensors[name]
    try:
        if hasattr(s, 'is_pressed'):
            return s.is_pressed
        elif hasattr(s, 'color_name'):
            return s.color_name
        elif hasattr(s, 'distance_centimeters'):
            return s.distance_centimeters
        elif hasattr(s, 'angle'):
            return s.angle
        else:
            return s.value()
    except:
        return None


# ==============================================================================
# Built-in Actions (override in subclass for custom robot)
# ==============================================================================

def action_status():
    """Return current status."""
    result = {"m": {}, "s": {}}
    for name in motors:
        try:
            result["m"][name[:1]] = motors[name].position
        except:
            pass
    for name in sensors:
        try:
            result["s"][name[:1]] = read_sensor(name)
        except:
            pass
    return json.dumps(result)

def action_stop():
    """Stop all motors."""
    return stop_all_motors()

def action_beep():
    """Make beep sound."""
    sound.beep()
    return "OK"

def action_speak(text="hello"):
    """Speak text."""
    sound.speak(text)
    return "OK"


# Base actions available
ACTIONS = {
    "status": action_status,
    "stop": action_stop,
    "beep": action_beep,
}


# ==============================================================================
# Command Processing
# ==============================================================================

def process_command(cmd):
    """Process a command string. Override to add custom commands."""
    cmd = cmd.strip().lower()
    
    # Eyes command (e.g., "eyes happy")
    if cmd.startswith("eyes "):
        style = cmd[5:].strip()
        if style in EYE_STYLES:
            draw_eyes(style)
            return "OK: " + style
        return "styles: " + ",".join(EYE_STYLES)
    
    # Direct eye style command (e.g., just "happy", "angry")
    if cmd in EYE_STYLES:
        draw_eyes(cmd)
        return "OK: " + cmd
    
    # Speak command
    if cmd.startswith("speak "):
        text = cmd[6:]
        sound.speak(text)
        return "OK"
    
    # Check built-in actions
    if cmd in ACTIONS:
        return ACTIONS[cmd]()
    
    return "ERR: " + cmd


def check_back_button():
    """Check if back button is pressed. Returns True if pressed."""
    return buttons.backspace


def run_daemon(custom_actions=None, on_start=None, on_stop=None, check_interval=0.1):
    """
    Main daemon loop.
    
    Args:
        custom_actions: dict of additional {name: function} actions
        on_start: function to call on startup
        on_stop: function to call on shutdown
        check_interval: how often to check buttons (seconds)
    """
    global ACTIONS
    
    if custom_actions:
        ACTIONS.update(custom_actions)
    
    # Stop brickman for display control
    stop_brickman()
    
    # Initialize hardware
    init_hardware()
    
    # Custom startup
    if on_start:
        on_start()
    else:
        draw_eyes("neutral")
    
    # Signal ready
    sys.stdout.write("READY\n")
    sys.stdout.flush()
    
    # Main loop with button checking
    running = True
    while running:
        try:
            # Check for back button press (quit)
            if check_back_button():
                sys.stdout.write("QUIT: back button\n")
                sys.stdout.flush()
                draw_eyes("sleepy")
                break
            
            # Use select to check stdin with timeout (non-blocking)
            readable, _, _ = select.select([sys.stdin], [], [], check_interval)
            
            if not readable:
                continue
            
            line = sys.stdin.readline()
            if not line:
                break
            
            cmd = line.strip()
            if cmd.lower() in ("quit", "exit"):
                draw_eyes("sleepy")
                break
            
            result = process_command(cmd)
            sys.stdout.write(str(result) + "\n")
            sys.stdout.flush()
            
        except Exception as e:
            sys.stdout.write("ERR: " + str(e) + "\n")
            sys.stdout.flush()
    
    # Cleanup
    stop_all_motors()
    if on_stop:
        on_stop()
    start_brickman()


# ==============================================================================
# Main - Run as standalone daemon
# ==============================================================================

if __name__ == "__main__":
    run_daemon()

