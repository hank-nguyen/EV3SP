# Platforms - Hardware-Specific Implementations

The `platforms/` directory contains implementations for specific robot hardware. Each platform implements the abstract interfaces from `core/`.

## Structure

```
platforms/
├── ev3/                    # LEGO Mindstorms EV3
│   ├── ev3_micropython.py  # ★ DEFAULT: USB/WiFi TCP (~1-15ms)
│   ├── pybricks_daemon.py  # Daemon for Pybricks MicroPython
│   ├── ev3_interface.py    # Legacy: SSH interface (~30-50ms)
│   ├── ev3_daemon.py       # Legacy: ev3dev daemon
│   └── ev3_client.py       # Legacy: SSH client wrapper
│
├── spike_prime/            # LEGO Spike Prime
│   ├── sp_interface.py     # BLE communication + LEGO protocol
│   ├── sp_fast.py          # Optimized interface (pre-upload, sequences)
│   └── (see protocols/)    # Official LEGO protocol documentation
│
└── README.md               # This file
```

## Platform Comparison

| Aspect | EV3 (MicroPython) | EV3 (ev3dev) | Spike Prime |
|--------|-------------------|--------------|-------------|
| **Firmware** | Pybricks | ev3dev-stretch | LEGO App 3 |
| **Python** | MicroPython | Python 3.4 | MicroPython |
| **Connection** | USB / WiFi TCP | SSH over WiFi | BLE |
| **Protocol** | stdin/stdout text | SSH + stdin | COBS + CRC binary |
| **Latency** | **1-15ms** | 30-50ms | 50-300ms |
| **Real-time Control** | ✅ Streaming | ✅ Streaming | ❌ Per-program |

## EV3 Platform

### Default: MicroPython (Recommended) ⚡

**Latency: 1-15ms** - Up to 10x faster than legacy SSH!

```python
from platforms.ev3 import EV3MicroPython, EV3Config

# Auto-detect (tries USB first, then WiFi)
async with EV3MicroPython() as ev3:
    response, latency = await ev3.beep(880, 200)
    print(f"Latency: {latency:.1f}ms")  # ~2-5ms via USB!

# Force specific transport
config = EV3Config(wifi_host="192.168.1.100", wifi_port=9000)
ev3 = EV3MicroPython(config=config, transport="wifi")
```

**Transport options:**
- `usb` - USB Serial (~1-5ms) - fastest, requires cable
- `wifi` - TCP Socket (~5-15ms) - no SSH overhead
- `bluetooth` - RFCOMM (~10-20ms) - wireless, needs pairing
- `auto` - Try all in order (default)

### Legacy: ev3dev SSH

**Latency: 30-50ms** - Still available for backward compatibility.

```python
from platforms.ev3 import EV3Interface, EV3DaemonSession

interface = EV3Interface("192.168.68.111", "robot", "maker")
session = EV3DaemonSession(interface, "my_daemon.py", "maker")
session.start(daemon_code)
response = session.send("bark")  # ~30ms
```

### EV3 Strengths
- **True daemon**: Persistent process accepts commands via stdin
- **Low latency**: ~1-50ms depending on transport
- **Full control**: Display, sound, motors, sensors
- **No startup sounds**: Silent operation

## Spike Prime Platform

### Strengths
- **Wireless**: BLE, no cables or dongles
- **Modern hub**: Better display, speaker, sensors
- **Official API**: Well-documented MicroPython

### Challenges
- **No stdin**: Can't send commands to running program
- **Startup melody**: Every program start plays a sound
- **Latency**: Upload + start = 200-500ms per action

### Solutions

#### 1. Pre-upload Programs (SpikeFastInterface)
```python
from platforms.spike_prime import SpikeFastInterface

# Upload all programs at connect time
spike = SpikeFastInterface(address, name)
await spike.connect(preload=True)  # Uploads 10+ programs

# Later: just start the slot (fast!)
await spike.fast_action("beep_high")  # ~50ms
```

#### 2. Batch Actions (1 Melody)
```python
# All beeps in ONE program = 1 melody total
await spike.run_sequence([
    ("beep", 880, 200),
    ("delay", 300),
    ("beep", 880, 200),
], delay_ms=0)
```

#### 3. Signal-Based Collaboration
```python
# Spike prints "DONE:N" → Host receives → triggers EV3
await spike.run_interactive_sequence(
    actions=[("beep", 880, 200), ("beep", 660, 200)],
    on_action_done=lambda n: ev3.bark()
)
```

## Adding New Platforms

1. Create `platforms/new_platform/`
2. Implement `RobotInterface` from `core/`
3. Optionally implement `DaemonSession` if platform supports it
4. Add to `core/interface.py` factory functions
5. Create README with platform-specific notes

## Protocol Notes

### EV3 (Text Protocol)
```
Host sends: "bark\n"
Daemon responds: "OK\n" or "ERR: message\n"
```

### Spike Prime (Binary Protocol)
```
Frame: [COBS-encoded payload][0x02]
Payload: [message_id][data...][CRC16]

Key message types:
- 0x0E: StartFileUpload
- 0x0F: TransferChunk
- 0x10: ProgramFlow (start/stop)
- 0x21: ConsoleNotification (print from hub)
```

See `protocols/spike-prime-protocol/` for full protocol specification.
