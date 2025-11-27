# Orchestra - Multi-Device Control

**Platform-agnostic controller** for multiple LEGO robots (EV3 + Spike Prime) with lowest latency.

## Key Concepts

The **Orchestra is platform-agnostic** - it provides a unified interface to control any device:

- **Conductor**: Single API to control EV3, Spike Prime, or any future device
- **Devices**: Hardware platforms (`ev3`, `spike`) with device-specific implementations
- **Projects**: Device-specific behaviors (e.g., `puppy` requires EV3 motors)

```
Conductor (agnostic) ──► EV3 device ──► puppy project (EV3-specific)
                    ──► Spike Prime ──► built-in fast actions
```

## Quick Start

```bash
cd projects/orchestra

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
# Devices are HARDWARE, not projects
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
# Which project runs on which device
projects:
  ev3: puppy           # EV3 runs the "puppy" project
  spike: null          # Spike uses built-in fast actions

latency_mode: fire     # "fire" or "ack"
```

## Latency

| Device | Method | Latency |
|--------|--------|---------|
| EV3 | Daemon session (SSH) | ~30-50ms |
| Spike Prime | Fast interface (fire-and-forget) | ~10-30ms |
| **Parallel total** | asyncio.gather | ~max(EV3, Spike) |

## Usage

### From Config

```python
from conductor import Conductor

async with Conductor.from_config("configs/config.yaml") as conductor:
    # Parallel commands (uses DEVICE names)
    await conductor.parallel(
        ("spike", "beep_high"),
        ("ev3", "bark"),        # "ev3" device running "puppy" project
    )
    
    # Sequence with delay
    await conductor.sequence(
        ("spike", "beep_high"),
        ("ev3", "bark"),
        ("spike", "beep_low"),
        delay_ms=200
    )
```

### Programmatic

```python
from conductor import Conductor

conductor = Conductor(latency_mode="fire")  # or "ack"
conductor.add_ev3("ev3", host="ev3dev.local", project="puppy")
conductor.add_spike("spike", address="E1BD...", hub_name="Avatar Karo")

async with conductor:
    await conductor.send("spike", "beep_high")
    await conductor.send("ev3", "bark")
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
| `heart` | Heart |
| `neutral` | Neutral face |
| `clear` | Clear display |

### EV3 (with Puppy project)

| Action | Description |
|--------|-------------|
| `bark` | Woof sound |
| `standup` | Stand up |
| `sitdown` | Sit down |
| `happy` | Happy expression |
| `sad` | Sad expression |
| `status` | Get sensor status |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         HOST                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Conductor                                                 │
│   ├── DeviceState["ev3"]    ─── EV3DaemonSession ───┐      │
│   │   └── project: "puppy"                          │      │
│   └── DeviceState["spike"]  ─── SpikeFastInterface ─┤      │
│                                                     │      │
│   parallel() ── asyncio.gather() ───────────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │                              │
         │ SSH (daemon)                 │ BLE (fire-and-forget)
         ▼                              ▼
    ┌─────────┐                    ┌─────────┐
    │  EV3    │                    │ Spike   │
    │ ~30ms   │                    │ ~10ms   │
    └─────────┘                    └─────────┘
```

## Files

| File | Description |
|------|-------------|
| `conductor.py` | Main orchestrator class |
| `test_beep_woof.py` | Beep/woof demo tests |
| `configs/devices.yaml` | Device (hardware) configuration |
| `configs/config.yaml` | Main settings + project mapping |
