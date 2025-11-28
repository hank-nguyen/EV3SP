#!/usr/bin/env python3
"""
Collaborate Test EV3 Daemon
---------------------------
Minimal EV3 daemon for collaboration tests. Device-level actions only.
No project-specific logic.

Commands:
    bark, beep, speak <text>
    display <pattern>  (happy, sad, neutral, heart, clear)
    status, stop, quit
"""

import sys
import time
import json
import subprocess
import select

from ev3dev2.sound import Sound
from ev3dev2.display import Display
from ev3dev2.button import Button
from PIL import Image, ImageDraw

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

# ==============================================================================
# Display Patterns
# ==============================================================================

def draw_pattern(pattern="neutral"):
    """Draw simple patterns on EV3 display."""
    img = Image.new("1", (178, 128), color=0)
    draw = ImageDraw.Draw(img)
    
    cx1, cx2 = 45, 133
    cy = 64
    
    if pattern == "happy":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.arc([cx1-15, cy-15, cx1+15, cy+15], 0, 180, fill=0)
        draw.arc([cx2-15, cy-15, cx2+15, cy+15], 0, 180, fill=0)
    
    elif pattern == "sad":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.arc([cx1-15, cy+5, cx1+15, cy+25], 180, 360, fill=0)
        draw.arc([cx2-15, cy+5, cx2+15, cy+25], 180, 360, fill=0)
    
    elif pattern == "heart":
        cx, cy = 89, 64
        draw.ellipse([cx-30, cy-20, cx, cy+10], fill=1)
        draw.ellipse([cx, cy-20, cx+30, cy+10], fill=1)
        draw.polygon([(cx-28, cy), (cx, cy+40), (cx+28, cy)], fill=1)
    
    elif pattern == "neutral":
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-10, cy-10, cx1+10, cy+10], fill=0)
        draw.ellipse([cx2-10, cy-10, cx2+10, cy+10], fill=0)
    
    elif pattern == "clear":
        pass  # All black
    
    lcd.image.paste(img, (0, 0))
    lcd.update()


PATTERNS = ["happy", "sad", "heart", "neutral", "clear"]

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
# Actions
# ==============================================================================

def bark():
    """Quick woof sound using beeps (faster than TTS)."""
    draw_pattern("happy")
    # Fast bark using beeps instead of slow TTS
    sound.beep(args="-f 400 -l 100")
    sound.beep(args="-f 300 -l 150")
    return "OK"


def bark_tts():
    """Woof sound using text-to-speech (slower but realistic)."""
    draw_pattern("happy")
    sound.speak("woof")
    return "OK"


def beep():
    """Simple beep."""
    sound.beep()
    return "OK"


def speak(text):
    """Speak text."""
    sound.speak(text)
    return "OK"


def status():
    """Get detailed hardware status: battery, connection info."""
    lines = []
    
    # Battery voltage
    try:
        with open("/sys/class/power_supply/lego-ev3-battery/voltage_now") as f:
            voltage_uv = int(f.read().strip())
            voltage = round(voltage_uv / 1000000, 2)
            status_str = "OK" if voltage >= 7.5 else ("LOW" if voltage >= 7.0 else "CRITICAL")
            lines.append(f"Battery: {voltage}V ({status_str})")
    except:
        lines.append("Battery: N/A")
    
    lines.append("Mode: collaborate_test daemon")
    lines.append("Actions: bark, beep, display, speak")
    
    return " | ".join(lines)


def stop():
    """Stop all sounds."""
    return "OK"


ACTIONS = {
    "bark": bark,
    "woof": bark,
    "bark_tts": bark_tts,  # Slower but realistic TTS bark
    "beep": beep,
    "status": status,
    "stop": stop,
}


# ==============================================================================
# Main Loop
# ==============================================================================

if __name__ == "__main__":
    try:
        stop_brickman()
        draw_pattern("neutral")
        
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        
        running = True
        while running:
            try:
                if buttons.backspace:
                    sys.stdout.write("QUIT: back button\n")
                    sys.stdout.flush()
                    break
                
                readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                
                if not readable:
                    continue
                
                line = sys.stdin.readline()
                if not line:
                    break
                
                cmd = line.strip().lower()
                
                if cmd in ("quit", "exit"):
                    break
                
                # Handle display command
                if cmd.startswith("display "):
                    pattern = cmd[8:].strip()
                    if pattern in PATTERNS:
                        draw_pattern(pattern)
                        sys.stdout.write("OK: " + pattern + "\n")
                    else:
                        sys.stdout.write("patterns: " + ",".join(PATTERNS) + "\n")
                    sys.stdout.flush()
                    continue
                
                # Handle speak command
                if cmd.startswith("speak "):
                    text = cmd[6:].strip()
                    speak(text)
                    sys.stdout.write("OK\n")
                    sys.stdout.flush()
                    continue
                
                # Direct pattern command
                if cmd in PATTERNS:
                    draw_pattern(cmd)
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
                break
            except Exception as e:
                try:
                    sys.stdout.write("ERR: " + str(e) + "\n")
                    sys.stdout.flush()
                except:
                    break
    
    finally:
        try:
            stop()
        except:
            pass
        start_brickman()

