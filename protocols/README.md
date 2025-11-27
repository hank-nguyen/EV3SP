# Protocol Documentation

Reference documentation for communicating with LEGO robots.

**⚠️ ALWAYS check this folder before implementing new features!**

## Available Protocols

### [spike-prime-protocol/](spike-prime-protocol/README.md)

Official LEGO® Education SPIKE™ Prime BLE protocol (App 3 firmware).

**Use for:**
- SPIKE Prime Hub communication
- BLE GATT service interaction
- File upload / program execution
- ConsoleNotification (print signals)

**Key files:**
```
spike-prime-protocol/
├── docs/source/
│   ├── connect.rst      # BLE UUIDs, handshake
│   ├── encoding.rst     # COBS algorithm
│   └── messages.rst     # All message types
└── examples/python/
    ├── app.py           # ★ Complete working example
    ├── messages.py      # Message serialization
    └── cobs.py          # COBS encode/decode
```

### [pybricks-protocol/](pybricks-protocol/README.md)

Pybricks MicroPython examples for LEGO robots.

**Use for:**
- EV3 sound, display, buttons patterns
- Motor control (speed, position, stall detection)
- EV3-to-EV3 Bluetooth messaging
- Sensor reading patterns
- Data logging

**Key examples:**
```
pybricks-protocol/examples/
├── ev3/                    # ★ EV3 Brick examples
│   ├── getting_started/    # Motor + beep basics
│   ├── speaker_basics/     # Sound, notes, TTS
│   ├── screen_print/       # Text display
│   ├── screen_draw/        # Graphics drawing
│   ├── buttons/            # Button handling
│   ├── bluetooth_server/   # EV3-to-EV3 server
│   ├── bluetooth_client/   # EV3-to-EV3 client
│   ├── bluetooth_pc/       # ★ PC-EV3 messaging library
│   └── datalog/            # Data logging
│
└── pup/                    # Powered Up hubs
    ├── hub_primehub/       # Spike Prime display
    ├── motor/              # Motor control patterns
    └── hub_common/         # BLE broadcast/observe
```

## When to Reference

### Spike Prime (Stock Firmware)

| Task | Protocol | Key File |
|------|----------|----------|
| BLE connect | spike-prime-protocol | `docs/source/connect.rst` |
| Upload program | spike-prime-protocol | `examples/python/app.py` |
| COBS encoding | spike-prime-protocol | `examples/python/cobs.py` |
| Receive print() | spike-prime-protocol | `messages.py` → `ConsoleNotification` |

### EV3 (ev3dev)

| Task | Protocol | Key File |
|------|----------|----------|
| Sound/beep | pybricks-protocol | `examples/ev3/speaker_basics/main.py` |
| Display text | pybricks-protocol | `examples/ev3/screen_print/main.py` |
| Draw graphics | pybricks-protocol | `examples/ev3/screen_draw/main.py` |
| Button handling | pybricks-protocol | `examples/ev3/buttons/main.py` |
| Motor control | pybricks-protocol | `examples/ev3/getting_started/main.py` |
| EV3-to-EV3 BT | pybricks-protocol | `examples/ev3/bluetooth_*/` |
| PC-to-EV3 BT | pybricks-protocol | `examples/ev3/bluetooth_pc/` |
| Data logging | pybricks-protocol | `examples/ev3/datalog/main.py` |

### Motor Patterns (Any Hub)

| Task | Protocol | Key File |
|------|----------|----------|
| Run at speed | pybricks-protocol | `examples/pup/motor/motor_action_basic.py` |
| Position control | pybricks-protocol | `examples/pup/motor/motor_absolute.py` |
| Stall detection | pybricks-protocol | `examples/pup/motor/motor_until_stalled.py` |
| Multiple motors | pybricks-protocol | `examples/pup/motor/motor_init_multiple.py` |

## Our Implementation

| Platform | Our Code | Uses Protocol |
|----------|----------|---------------|
| Spike Prime | `platforms/spike_prime/sp_interface.py` | spike-prime-protocol |
| Spike Prime | `platforms/spike_prime/sp_fast.py` | spike-prime-protocol |
| EV3 | `platforms/ev3/ev3_daemon.py` | pybricks-protocol patterns (adapted for ev3dev2) |
| EV3 | `projects/puppy/puppy_daemon.py` | pybricks-protocol patterns |

## API Comparison

### Sound

| API | Example |
|-----|---------|
| **Pybricks** | `ev3.speaker.beep(1000, 500)` |
| **ev3dev2** (our EV3) | `sound.beep(1000, 500)` |
| **Stock Spike** (our SP) | `await sound.beep(1000, 500)` |

### Display

| API | Example |
|-----|---------|
| **Pybricks EV3** | `ev3.screen.print("Hi")` |
| **ev3dev2** (our EV3) | `display.text_pixels("Hi", x=0, y=0)` |
| **Stock Spike** (our SP) | `await light_matrix.write("Hi")` |

### Buttons

| API | Example |
|-----|---------|
| **Pybricks** | `Button.CENTER in ev3.buttons.pressed()` |
| **ev3dev2** (our EV3) | `Button.enter in button.buttons_pressed` |

## Notes

- **spike-prime-protocol**: Stock LEGO firmware (App 3) - we use this
- **pybricks-protocol**: Pybricks firmware (requires flash) - we use patterns only
- EV3 uses **ev3dev2** library, but patterns from Pybricks examples still apply
- Spike Prime uses **stock firmware** with LEGO MicroPython API

