# EV3 Puppy Robot

Interactive puppy robot controller for LEGO MINDSTORMS EV3.

## Hardware Setup

| Port | Device | Description |
|------|--------|-------------|
| A | Large Motor | Right leg |
| C | Medium Motor | Head (with gears) |
| D | Large Motor | Left leg |
| S1 | Touch Sensor | Petting detection |
| S4 | Color Sensor | Feeding detection |

## Quick Start

```bash
cd projects/puppy
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
host: ev3dev.local
user: robot
password: maker
sudo_password: maker
```

## Files

| File | Location | Description |
|------|----------|-------------|
| `puppy.py` | Host | Controller with CLI |
| `puppy_daemon.py` | EV3 | Daemon (auto-uploaded) |
| `configs/` | Host | Hydra configuration |

