#!/usr/bin/env python3
"""
Puppy Robot Daemon
------------------
EV3 Puppy-specific daemon for motor/sensor control and display.
Standalone file - upload to EV3 and run directly.

Usage on EV3:
    python3 puppy_daemon.py

Commands via stdin:
    standup, sitdown, bark, stretch, hop
    head_up, head_down, happy, angry
    eyes <style>  (neutral, happy, angry, sleepy, surprised, love, wink, off)
    status, stop, quit
"""

import sys
import time
import json
import subprocess
import select

# Core ev3dev2 imports (always needed)
from ev3dev2.motor import LargeMotor, MediumMotor, OUTPUT_A, OUTPUT_C, OUTPUT_D
from ev3dev2.sound import Sound
from ev3dev2.display import Display
from ev3dev2.button import Button

# PIL for display drawing
from PIL import Image, ImageDraw

# Lazy-loaded (sensors are optional, only for status)
TouchSensor = None
ColorSensor = None

# ==============================================================================
# Configuration
# ==============================================================================

SUDO_PASSWORD = "maker"

# ==============================================================================
# Hardware
# ==============================================================================

sound = Sound()
lcd = Display()
buttons = Button()

# Motors
left_motor = None
right_motor = None
head_motor = None

# Sensors
touch_sensor = None
color_sensor = None


def init_hardware():
    """Initialize motors (fast). Sensors are lazy-loaded on first status call."""
    global left_motor, right_motor, head_motor
    
    try:
        left_motor = LargeMotor(OUTPUT_D)
    except Exception as e:
        sys.stderr.write("Left motor: " + str(e) + "\n")
    
    try:
        right_motor = LargeMotor(OUTPUT_A)
    except Exception as e:
        sys.stderr.write("Right motor: " + str(e) + "\n")
    
    try:
        head_motor = MediumMotor(OUTPUT_C)
    except Exception as e:
        sys.stderr.write("Head motor: " + str(e) + "\n")


def init_sensors():
    """Lazy-load sensors only when needed (status command)."""
    global touch_sensor, color_sensor, TouchSensor, ColorSensor
    
    # Lazy import sensor modules
    if TouchSensor is None:
        try:
            from ev3dev2.sensor.lego import TouchSensor as TS, ColorSensor as CS
            TouchSensor = TS
            ColorSensor = CS
        except ImportError:
            return
    
    # Initialize sensors (INPUT_1 = "in1", INPUT_4 = "in4")
    if touch_sensor is None:
        try:
            touch_sensor = TouchSensor("in1")
        except Exception as e:
            sys.stderr.write("Touch sensor: " + str(e) + "\n")
    
    if color_sensor is None:
        try:
            color_sensor = ColorSensor("in4")
        except Exception as e:
            sys.stderr.write("Color sensor: " + str(e) + "\n")


# ==============================================================================
# Display - Eyes
# ==============================================================================

def draw_eyes(style="neutral"):
    img = Image.new("1", (178, 128), color=0)
    draw = ImageDraw.Draw(img)
    
    cx1, cx2 = 45, 133
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
    
    else:
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
    try:
        subprocess.call("echo " + SUDO_PASSWORD + " | sudo -S systemctl stop brickman 2>/dev/null", shell=True)
        time.sleep(0.5)
    except:
        pass


def start_brickman():
    try:
        subprocess.call("echo " + SUDO_PASSWORD + " | sudo -S systemctl start brickman 2>/dev/null", shell=True)
    except:
        pass


# ==============================================================================
# Puppy Actions
# ==============================================================================

def standup():
    if not left_motor or not right_motor:
        return "ERR: motors"
    draw_eyes("neutral")
    left_motor.on_for_degrees(speed=80, degrees=50, block=False)
    right_motor.on_for_degrees(speed=80, degrees=50, block=True)
    time.sleep(0.3)
    left_motor.on_for_degrees(speed=60, degrees=60, block=False)
    right_motor.on_for_degrees(speed=60, degrees=60, block=True)
    time.sleep(0.3)
    left_motor.on_for_degrees(speed=40, degrees=70, block=False)
    right_motor.on_for_degrees(speed=40, degrees=70, block=True)
    return "OK"


def sitdown():
    if not left_motor or not right_motor:
        return "ERR: motors"
    draw_eyes("sleepy")
    left_motor.on(speed=-25)
    right_motor.on(speed=-25)
    time.sleep(0.8)
    left_motor.off()
    right_motor.off()
    return "OK"


def bark():
    draw_eyes("surprised")
    sound.speak("woof woof")
    return "OK"


def stretch():
    if not left_motor or not right_motor:
        return "ERR: motors"
    draw_eyes("sleepy")
    left_motor.on_for_degrees(speed=30, degrees=25, block=False)
    right_motor.on_for_degrees(speed=30, degrees=25, block=True)
    time.sleep(0.3)
    left_motor.on_for_degrees(speed=25, degrees=40, block=False)
    right_motor.on_for_degrees(speed=25, degrees=40, block=True)
    left_motor.on_for_degrees(speed=30, degrees=60, block=False)
    right_motor.on_for_degrees(speed=30, degrees=60, block=True)
    left_motor.on_for_degrees(speed=30, degrees=-60, block=False)
    right_motor.on_for_degrees(speed=30, degrees=-60, block=True)
    draw_eyes("neutral")
    return "OK"


def hop():
    if not left_motor or not right_motor:
        return "ERR: motors"
    draw_eyes("surprised")
    left_motor.on(speed=50)
    right_motor.on(speed=50)
    time.sleep(0.2)
    left_motor.off(brake=True)
    right_motor.off(brake=True)
    time.sleep(0.2)
    left_motor.on(speed=-25)
    right_motor.on(speed=-25)
    time.sleep(0.2)
    left_motor.off()
    right_motor.off()
    return "OK"


def head_up():
    draw_eyes("neutral")
    if head_motor:
        head_motor.on_for_degrees(speed=90, degrees=60)
        return "OK"
    return "ERR: head"


def head_down():
    draw_eyes("sleepy")
    if head_motor:
        head_motor.on_for_degrees(speed=90, degrees=-60)
        return "OK"
    return "ERR: head"


def happy():
    draw_eyes("love")
    sound.speak("woof woof")  # Longer phrase for TTS
    if left_motor and right_motor:
        left_motor.on(speed=50)
        right_motor.on(speed=50)
        time.sleep(0.2)
        left_motor.off(brake=True)
        right_motor.off(brake=True)
        time.sleep(0.2)
        left_motor.on(speed=-25)
        right_motor.on(speed=-25)
        time.sleep(0.2)
        left_motor.off()
        right_motor.off()
    draw_eyes("happy")
    sound.speak("happy happy")  # Longer phrase
    return "OK"


def angry():
    draw_eyes("angry")
    sound.speak("grrr grrr")  # Longer phrase for TTS
    if left_motor and right_motor:
        left_motor.on_for_degrees(speed=30, degrees=25, block=False)
        right_motor.on_for_degrees(speed=30, degrees=25, block=True)
        time.sleep(0.3)
        left_motor.on_for_degrees(speed=25, degrees=40, block=False)
        right_motor.on_for_degrees(speed=25, degrees=40, block=True)
    sound.speak("woof woof woof")  # Longer phrase
    return "OK"


def status():
    """Get detailed hardware status: battery, motors (port+position), sensors."""
    init_sensors()  # Lazy-load sensors only when status is requested
    
    lines = []
    
    # Battery voltage (read from sysfs)
    try:
        with open("/sys/class/power_supply/lego-ev3-battery/voltage_now") as f:
            voltage_uv = int(f.read().strip())
            voltage = round(voltage_uv / 1000000, 2)
            # Battery status indicator
            if voltage >= 7.5:
                status = "OK"
            elif voltage >= 7.0:
                status = "LOW"
            else:
                status = "CRITICAL"
            lines.append("Battery: {}V ({})".format(voltage, status))
    except:
        lines.append("Battery: N/A")
    
    # Motors with port info
    motors = []
    if left_motor:
        motors.append("Left(D): pos={}".format(left_motor.position))
    if right_motor:
        motors.append("Right(A): pos={}".format(right_motor.position))
    if head_motor:
        motors.append("Head(C): pos={}".format(head_motor.position))
    if motors:
        lines.append("Motors: " + ", ".join(motors))
    else:
        lines.append("Motors: None connected")
    
    # Sensors with port info
    sensors = []
    if touch_sensor:
        pressed = "PRESSED" if touch_sensor.is_pressed else "released"
        sensors.append("Touch(1): {}".format(pressed))
    if color_sensor:
        sensors.append("Color(4): {}".format(color_sensor.color_name))
    if sensors:
        lines.append("Sensors: " + ", ".join(sensors))
    else:
        lines.append("Sensors: None connected")
    
    return " | ".join(lines)


def stop():
    if left_motor:
        left_motor.off()
    if right_motor:
        right_motor.off()
    if head_motor:
        head_motor.off()
    return "OK"


# ==============================================================================
# Action Registry
# ==============================================================================

ACTIONS = {
    "standup": standup,
    "stand_up": standup,
    "sitdown": sitdown,
    "sit_down": sitdown,
    "bark": bark,
    "stretch": stretch,
    "hop": hop,
    "head_up": head_up,
    "head_down": head_down,
    "happy": happy,
    "angry": angry,
    "status": status,
    "stop": stop,
}


# ==============================================================================
# Main Loop
# ==============================================================================

if __name__ == "__main__":
    try:
        # Stop brickman for display control
        stop_brickman()
        
        # Initialize hardware
        init_hardware()
        
        # Show neutral eyes
        draw_eyes("neutral")
        
        # Signal ready
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        
        # Command loop with button checking
        running = True
        while running:
            try:
                # Check for back button press (escape/quit)
                if buttons.backspace:
                    sys.stdout.write("QUIT: back button\n")
                    sys.stdout.flush()
                    draw_eyes("sleepy")
                    break
                
                # Use select to check if stdin has data (non-blocking)
                readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                
                if not readable:
                    continue
                
                line = sys.stdin.readline()
                if not line:
                    # stdin closed (host disconnected)
                    break
                
                cmd = line.strip().lower()
                
                if cmd == "quit" or cmd == "exit":
                    draw_eyes("sleepy")
                    break
                
                # Handle eyes command (both "eyes happy" and just "happy")
                if cmd.startswith("eyes "):
                    style = cmd[5:].strip()
                    if style in EYE_STYLES:
                        draw_eyes(style)
                        sys.stdout.write("OK: " + style + "\n")
                    else:
                        sys.stdout.write("styles: " + ",".join(EYE_STYLES) + "\n")
                    sys.stdout.flush()
                    continue
                
                # Direct eye style command (e.g., just "neutral", "happy", etc.)
                if cmd in EYE_STYLES:
                    draw_eyes(cmd)
                    sys.stdout.write("OK: " + cmd + "\n")
                    sys.stdout.flush()
                    continue
                
                # Handle actions
                if cmd in ACTIONS:
                    result = ACTIONS[cmd]()
                    sys.stdout.write(str(result) + "\n")
                else:
                    sys.stdout.write("ERR: " + cmd + "\n")
                sys.stdout.flush()
                
            except IOError:
                # Pipe broken (host disconnected)
                break
            except Exception as e:
                try:
                    sys.stdout.write("ERR: " + str(e) + "\n")
                    sys.stdout.flush()
                except:
                    break
    
    finally:
        # ALWAYS cleanup and restart brickman, even on crash/disconnect
        try:
            stop()
        except:
            pass
        start_brickman()
