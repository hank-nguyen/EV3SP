# EV3 Platform

LEGO Mindstorms EV3 implementation supporting both **ev3dev** (Linux) and **Pybricks MicroPython**.

## Firmware Options

| Firmware | Python | Connection | Latency | Best For |
|----------|--------|------------|---------|----------|
| **Pybricks MicroPython** | MicroPython | USB Serial / TCP | **1-15ms** | Low-latency control |
| ev3dev-stretch | Python 3.4 | SSH over WiFi | 30-50ms | Linux shell access |

## Quick Start (Pybricks MicroPython) ⚡

### 1. Flash Pybricks to EV3
1. Download Pybricks firmware from [pybricks.com](https://pybricks.com/)
2. Flash to microSD card
3. Boot EV3 from SD card

### 2. Deploy Daemon
```bash
# Copy daemon to EV3 via USB or network
scp platforms/ev3/pybricks_daemon.py robot@192.168.68.114:~/

# On EV3, run manually:
brickrun pybricks_daemon.py
```

### 3. Auto-Start Daemon (Optional)

To start the daemon automatically on EV3 boot:

```bash
# Copy service file to EV3
scp platforms/ev3/pybricks-daemon.service robot@192.168.68.114:~/

# SSH to EV3 and install service
ssh robot@192.168.68.114
sudo cp ~/pybricks-daemon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pybricks-daemon
sudo systemctl start pybricks-daemon

# Check status
sudo systemctl status pybricks-daemon
```

After this, the daemon starts automatically on boot - no manual start needed!

### 4. Connect from Host
```bash
# Auto-detect (tries USB first, then WiFi)
python projects/puppy/puppy.py action=flow

# Specify WiFi host
python projects/puppy/puppy.py action=flow connection.host=192.168.68.114

# Or use ev3_micropython directly
python platforms/ev3/ev3_micropython.py flow --host 192.168.68.114
```

## Architecture

### Pybricks MicroPython (Recommended)

```
┌─────────────────┐                 ┌─────────────────┐
│   Host (Python) │                 │  EV3 (Pybricks) │
│                 │                 │                 │
│  ev3_micropython├───── USB ──────►│ pybricks_daemon │
│       .py       │   Serial        │     .py         │
│                 │   (~1-5ms)      │                 │
│                 ├──── WiFi ──────►│  TCP:9000       │
│                 │   TCP Socket    │  (~5-15ms)      │
│                 │                 │                 │
└─────────────────┘                 └────────┬────────┘
                                             │
                                             ▼
                                    ┌────────────────┐
                                    │    Hardware    │
                                    │ Motors/Sensors │
                                    │ Display/Sound  │
                                    └────────────────┘
```

### ev3dev (Legacy)

```
┌─────────────────┐     SSH      ┌─────────────────┐
│   Host PC       │ ──────────── │   EV3 (ev3dev)  │
│   (Python)      │   Paramiko   │    Linux 4.x    │
└─────────────────┘   (~30-50ms) └─────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `ev3_micropython.py` | Host interface for Pybricks (USB/WiFi) |
| `action_adapter.py` | Translates project actions → daemon commands |
| `pybricks_daemon.py` | Generic daemon running on EV3 (Pybricks) |
| `ev3_interface.py` | Legacy ev3dev interface (SSH) |

## Action Adapter

The `ActionAdapter` translates high-level project actions to daemon commands:

```python
from platforms.ev3 import EV3MicroPython, ActionAdapter

# Option 1: Load from YAML
async with EV3MicroPython() as ev3:
    ev3.load_actions("projects/puppy/configs/actions.yaml")
    await ev3.execute("sitdown")  # Auto-translates!

# Option 2: Auto-load for known project
async with EV3MicroPython() as ev3:
    ev3.load_actions_for_project("puppy")
    await ev3.execute("bark")

# Option 3: Use adapter directly
adapter = ActionAdapter.from_yaml("actions.yaml")
commands = adapter.translate("sitdown")
# Returns: [("eyes sleepy", 0), ("motor D -25", 0), ...]
```

### YAML Action Format

```yaml
# projects/<project>/configs/actions.yaml
actions:
  sitdown:
    description: "Sit down"
    steps:
      - [eyes happy, 0]              # [command, delay_ms]
      - [target2 D A 0 150, 1500]    # Move both legs to 0°, wait 1500ms
  
  standup:
    description: "Stand up"
    steps:
      - [eyes neutral, 0]
      - [target2 D A -55 100, 1800]  # Move both legs to -55°

  bark:
    description: "Bark"
    steps:
      - [eyes surprised, 0]
      - [sound dog_bark, 0]
```

## Generic Daemon Design

**Key insight**: `pybricks_daemon.py` is intentionally **generic** - it only provides low-level primitives:

```
Generic Commands (daemon knows):     Project Actions (adapter translates):
├── motor <port> <speed> [ms]        ├── sitdown → [eyes happy, target2 D A 0 150]
├── target <port> <angle> [speed]    ├── standup → [eyes neutral, target2 D A -55 100]
├── target2 <p1> <p2> <angle>        ├── bark → [eyes surprised, sound dog_bark]
├── stop [port]                      └── ... defined in YAML, not code!
├── pos / reset
├── beep / sound / speak
├── eyes <expression>
├── display <text>
├── sensor <port>
├── status
└── quit
```

**Benefits**:
- **Reusable**: Same daemon works for puppy, robot arm, or any project
- **Simple**: Daemon has no project knowledge, easy to maintain
- **Flexible**: Add new actions via YAML - no code changes!
- **Debuggable**: Test motor commands directly via `nc <ip> 9000`

**Adding project support**: Create `configs/actions.yaml` in your project folder.

## Latency Comparison

| Transport | Latency | Notes |
|-----------|---------|-------|
| **USB Serial** | **1-5ms** | Best, requires USB cable |
| **WiFi TCP Socket** | **5-15ms** | Good, direct socket (no SSH) |
| Bluetooth RFCOMM | 10-20ms | Wireless, needs pairing |
| SSH over WiFi | 30-50ms | Legacy ev3dev method |
| Execute command | 1-2s | One-off scripts |

## Usage

### Pybricks MicroPython API

```python
from platforms.ev3.ev3_micropython import EV3MicroPython, EV3Config

# Auto-detect connection (USB > WiFi > Bluetooth)
async with EV3MicroPython() as ev3:
    response, latency = await ev3.beep(880, 200)
    print(f"Response: {response} ({latency:.1f}ms)")

# Force WiFi connection
config = EV3Config(wifi_host="192.168.1.100", wifi_port=9000)
async with EV3MicroPython(config=config, transport="wifi") as ev3:
    await ev3.motor("A", 50, 1000)  # Motor A at 50% for 1 second
    await ev3.eyes("happy")
```

### Available Commands

| Command | Description |
|---------|-------------|
| `beep [freq] [dur]` | Play beep (default: 880Hz, 200ms) |
| `speak <text>` | Text-to-speech |
| `sound <name>` | Play sound file (e.g., `dog_bark`) |
| `motor <port> <speed>` | Run motor (-100 to 100) |
| `motor <port> <speed> <ms>` | Run motor for time |
| `target <port> <angle> [speed]` | Move motor to angle |
| `target2 <p1> <p2> <angle> [speed]` | Move 2 motors simultaneously |
| `stop [port]` | Stop motor (or all) |
| `pos [port]` | Get motor angle(s) |
| `reset [port]` | Reset motor angle to 0 |
| `sensor <port>` | Read sensor value |
| `eyes <expr>` | Show expression (happy, angry, sleepy, surprised, love, wink) |
| `display <text>` | Show text on display |
| `status` | Get battery/motor/sensor status |
| `quit` | Exit daemon |

### Interactive Flow Mode

```bash
python platforms/ev3/ev3_micropython.py flow
```

```
> beep 440 500
[EV3] OK (3.2ms)

> motor A 50 1000
[EV3] OK (2.1ms)

> eyes happy
[EV3] OK (4.5ms)

> status
[EV3] OK bat:7800mV motors:A,B,C sensors:1:touch (2.8ms)

> benchmark
Benchmark: 10 round-trips...
  1: 2.3ms
  2: 2.1ms
  ...
Average: 2.5ms
```

## Daemon Protocol

### Command Format
```
Host → EV3:  command [args...]\n
EV3 → Host:  OK [result]\n        (success)
             ERR: message\n       (failure)
             QUIT:reason\n        (daemon exit)
```

### Example Session
```
Host → EV3:  beep 880 200
EV3 → Host:  OK

Host → EV3:  motor A 50
EV3 → Host:  OK

Host → EV3:  status
EV3 → Host:  OK bat:7800mV motors:A,B,C sensors:1:touch

Host → EV3:  quit
EV3 → Host:  QUIT
```

## Transport Details

### USB Serial

**Best latency (~1-5ms)**, requires USB cable.

The EV3 appears as a serial device:
- macOS: `/dev/tty.usbmodem*` or `/dev/cu.usbmodem*`
- Linux: `/dev/ttyACM*`
- Windows: `COM*`

Auto-detection checks for LEGO/EV3 USB identifiers.

### WiFi TCP Socket

**Good latency (~5-15ms)**, wireless.

Direct TCP socket on port 9000 (configurable). Much faster than SSH because:
- No encryption overhead
- No shell spawn
- Simple text protocol

Requirements:
- EV3 connected to WiFi (USB dongle or Bluetooth PAN)
- Firewall allows port 9000

### Bluetooth RFCOMM

**Moderate latency (~10-20ms)**, wireless without WiFi.

Uses RFCOMM channel 1 (EV3 standard). Requires:
- Bluetooth pairing between host and EV3
- Python `socket` with Bluetooth support

## Migration from ev3dev

| ev3dev (old) | Pybricks (new) |
|--------------|----------------|
| `from ev3dev2.sound import Sound` | `from pybricks.hubs import EV3Brick` |
| `sound.beep()` | `ev3.speaker.beep()` |
| `EV3Interface` (SSH) | `EV3MicroPython` (USB/TCP) |
| `EV3DaemonSession` | Use `EV3MicroPython` directly |

### Key Differences

1. **No SSH**: Pybricks uses direct serial/socket connections
2. **No sudo**: Pybricks doesn't need password for display control
3. **No brickman**: Pybricks has its own launcher
4. **Modern Python**: Pybricks supports f-strings and async (unlike ev3dev's Python 3.4)

## Troubleshooting

### USB Serial not detected
```bash
# Check USB devices
ls /dev/tty.usb*   # macOS
ls /dev/ttyACM*    # Linux

# Install pyserial
pip install pyserial
```

### WiFi connection refused
```bash
# Check EV3 IP
ping ev3dev.local

# Check daemon is running on EV3
# Should see "TCP Daemon" on EV3 display

# Test connection
nc 192.168.1.100 9000
```

### Daemon won't start
```bash
# On EV3, check for errors
brickrun -v pybricks_daemon.py

# Check Pybricks firmware is installed
# EV3 should show Pybricks logo on boot
```

## Requirements

### Host
```bash
pip install pyserial  # For USB Serial
```

### EV3
- Pybricks firmware (recommended) OR
- ev3dev-stretch with Python 3.4

## References

- [Pybricks Documentation](https://docs.pybricks.com/)
- [Pybricks EV3 Guide](https://pybricks.com/ev3-micropython/)
- [ev3dev Documentation](https://www.ev3dev.org/) (legacy)
- Protocol examples: `protocols/pybricks-protocol/examples/ev3/`
