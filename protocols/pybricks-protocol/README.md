# Pybricks Protocol & Examples

Reference examples for Pybricks MicroPython on LEGO robots. These examples work with **Pybricks firmware** (alternative to stock LEGO firmware).

**⚠️ Reference these examples for motor/sensor patterns, Bluetooth communication, and display APIs!**

## Quick Reference

### EV3 Imports

```python
#!/usr/bin/env pybricks-micropython
from pybricks.hubs import EV3Brick
from pybricks.ev3devices import Motor, TouchSensor, ColorSensor
from pybricks.parameters import Port, Button
from pybricks.tools import wait, StopWatch, DataLog
from pybricks.media.ev3dev import SoundFile, Font
```

### Spike Prime / Powered Up Imports

```python
from pybricks.hubs import PrimeHub  # or TechnicHub, CityHub, etc.
from pybricks.pupdevices import Motor
from pybricks.parameters import Port
from pybricks.tools import wait
```

## File Structure

```
protocols/pybricks-protocol/examples/
├── ev3/                    # ★ EV3 Brick examples
│   ├── getting_started/    # Basic motor + beep
│   ├── speaker_basics/     # Sound, notes, TTS
│   ├── screen_print/       # Text display
│   ├── screen_draw/        # Graphics drawing
│   ├── buttons/            # Button handling
│   ├── bluetooth_server/   # EV3-to-EV3 server
│   ├── bluetooth_client/   # EV3-to-EV3 client
│   ├── bluetooth_pc/       # EV3-to-PC messaging
│   └── datalog/            # Data logging
│
├── pup/                    # Powered Up hubs (Spike Prime, etc.)
│   ├── hub_primehub/       # Spike Prime display
│   ├── hub_common/         # BLE broadcast/observe
│   ├── motor/              # Motor control patterns
│   ├── sensor_*/           # Various sensors
│   └── robotics/           # DriveBase, car control
│
└── micropython/            # General MicroPython utilities
```

## EV3 Examples

### Sound (`examples/ev3/speaker_basics/`)

```python
from pybricks.hubs import EV3Brick
from pybricks.media.ev3dev import SoundFile

ev3 = EV3Brick()

# Simple beep
ev3.speaker.beep()

# Custom frequency and duration
ev3.speaker.beep(frequency=1000, duration=500)

# Play notes (Twinkle Twinkle)
notes = ["C4/4", "C4/4", "G4/4", "G4/4", "A4/4", "A4/4", "G4/2"]
ev3.speaker.play_notes(notes)

# Play sound file
ev3.speaker.play_file(SoundFile.HELLO)

# Text-to-speech
ev3.speaker.say("Hello, I am EV3")

# Change voice (Danish female)
ev3.speaker.set_speech_options(voice="da+f5")
```

### Display (`examples/ev3/screen_print/`, `screen_draw/`)

```python
from pybricks.hubs import EV3Brick
from pybricks.media.ev3dev import Font

ev3 = EV3Brick()

# Print text
ev3.screen.print("Hello!")

# Custom fonts
tiny = Font(size=6)
big = Font(size=24, bold=True)
ev3.screen.set_font(big)
ev3.screen.print("BIG TEXT")

# Draw shapes
ev3.screen.draw_box(10, 10, 40, 40)           # Rectangle
ev3.screen.draw_box(10, 10, 40, 40, fill=True) # Filled
ev3.screen.draw_circle(50, 50, 20)             # Circle
ev3.screen.draw_line(0, 0, 100, 100)           # Line
```

### Buttons (`examples/ev3/buttons/`)

```python
from pybricks.hubs import EV3Brick
from pybricks.parameters import Button
from pybricks.tools import wait

ev3 = EV3Brick()

# Wait for any button
while not any(ev3.buttons.pressed()):
    wait(10)

# Check specific button
if Button.LEFT in ev3.buttons.pressed():
    print("Left pressed!")

# Wait for release
while any(ev3.buttons.pressed()):
    wait(10)
```

### Motors (`examples/ev3/getting_started/`)

```python
from pybricks.ev3devices import Motor
from pybricks.parameters import Port

motor = Motor(Port.B)

# Run at speed (deg/s)
motor.run(500)

# Run to target angle
motor.run_target(500, 90)  # 500 deg/s to 90°

# Run for time
motor.run_time(500, 2000)  # 500 deg/s for 2 seconds

# Stop
motor.stop()
```

### Bluetooth EV3-to-EV3 (`examples/ev3/bluetooth_server/`, `bluetooth_client/`)

**Server (start first):**
```python
from pybricks.messaging import BluetoothMailboxServer, TextMailbox

server = BluetoothMailboxServer()
mbox = TextMailbox("greeting", server)

print("waiting for connection...")
server.wait_for_connection()
print("connected!")

mbox.wait()
print(mbox.read())  # Receive message
mbox.send("hello back!")  # Send reply
```

**Client:**
```python
from pybricks.messaging import BluetoothMailboxClient, TextMailbox

client = BluetoothMailboxClient()
mbox = TextMailbox("greeting", client)

client.connect("ev3dev")  # Server's Bluetooth name
mbox.send("hello!")
mbox.wait()
print(mbox.read())  # Receive reply
```

### Bluetooth EV3-to-PC (`examples/ev3/bluetooth_pc/`)

Python library for PC-side EV3 Bluetooth communication:

```python
# On PC (using pybricks/messaging.py)
from pybricks.messaging import BluetoothMailboxClient, TextMailbox

client = BluetoothMailboxClient()
mbox = TextMailbox("commands", client)

client.connect("XX:XX:XX:XX:XX:XX")  # EV3 Bluetooth address
mbox.send("start")
```

### Data Logging (`examples/ev3/datalog/`)

```python
from pybricks.tools import DataLog, StopWatch
from pybricks.ev3devices import Motor
from pybricks.parameters import Port

motor = Motor(Port.B)
data = DataLog("time", "angle")
watch = StopWatch()

motor.run(500)
for i in range(10):
    data.log(watch.time(), motor.angle())
    wait(100)
```

## Powered Up / Spike Prime Examples

### Display Pixels (`examples/pup/hub_primehub/display_pixel.py`)

```python
from pybricks.hubs import PrimeHub
from pybricks.tools import wait

hub = PrimeHub()

# Turn on pixel (row, col)
hub.display.pixel(1, 2)        # Full brightness
hub.display.pixel(2, 4, 50)    # 50% brightness
hub.display.pixel(1, 2, 0)     # Turn off
```

### BLE Broadcast (`examples/pup/hub_common/ble_broadcast.py`)

```python
from pybricks.hubs import PrimeHub  # or ThisHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port

hub = PrimeHub(broadcast_channel=1)
motor = Motor(Port.A)

while True:
    angle = motor.angle()
    hub.ble.broadcast((angle,))  # Send to other hubs
    wait(100)
```

### Motor Control (`examples/pup/motor/`)

```python
from pybricks.pupdevices import Motor
from pybricks.parameters import Port

motor = Motor(Port.A)

# Speed control
motor.run(500)           # deg/s
motor.dc(50)             # 50% duty cycle
motor.stop()

# Position control
motor.run_time(500, 2000)     # Run for 2 seconds
motor.run_angle(500, 90)      # Run 90 degrees
motor.run_target(500, 0)      # Go to position 0
motor.run_until_stalled(500)  # Run until stalled

# Read state
angle = motor.angle()
speed = motor.speed()
```

## Key Patterns for Our Codebase

### EV3 Daemon Sound Pattern

```python
# Based on examples/ev3/speaker_basics/main.py
def bark():
    ev3.speaker.beep(880, 100)
    wait(50)
    ev3.speaker.beep(700, 150)

def speak(text):
    ev3.speaker.say(text)
```

### EV3 Display Pattern

```python
# Based on examples/ev3/screen_draw/main.py
def draw_eyes(expression):
    ev3.screen.clear()
    if expression == "happy":
        ev3.screen.draw_circle(40, 64, 20, fill=True)
        ev3.screen.draw_circle(138, 64, 20, fill=True)
    elif expression == "sad":
        # Draw sad eyes...
```

### EV3 Button Quit Pattern

```python
# Based on examples/ev3/buttons/main.py
from pybricks.parameters import Button

def check_quit():
    if Button.CENTER in ev3.buttons.pressed():
        return True
    return False

# In daemon loop:
while True:
    if check_quit():
        break
    # process commands...
```

### Bluetooth Mailbox Pattern

```python
# Based on examples/ev3/bluetooth_*/
# For hub-to-hub communication

# Mailbox types:
# - TextMailbox: strings
# - NumericMailbox: floats
# - LogicMailbox: booleans

# Pattern: mailbox name must match on both sides
mbox = TextMailbox("commands", connection)
mbox.send("action:bark")
mbox.wait()
response = mbox.read()
```

## Comparison with Our Implementation

| Pybricks Example | Our Code Location | Notes |
|------------------|-------------------|-------|
| `ev3/speaker_basics/` | `projects/puppy/puppy_daemon.py` | We use ev3dev2, similar API |
| `ev3/screen_draw/` | `projects/puppy/puppy_daemon.py` | Display patterns |
| `ev3/buttons/` | `projects/puppy/puppy_daemon.py` | Quit button handling |
| `ev3/bluetooth_*/` | Future: hub-to-hub sync | EV3 ↔ EV3 messaging |
| `pup/hub_primehub/` | Pybricks firmware only | Stock firmware uses different API |

## Notes

### Pybricks vs ev3dev2

Our EV3 code uses **ev3dev2** (stock ev3dev), not Pybricks:

| Pybricks | ev3dev2 (Our Code) |
|----------|-------------------|
| `from pybricks.hubs import EV3Brick` | `from ev3dev2.sound import Sound` |
| `ev3.speaker.beep()` | `sound.beep()` |
| `ev3.screen.print()` | `display.text_pixels()` |
| `Button.CENTER` | `Button.enter` |

### Pybricks vs Stock Spike Prime

For Spike Prime, we use **stock LEGO firmware**, not Pybricks:

| Pybricks | Stock Firmware (Our Code) |
|----------|--------------------------|
| `hub.display.pixel(1, 2)` | `light_matrix.set_pixel(1, 2, 100)` |
| `hub.speaker.beep()` | `await sound.beep(440, 500)` |
| `hub.ble.broadcast()` | Not available (use ConsoleNotification) |

### When to Use These Examples

- **Motor patterns**: Timing, stall detection, position control
- **Bluetooth patterns**: EV3-to-EV3 communication ideas
- **Display patterns**: Drawing, fonts, expressions
- **Sound patterns**: Notes, melodies, TTS

## References

- [Pybricks Documentation](https://docs.pybricks.com/)
- [ev3dev Documentation](https://www.ev3dev.org/)
- Our EV3 implementation: `platforms/ev3/`
- Our Spike Prime implementation: `platforms/spike_prime/`

