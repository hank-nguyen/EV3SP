# LEGO Robotics Orchestra

Unified control framework for multiple LEGO robots. **The Orchestra is platform-agnostic** - control EV3s and Spike Primes through a single interface with synchronized, low-latency commands.

## ⚡ New: MicroPython Interface (Default)

EV3 now uses **Pybricks MicroPython** by default with **1-15ms latency** (up to 10x faster than legacy SSH!):

```python
from platforms.ev3 import EV3MicroPython

async with EV3MicroPython() as ev3:
    await ev3.beep(880, 200)  # ~2-5ms via USB!
```

See `platforms/ev3/README.md` for setup instructions.

## Key Concepts

- **Orchestra/Conductor**: Platform-agnostic layer that controls any device
- **Devices**: Hardware platforms (EV3, Spike Prime) - each with specific interfaces
- **Projects**: Device-specific behaviors (e.g., "puppy" uses specific EV3 motors)
- **Action Translation**: Host translates project actions to generic daemon commands

```
Orchestra (agnostic) ──► EV3 device ──► puppy project
                    ──► Spike Prime ──► (built-in actions)
```

### Generic Daemon + Action Adapter

The EV3 daemon is **intentionally generic** - projects define actions in YAML:

```
┌──────────────────────────────────────┐     ┌────────────────────┐
│               HOST                   │     │   EV3 (daemon)     │
├──────────────────────────────────────┤     ├────────────────────┤
│                                      │     │                    │
│  projects/puppy/                     │     │  Generic commands: │
│  └── configs/actions.yaml            │     │  - motor D -25     │
│      ┌────────────────┐              │     │  - motor A -25     │
│      │ sitdown:       │              │     │  - eyes sleepy     │
│      │   - eyes sleepy│──── TCP ────►│  - stop            │
│      │   - motor D -25│     USB      │  - beep            │
│      │   - motor A -25│              │  - speak           │
│      │   - stop       │              │                    │
│      └────────────────┘              │     │  No project logic! │
│                                      │     │                    │
│  platforms/ev3/action_adapter.py     │     │                    │
│  (loads YAML, translates actions)    │     │                    │
└──────────────────────────────────────┘     └────────────────────┘
```

**Benefits**:
- Define actions in YAML - no code changes!
- Daemon stays generic and reusable
- Add new projects without touching daemon or adapter code

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              HOST                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   projects/collaborate_test/       (Platform-Agnostic)              │
│   └── collaborate_test.py          Controls ANY device uniformly    │
│       ├── parallel()               Send to all at once              │
│       └── sequence()               Choreographed timing             │
│                                                                     │
│   ─────────────────────────────────────────────────────────────     │
│                                                                     │
│   platforms/                       (Device-Specific Implementations)│
│   ├── ev3/                                                          │
│   │   ├── ev3_micropython.py       EV3MicroPython (USB/WiFi) ⚡     │
│   │   ├── pybricks_daemon.py       Pybricks daemon                  │
│   │   └── ev3_interface.py         Legacy SSH (fallback)            │
│   └── spike_prime/                 ✓ IMPLEMENTED                    │
│       ├── sp_interface.py          SpikeInterface (BLE)             │
│       └── sp_fast.py               SpikeFastInterface (low-latency) │
│                                                                     │
│   ─────────────────────────────────────────────────────────────     │
│                                                                     │
│   projects/                        (Device-Specific Projects)       │
│   └── puppy/                       Requires EV3 hardware            │
│       ├── puppy.py                 Host controller                  │
│       └── puppy_daemon.py          Device daemon                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          │ USB Serial / WiFi TCP / BLE
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          DEVICES                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   EV3 Brick (Pybricks)             Spike Prime Hub (BLE)            │
│   ├── pybricks_daemon.py           ├── Pre-uploaded programs        │
│   ├── Motors, sensors              ├── Light matrix                 │
│   └── ~1-15ms latency ⚡           └── ~10-50ms latency             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 🎼 Orchestra Interactive Shell (WIP)

```bash
# Interactive mode
python main.py collaborate_test

# Run specific tests
python main.py collaborate_test parallel
python main.py collaborate_test sync
python main.py collaborate_test seq
```

**Inside the shell:**
```
[ev3 sp] ⚡ ev3 beep
  ev3: OK (32ms)

[ev3 sp] ⚡ sp display heart  
  sp: OK (15ms)

[ev3 sp] ⚡ all status
  ev3: bat:7.8V motors:ABC (28ms)
  sp: connected, actions: 5 (12ms)

[ev3 sp] ⚡ help
  ... shows all available commands ...

[ev3 sp] ⚡ quit
```

### Collaborate Test Scripts

```bash
cd projects/collaborate_test

# Both devices at once: Spike beeps, EV3 barks
python test_beep_woof.py

# Synchronized (same time)
python test_beep_woof.py --sync

# Alternating sequence
python test_beep_woof.py --seq
```

### Single Device Control

```bash
# EV3 Puppy
python main.py puppy flow
> standup
> bark
> quit

# Spike Prime
python platforms/spike_prime/sp_fast.py flow
> beep_high
> happy
> quit
```

## Configuration

### Device Settings (`projects/collaborate_test/configs/devices.yaml`)

```yaml
devices:
  ev3:
    platform: ev3
    host: ev3dev.local
    user: robot
    password: maker

  spike:
    platform: spike_prime
    name: Avatar Karo
    address: E1BDF5C6-C666-4E77-A7E8-458FC0A9F809
```

### Project Mapping (`projects/collaborate_test/configs/config.yaml`)

```yaml
# Which project runs on which device
projects:
  ev3: puppy    # EV3 runs "puppy" project
  spike: null   # Spike uses built-in fast actions

latency_mode: fire  # "fire" (fast) or "ack" (reliable)
```

## Usage

### Orchestra API

```python
from conductor import Conductor

async with Conductor.from_config("configs/config.yaml") as conductor:
    # Parallel: both at same time (~50ms total)
    await conductor.parallel(
        ("spike", "beep_high"),
        ("ev3", "bark"),
    )
    
    # Sequence: alternating with delay
    await conductor.sequence(
        ("spike", "beep_high"),
        ("ev3", "bark"),
        ("spike", "beep_low"),
        delay_ms=200
    )
```

### Programmatic Setup

```python
conductor = Conductor(latency_mode="fire")
conductor.add_ev3("ev3", host="ev3dev.local", project="puppy")
conductor.add_spike("spike", address="E1BD...", hub_name="Avatar Karo")

async with conductor:
    await conductor.send("spike", "beep_high")
    await conductor.send("ev3", "bark")
```

## Latency

| Device | Method | Latency |
|--------|--------|---------|
| **EV3** | **MicroPython (USB)** | **~1-5ms** ⚡ |
| **EV3** | **MicroPython (WiFi)** | **~5-15ms** ⚡ |
| EV3 | Legacy SSH | ~30-50ms |
| Spike Prime | Fast (fire-and-forget) | ~10-30ms |
| **Parallel** | asyncio.gather | ~max(both) |

## Project Structure

```
EV3SP/
├── main.py                    # Entry point
├── README.md
├── requirements.txt
│
├── core/                      # ★ Platform-agnostic abstractions
│   ├── interface.py           # RobotInterface, DaemonSession
│   ├── collaboration.py       # SignalQueue, batched programs
│   ├── types.py               # Platform, RobotState
│   └── utils/                 # Graceful shutdown, etc.
│
├── platforms/                 # Device-specific implementations
│   ├── ev3/
│   │   ├── ev3_micropython.py # ⚡ EV3MicroPython (USB/WiFi, 1-15ms)
│   │   ├── pybricks_daemon.py # Daemon for Pybricks MicroPython
│   │   ├── ev3_interface.py   # Legacy SSH (30-50ms)
│   │   └── README.md
│   └── spike_prime/
│       ├── sp_interface.py    # SpikeInterface (BLE)
│       ├── sp_fast.py         # SpikeFastInterface (low-latency)
│       └── README.md
│
├── protocols/                 # ★ REFERENCE BEFORE CODING
│   ├── spike-prime-protocol/  # Official LEGO BLE protocol
│   │   ├── docs/source/       # Messages, encoding, UUIDs
│   │   └── examples/python/   # Working implementation
│   └── pybricks-protocol/     # Pybricks examples
│
└── projects/
    ├── collaborate_test/      # ★ Platform-agnostic controller
    │   ├── collaborate_test.py # Multi-device orchestrator
    │   ├── test_beep_woof.py  # Demo test
    │   └── configs/
    └── puppy/                 # EV3-specific project
        ├── puppy.py           # Host controller + PUPPY_ACTION_SEQUENCES
        └── puppy_daemon.py    # Legacy ev3dev daemon (SSH mode)
```

## Available Actions

### Spike Prime (via SpikeFastInterface)

| Action | Description |
|--------|-------------|
| `beep_high` | 880Hz beep |
| `beep_med` | 440Hz beep |
| `beep_low` | 220Hz beep |
| `happy` | Happy face |
| `sad` | Sad face |
| `heart` | Heart |
| `neutral` | Neutral face |
| `clear` | Clear display |

### EV3 (via puppy project)

| Action | Description |
|--------|-------------|
| `bark` | Woof sound |
| `standup` | Stand up |
| `sitdown` | Sit down |
| `happy` | Happy expression |
| `sad` | Sad expression |
| `status` | Get sensor data |

## Platforms

### [EV3](platforms/ev3/README.md) - LEGO MINDSTORMS EV3

- **Default: Pybricks MicroPython** (USB Serial / WiFi TCP)
- Ultra-low latency: **1-15ms** ⚡
- Display, sound, motors, sensors
- Legacy SSH mode available (30-50ms)

### [Spike Prime](platforms/spike_prime/README.md) - LEGO Spike Prime

- BLE connection (App 3 firmware)
- Fast interface with pre-uploaded programs (~10-50ms)
- Display, sound, motors

## Core Abstractions

### [core/](core/README.md) - Platform-Agnostic Layer

- `RobotInterface` - Base class for all platforms
- `DaemonSession` - Low-latency control via persistent connection
- `SignalQueue` - Cross-device synchronization
- `create_batched_program()` - Minimize Spike Prime melodies

## Protocol Documentation

### [protocols/](protocols/README.md) - Reference Before Coding!

**⚠️ Always check protocol docs before implementing new features!**

| Protocol | Use For |
|----------|---------|
| [spike-prime-protocol](protocols/spike-prime-protocol/README.md) | Spike Prime BLE, COBS, messages |
| [pybricks-protocol](protocols/pybricks-protocol/README.md) | EV3 sound, display, buttons, motors, Bluetooth |

Key references:
- **Spike BLE UUIDs**: `protocols/spike-prime-protocol/docs/source/connect.rst`
- **Spike Messages**: `protocols/spike-prime-protocol/docs/source/messages.rst`
- **Spike Example**: `protocols/spike-prime-protocol/examples/python/app.py`
- **EV3 Sound**: `protocols/pybricks-protocol/examples/ev3/speaker_basics/main.py`
- **EV3 Display**: `protocols/pybricks-protocol/examples/ev3/screen_draw/main.py`
- **EV3 Bluetooth**: `protocols/pybricks-protocol/examples/ev3/bluetooth_*/`

## Roadmap

- [x] EV3 platform implementation
- [x] Puppy robot project
- [x] Low-latency daemon protocol (EV3)
- [x] Display (eye expressions)
- [x] Button quit handling
- [x] **Spike Prime platform**
- [x] **Spike Prime fast interface** (~10-50ms)
- [x] **Orchestra multi-device control**
- [x] **EV3 MicroPython interface** ⚡ (~1-15ms, 10x faster!)
  - [x] USB Serial transport
  - [x] WiFi TCP transport
  - [x] Bluetooth RFCOMM transport
  - [x] Auto-detection (USB → WiFi → Bluetooth)
- [🚧] **Collaborate Test Interactive Shell** (WIP) - `python main.py collaborate_test`
  - [x] Unified command registry (`core/commands.py`)
  - [x] Tab completion & history
  - [x] EV3 universal daemon (`platforms/ev3/universal_daemon.py`)
  - [x] Multi-target commands (`ev3 beep`, `sp display`, `all status`)
  - [x] MicroPython transport support
  - [ ] Config file loading
  - [ ] Spike Prime sensor/motor status
- [ ] Time-synchronized commands
- [ ] Event system (cross-device sensors)
- [ ] Choreography API
- [ ] Web UI

---

## Future: Advanced Orchestra Features

### Time-Synchronized Commands

Send commands with future execution timestamp for precise choreography.

```python
# All devices execute at exactly the same moment
conductor.send_at(time.time() + 0.1, {
    "ev3": "bark",
    "spike": "beep_high"
})
# Requires NTP sync on all devices
```

### Event System

React to sensors across devices:

```python
@conductor.on("ev3.touch")
def on_pet():
    conductor.send("spike", "happy")
```

### Choreography

Script multi-robot sequences:

```python
conductor.choreograph([
    (0.0, "ev3", "standup"),
    (0.0, "spike", "happy"),
    (0.5, "ev3", "bark"),
    (0.7, "spike", "beep_high"),
    (1.0, "all", "neutral"),
])
```
