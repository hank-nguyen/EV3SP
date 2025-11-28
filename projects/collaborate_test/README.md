# Collaborate Test - Multi-Device Control

**Platform-agnostic controller** for multiple LEGO robots (EV3 + Spike Prime) with lowest latency.

## Quick Start

### Via main.py

```bash
# Interactive flow mode
python main.py collaborate_test

# Run specific tests
python main.py collaborate_test parallel  # SP beep + EV3 woof
python main.py collaborate_test sync      # 3 synchronized rounds
python main.py collaborate_test seq       # Alternating sequence
```

### Direct test scripts

```bash
cd projects/collaborate_test

# Parallel test: SP beep + EV3 woof at same time
python test_beep_woof.py

# Synchronized: beep+woof together, 3 times
python test_beep_woof.py --sync

# Sequential: alternating beep/woof
python test_beep_woof.py --seq
```

## Configuration

### Device Configuration (`configs/devices.yaml`)

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

### Project Mapping (`configs/config.yaml`)

```yaml
projects:
  ev3: collaborate_test  # EV3 runs collaborate_test daemon
  spike: null            # Spike uses built-in fast actions

latency_mode: ack
```

## Usage

### Programmatic

```python
from collaborate_test import Conductor

async with Conductor.from_config("configs/config.yaml") as conductor:
    # Parallel commands
    await conductor.parallel(
        ("spike", "beep_high"),
        ("ev3", "bark"),
    )
    
    # Sequence with delay
    await conductor.sequence(
        ("spike", "beep_high"),
        ("ev3", "bark"),
        ("spike", "beep_low"),
        delay_ms=200
    )
```

## Available Actions

### Spike Prime
| Action | Description |
|--------|-------------|
| `beep_high` | 880Hz beep |
| `beep_med` | 440Hz beep |
| `beep_low` | 220Hz beep |
| `happy` | Happy face |
| `sad` | Sad face |

### EV3
| Action | Description |
|--------|-------------|
| `bark` | Woof sound |
| `beep` | Simple beep |
| `display <pattern>` | happy, sad, neutral, heart, clear |

## Files

| File | Description |
|------|-------------|
| `collaborate_test.py` | Main controller (Conductor + Controller) |
| `collaborate_test_daemon.py` | EV3 daemon for device-level actions |
| `test_beep_woof.py` | Beep/woof demo tests |
| `configs/devices.yaml` | Device hardware configuration |
| `configs/config.yaml` | Main settings + project mapping |

