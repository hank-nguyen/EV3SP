# EV3 Puppy Robot

Interactive puppy robot controller for LEGO MINDSTORMS EV3.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HOST                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   projects/puppy/              platforms/ev3/                       │
│   ├── puppy.py ──────────────► action_adapter.py                   │
│   └── configs/                      │                               │
│       └── actions.yaml ◄────────────┘ (loads YAML)                 │
│                                                                     │
│   User: "sitdown"  ──►  ActionAdapter  ──►  [eyes sleepy,          │
│                         (from YAML)          motor D -25,           │
│                                              motor A -25,           │
│                                              stop]                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │ WiFi TCP / USB Serial
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   EV3 (pybricks_daemon.py)                          │
├─────────────────────────────────────────────────────────────────────┤
│   Generic daemon: motor, beep, speak, eyes, stop, status, quit      │
│   No project-specific code - stays reusable!                        │
└─────────────────────────────────────────────────────────────────────┘
```

**Key insights**:
- Actions defined in YAML (`configs/actions.yaml`)
- ActionAdapter at platform level (`platforms/ev3/action_adapter.py`)
- Project code stays clean - no action sequences in `puppy.py`
- Daemon stays generic and reusable

## Hardware Setup

| Port | Device | Description |
|------|--------|-------------|
| A | Large Motor | Right leg |
| C | Medium Motor | Head (with gears) |
| D | Large Motor | Left leg |
| S1 | Touch Sensor | Petting detection |
| S4 | Color Sensor | Feeding detection |

## Quick Start

### 1. Start daemon on EV3
```bash
# SSH to EV3 and start daemon
ssh robot@<EV3_IP> "nohup brickrun ~/pybricks_daemon.py &"
```

### 2. Run from host
```bash
python puppy.py action=flow
```

## Flow Mode Commands

### Actions
| Command | Description |
|---------|-------------|
| `standup` | Stand up |
| `sitdown` | Sit down |
| `bark` | Say "woof woof" |
| `stretch` | Stretch legs |
| `hop` | Jump |
| `head_up` | Raise head |
| `head_down` | Lower head |
| `happy` | Happy dance with barks |
| `angry` | Growl and bark |
| `status` | Get motor/sensor status |
| `stop` | Stop all motors |

### Eye Expressions
| Command | Expression |
|---------|------------|
| `neutral` | Normal eyes 👁️ |
| `happy` | Curved smile (^_^) |
| `angry` | Slanted + eyebrows 😠 |
| `sleepy` | Half-closed 😴 |
| `surprised` | Wide eyes 😲 |
| `love` | Heart eyes ❤️ |
| `wink` | One eye closed 😉 |
| `off` | Screen off |

## Exit Methods

1. Type `quit` in flow mode
2. Press **back button** on EV3 brick
3. `Ctrl+C` on host

## Configuration

Edit `configs/connection/remote.yaml`:
```yaml
# MicroPython (recommended, ~5-15ms latency)
host: 192.168.68.114
transport: micropython
wifi_port: 9000

# Legacy SSH (~30-50ms latency)
# transport: ssh
# user: robot
# password: maker
```

## Action Translation

Actions are defined in `configs/actions.yaml` and loaded by the platform-level `ActionAdapter`:

```yaml
# configs/actions.yaml
actions:
  sitdown:
    description: "Sit down"
    steps:
      - [eyes sleepy, 0]
      - [motor D -25, 0]
      - [motor A -25, 800]
      - [stop, 0]
  
  bark:
    description: "Bark (woof woof)"
    steps:
      - [eyes surprised, 0]
      - [speak woof woof, 0]
```

**Adding new actions**: Just add entries to `configs/actions.yaml` - no code changes needed!

## Files

| File | Location | Description |
|------|----------|-------------|
| `puppy.py` | Host | Controller (uses platform-level adapter) |
| `configs/actions.yaml` | Host | Action definitions (YAML) |
| `configs/connection/` | Host | Connection settings |
| `pybricks_daemon.py` | EV3 | Generic daemon (from `platforms/ev3/`) |
| `puppy_daemon.py` | EV3 | Legacy ev3dev daemon (SSH mode) |

## Transport Modes

| Transport | Latency | Daemon | Config |
|-----------|---------|--------|--------|
| **MicroPython** | ~5-15ms | `pybricks_daemon.py` | `transport: micropython` |
| SSH (legacy) | ~30-50ms | `puppy_daemon.py` | `transport: ssh` |

