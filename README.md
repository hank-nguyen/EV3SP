# LEGO Robotics Orchestra

Unified control framework for multiple LEGO robots. **Platform-agnostic** - control EV3s and Spike Primes through a single interface with synchronized, low-latency commands.

## ⚡ MicroPython Interface (Default for EV3)

EV3 uses **Pybricks MicroPython** by default with **1-15ms latency** (10x faster than legacy SSH):

```python
from platforms.ev3 import EV3MicroPython

async with EV3MicroPython() as ev3:
    await ev3.beep(880, 200)  # ~2-5ms via USB!
```

See `platforms/ev3/README.md` for setup.

## Key Concepts

- **Orchestra/Conductor**: Platform-agnostic layer controlling any device
- **Devices**: Hardware platforms (EV3, Spike Prime) with specific interfaces
- **Projects**: Device-specific behaviors (e.g., "puppy" uses EV3 motors)
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
│  projects/puppy/configs/actions.yaml │     │  Generic commands: │
│  ┌────────────────────┐              │     │  - target2 D A -55 │
│  │ standup:           │              │     │  - motor D 100 500 │
│  │   - eyes neutral   │──── TCP ────►│  - eyes happy      │
│  │   - target2 D A -55│     USB      │  - beep 440 200    │
│  └────────────────────┘              │     │  - sound dog_bark  │
│                                      │     │                    │
│  platforms/ev3/action_adapter.py     │     │  No project logic! │
│  (loads YAML, translates actions)    │     │                    │
└──────────────────────────────────────┘     └────────────────────┘
```

**Benefits**:
- Define actions in YAML - no code changes
- Daemon stays generic and reusable
- Add new projects without touching daemon code
- Actions auto-reload when YAML file changes

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              HOST                                   │
├─────────────────────────────────────────────────────────────────────┤
│   platforms/                       (Device-Specific Implementations)│
│   ├── ev3/                                                          │
│   │   ├── ev3_micropython.py       EV3MicroPython (USB/WiFi) ⚡     │
│   │   ├── pybricks_daemon.py       Generic daemon (Pybricks)        │
│   │   ├── action_adapter.py        YAML action translator          │
│   │   └── ev3_interface.py         Legacy SSH (fallback)            │
│   └── spike_prime/                 ✓ IMPLEMENTED                    │
│       ├── sp_interface.py          SpikeInterface (BLE)             │
│       └── sp_fast.py               SpikeFastInterface (low-latency) │
│                                                                     │
│   projects/                        (Device-Specific Projects)       │
│   └── puppy/                       Requires EV3 hardware            │
│       ├── puppy.py                 Host controller + flow shell     │
│       ├── configs/actions.yaml     Action definitions (YAML)        │
│       └── puppy_daemon.py          Legacy ev3dev daemon             │
└─────────────────────────────────────────────────────────────────────┘
                          │ USB Serial / WiFi TCP / BLE
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          DEVICES                                    │
├─────────────────────────────────────────────────────────────────────┤
│   EV3 Brick (Pybricks)             Spike Prime Hub (BLE)            │
│   ├── pybricks_daemon.py           ├── Pre-uploaded programs        │
│   ├── Motors, sensors, display     ├── Light matrix                 │
│   └── ~1-15ms latency ⚡           └── ~10-50ms latency             │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### EV3 Puppy (Interactive Shell)

```bash
# Connect via USB (auto-detect)
python projects/puppy/puppy.py action=flow

# Connect via WiFi
python projects/puppy/puppy.py action=flow connection.host=192.168.68.114
```

**Inside the flow shell:**
```
[Puppy] ● > calibrate     # Set current position as 0°
[Puppy] ● > standup       # Move legs to standing position
[Puppy] ● > sitdown       # Move legs to sitting position
[Puppy] ● > bark          # Woof!
[Puppy] ● > hop           # Jump
[Puppy] ● > pos           # Show motor positions
[Puppy] ● > help          # Show all commands
[Puppy] ● > quit
```

### Spike Prime

```bash
python platforms/spike_prime/sp_fast.py flow
> beep_high
> happy
> quit
```

## Configuration

### Puppy Actions (`projects/puppy/configs/actions.yaml`)

```yaml
actions:
  sitdown:
    description: "Sit down"
    steps:
      - [eyes happy, 0]
      - [target2 D A 0 150, 1500]  # Both legs to 0°

  standup:
    description: "Stand up"
    steps:
      - [eyes neutral, 0]
      - [target2 D A -55 100, 1800]  # Both legs to -55°

  bark:
    steps:
      - [eyes surprised, 0]
      - [sound dog_bark, 0]
```

### Connection (`projects/puppy/configs/connection/remote.yaml`)

```yaml
host: 192.168.68.114
port: 9000
transport: micropython
```

## Daemon Commands

| Command | Description | Example |
|---------|-------------|---------|
| `beep <freq> <ms>` | Play tone | `beep 440 200` |
| `sound <name>` | Play sound file | `sound dog_bark` |
| `motor <port> <speed> [ms]` | Run motor | `motor D 100 500` |
| `target <port> <angle> [speed]` | Move to angle | `target D -55 150` |
| `target2 <p1> <p2> <angle> [speed]` | Move 2 motors | `target2 D A -55 100` |
| `stop [port]` | Stop motor(s) | `stop` |
| `eyes <style>` | Set expression | `eyes happy` |
| `pos [port]` | Get motor angle | `pos` |
| `reset [port]` | Reset angle to 0 | `reset` |
| `status` | Battery & motors | `status` |

## Latency

| Device | Method | Latency |
|--------|--------|---------|
| **EV3** | **MicroPython (USB)** | **~1-5ms** ⚡ |
| **EV3** | **MicroPython (WiFi)** | **~5-15ms** ⚡ |
| EV3 | Legacy SSH | ~30-50ms |
| Spike Prime | Fast (fire-and-forget) | ~10-30ms |

## Project Structure

```
EV3SP/
├── main.py                    # Entry point
├── orchestra.py               # Multi-device orchestrator (WIP)
├── requirements.txt
│
├── core/                      # Platform-agnostic abstractions
│   ├── interface.py           # RobotInterface, DaemonSession
│   ├── project_shell.py       # Interactive shell framework
│   └── types.py               # Platform, RobotState
│
├── platforms/                 # Device-specific implementations
│   ├── ev3/
│   │   ├── ev3_micropython.py # ⚡ USB/WiFi (1-15ms)
│   │   ├── pybricks_daemon.py # Generic daemon
│   │   ├── action_adapter.py  # YAML action loader
│   │   └── ev3_interface.py   # Legacy SSH
│   └── spike_prime/
│       ├── sp_interface.py    # SpikeInterface (BLE)
│       └── sp_fast.py         # Fast interface
│
├── protocols/                 # Reference documentation
│   ├── spike-prime-protocol/  # Official LEGO BLE protocol
│   └── pybricks-protocol/     # Pybricks examples
│
└── projects/
    └── puppy/                 # EV3 puppy robot
        ├── puppy.py           # Host controller
        ├── configs/
        │   └── actions.yaml   # Action definitions
        └── puppy_daemon.py    # Legacy ev3dev daemon
```

## Platforms

### [EV3](platforms/ev3/README.md)
- **Default: Pybricks MicroPython** (USB/WiFi TCP)
- Ultra-low latency: **1-15ms** ⚡
- Position-aware motor control with verification
- Display (eye expressions), sound, sensors

### [Spike Prime](platforms/spike_prime/README.md)
- BLE connection (App 3 firmware)
- Fast interface with pre-uploaded programs (~10-50ms)
- Display, sound, motors

## Roadmap

- [x] EV3 MicroPython interface ⚡ (1-15ms)
- [x] Position-aware motor commands (target, target2)
- [x] YAML action definitions with auto-reload
- [x] Spike Prime fast interface
- [x] Interactive flow shell
- [ ] Multi-device orchestra shell
- [ ] Time-synchronized commands
- [ ] Web UI
