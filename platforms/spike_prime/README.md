# Spike Prime Platform

Control LEGO Spike Prime hub (App 3 firmware) via Bluetooth Low Energy.

## Key Insights

| Limitation | Impact | Solution |
|------------|--------|----------|
| **No stdin** | Can't send commands to running program | Batch all actions into ONE program |
| **Startup melody** | Every program start plays a sound | Minimize program starts (1 melody) |
| **No true daemon** | Can't maintain persistent control loop | Use pre-uploaded programs |
| **Upload latency** | 200-500ms per program | Pre-upload or fire-and-forget |

### The Melody Problem

Each program start triggers a **firmware-level startup melody** that cannot be disabled:
- Upload program → Start program → **MELODY** → Actions run
- Solution: Put ALL actions in ONE program = **1 melody total**

### Signal-Based Collaboration

Spike can signal completion via `print()` + ConsoleNotification:

```python
# Spike program:
await sound.beep(880, 200)
print("DONE:0")  # Signals host via BLE

# Host receives "DONE:0" via ConsoleNotification
# Host can then trigger other robots (e.g., EV3)
```

## Quick Start

```bash
# Scan for hubs
python platforms/spike_prime/scan_lego.py

# Test sound and display
python platforms/spike_prime/test_sound.py

# Interactive flow mode (low latency)
python platforms/spike_prime/sp_fast.py flow

# Benchmark latency
python platforms/spike_prime/sp_fast.py benchmark
```

## Architecture

```
platforms/spike_prime/
├── sp_interface.py      # Main interface (SpikeInterface)
├── sp_fast.py           # Low-latency interface (SpikeFastInterface)
├── scan_lego.py         # BLE scanner for hubs
├── test_sound.py        # API tests
├── configs/             # Connection settings
└── lego_docs/           # Official LEGO protocol reference
```

## Spike App 3 API Reference

**Always reference `lego_docs/` before coding!**

### Sound (requires `await`)

```python
import runloop
from hub import sound

async def main():
    await sound.beep(440, 500)  # freq=440Hz, duration=500ms

runloop.run(main())
```

### Display - Text (requires `await`)

```python
import runloop
from hub import light_matrix

async def main():
    await light_matrix.write("HI")

runloop.run(main())
```

### Display - Pixels (synchronous)

```python
from hub import light_matrix
import time

light_matrix.clear()
light_matrix.set_pixel(2, 2, 100)  # x, y, brightness(0-100)

while True:
    time.sleep(1)  # Keep display on
```

### API Summary

| Function | Sync/Async | Example |
|----------|------------|---------|
| `sound.beep(freq, dur)` | **await** | `await sound.beep(440, 500)` |
| `sound.volume(level)` | sync | `sound.volume(100)` (0-100 scale) |
| `light_matrix.write(text)` | **await** | `await light_matrix.write("HI")` |
| `light_matrix.set_pixel(x,y,b)` | sync | `light_matrix.set_pixel(2, 2, 100)` |
| `light_matrix.clear()` | sync | `light_matrix.clear()` |

## Interfaces

### SpikeInterface (Standard)

Full-featured interface, uploads program for each action.

```python
from platforms.spike_prime import SpikeInterface

async with SpikeInterface(address, name) as spike:
    await spike.beep(880, 200)          # ~600-800ms
    await spike.show_display("happy")   # ~600-800ms
    await spike.play_melody("happy")
```

**Latency:** ~600-800ms per action (BLE upload)

### SpikeFastInterface (Low Latency)

Pre-uploads programs to slots at connect, then just starts slots.

```python
from platforms.spike_prime.sp_fast import SpikeFastInterface

async with SpikeFastInterface(address, name) as spike:
    # Pre-upload happens at connect (~3s once)
    
    await spike.fast_action("beep_high")  # ~50-100ms
    await spike.fast_action("happy")      # ~50-100ms
    
    # Fire-and-forget mode (fastest)
    await spike.fast_action("beep_high", wait_response=False)  # ~10-30ms
```

**Latency:**
- With acknowledgment: ~50-100ms
- Fire-and-forget: ~10-30ms

## Flow Mode

Interactive command-line interface:

```bash
python platforms/spike_prime/sp_fast.py flow
```

```
==================================================
SPIKE PRIME FLOW MODE
==================================================

Commands:
  beep [high|med|low]  - play beep
  happy/sad/heart/neutral - show face
  clear                - clear display
  stop                 - stop program
  quit                 - disconnect

Options:
  --wait               - wait for acknowledgment
--------------------------------------------------

> beep
[Spike] OK: beep_high (15ms, fire)

> happy
[Spike] OK: happy (12ms, fire)

> beep --wait
[Spike] OK: beep_high (89ms, ack)

> quit
Goodbye!
```

## Configuration

`configs/connection/bluetooth.yaml`:

```yaml
mode: bluetooth
name: Avatar Karo
address: E1BDF5C6-C666-4E77-A7E8-458FC0A9F809
slot: 19
```

## BLE Protocol

Reference: `lego_docs/docs/source/`

| UUID | Description |
|------|-------------|
| `0000FD02-0000-...` | Service |
| `0000FD02-0001-...` | RX (hub receives) |
| `0000FD02-0002-...` | TX (hub transmits) |

## Multi-Robot Collaboration

### Batched Sequences (Recommended)

Execute multiple actions in ONE program = **1 melody only**:

```python
# Instead of 3 separate programs (3 melodies):
await spike.fast_action("beep_high")
await spike.fast_action("beep_med")
await spike.fast_action("beep_low")

# Use ONE program (1 melody):
await spike.run_sequence([
    ("beep", 880, 200),
    ("delay", 300),
    ("beep", 660, 200),
    ("delay", 300),
    ("beep", 440, 200),
], delay_ms=0)
```

### Interactive Sequences (Real Collaboration)

Signal completion to host, enabling true alternation with other robots:

```python
async def on_beep_done(n):
    print(f"Beep {n} done!")
    await ev3.bark()  # Trigger EV3 after each beep

# Spike beeps, signals, host triggers EV3
await spike.run_interactive_sequence(
    actions=[("beep", 880, 200), ("beep", 660, 200), ("beep", 440, 200)],
    on_action_done=on_beep_done
)

# Timeline:
# Spike beep → signal → EV3 bark →
# Spike beep → signal → EV3 bark →
# Spike beep → signal → EV3 bark →
```

### Latency Modes

| Mode | Latency | Reliability | Use Case |
|------|---------|-------------|----------|
| **Fire-and-forget** | 10-30ms | Low (no ack) | Visual effects |
| **Acknowledged** | 50-100ms | High | Critical actions |
| **Batched sequence** | 300-500ms | High | Multi-action |
| **Interactive** | 500-1000ms | High | Collaboration |

## Troubleshooting

### Hub not found in scan
- Turn on hub (center button)
- Disconnect from LEGO app first (hub only advertises when not connected)
- Check Bluetooth is on

### Programs show slot number instead of running
- Program has syntax error
- Check API: `await` required for sound and text display

### Default melody plays instead of beep
- Missing `await` before `sound.beep()`
- Use: `await sound.beep(freq, dur)` not `sound.beep(freq, dur)`

### Melody plays multiple times
- You're starting multiple programs
- Use `run_sequence()` or `run_interactive_sequence()` for batched execution

### ConsoleNotification not received
- Ensure `print()` is followed by small delay: `time.sleep(0.1)`
- Check callback is registered: `spike.set_console_callback(handler)`

