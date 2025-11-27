# Core - Platform-Agnostic Robot Control

The `core/` module provides abstract interfaces and utilities that work across all robot platforms (EV3, Spike Prime, and future additions).

## Architecture

```
core/
├── interface.py      # Abstract RobotInterface, DaemonSession
├── types.py          # Common types (Platform, RobotState, etc.)
├── collaboration.py  # Multi-robot coordination patterns
├── commands.py       # Unified command registry
├── shell.py          # Interactive terminal (IPython-like)
└── utils/
    └── signal_handler.py  # Graceful Ctrl+C handling
```

## Interactive Shell

The Orchestra Shell provides an IPython-like terminal for controlling robots:

```bash
python orchestra.py --ev3 192.168.68.111 --spike E1BDF5C6-...
```

```
╔═══════════════════════════════════════════════════════════════╗
║              LEGO Robotics Orchestra Shell                    ║
╚═══════════════════════════════════════════════════════════════╝

[ev3 sp] ⚡ ev3 beep
  ev3: OK (32ms)

[ev3 sp] ⚡ sp display heart
  sp: OK (15ms)

[ev3 sp] ⚡ all status
  ev3: bat:7.8V motors:ABC (28ms)
  sp: connected (12ms)
```

### Features

- **Tab completion** for commands and arguments
- **Command history** (↑/↓ arrows)
- **Color output** with latency display
- **Parallel execution** to multiple devices
- **Platform-agnostic commands** with automatic translation

## Unified Command Registry

Commands are defined once, work on both platforms:

```python
from core.commands import get_command, parse_command_line

# Parse user input
target, cmd_name, args = parse_command_line("ev3 beep high 500")
# target="ev3", cmd_name="beep", args={"pitch": "high", "duration": 500}

# Get platform-specific action
from core.commands import get_ev3_command, get_spike_action

ev3_cmd = get_ev3_command("display", {"pattern": "happy"})  # "eyes happy"
spike_action = get_spike_action("display", {"pattern": "happy"})  # "happy"
```

### Available Commands

| Command | Description | EV3 | Spike |
|---------|-------------|-----|-------|
| `beep [pitch] [duration]` | Play beep | ✓ | ✓ |
| `bark` | Woof sound | ✓ | - |
| `speak <text>` | Text-to-speech | ✓ | - |
| `display <pattern>` | Show pattern | ✓ | ✓ |
| `status` | Get device status | ✓ | ✓ |
| `motor <port> <speed>` | Control motor | ✓ | ✓ |
| `stop` | Stop all motors | ✓ | ✓ |

Patterns: `happy`, `sad`, `angry`, `surprised`, `heart`, `neutral`, `check`, `clear`

## Key Abstractions

### RobotInterface

Base class for platform-specific implementations:

```python
from core import RobotInterface

class MyRobotInterface(RobotInterface):
    def connect(self): ...
    def disconnect(self): ...
    def upload_file(self, local_path, remote_name): ...
    def execute_command(self, cmd, timeout=30): ...
    def get_state(self): ...
```

### DaemonSession

Low-latency control via persistent connection:

```python
from core import DaemonSession

# Daemon keeps robot ready for instant commands
# No re-authentication, no process restart
# Latency: ~20-100ms vs ~1-2s without daemon
```

## Collaboration Patterns

### The Problem

**Spike Prime limitation:** Each program start triggers a startup melody.
- Can't send commands to running program (no stdin like EV3)
- Each action upload = 1 melody
- Alternating actions = N melodies

### Solutions

#### 1. Batched Program (1 Melody)

```python
from core import create_batched_program

# All actions in ONE program = 1 melody total
program = create_batched_program([
    ("beep", 880, 200),
    ("delay", 500),
    ("beep", 880, 200),
    ("delay", 500),
    ("beep", 880, 200),
], platform="spike")
```

#### 2. Signal-Based Collaboration

```python
from core import SignalQueue, Signal

# Spike program prints "DONE:N" after each action
# Host receives via ConsoleNotification
# Host triggers EV3 in response

queue = SignalQueue()

def on_console(text):
    if "DONE:" in text:
        idx = int(text.split("DONE:")[1])
        queue.put(Signal("spike", idx))

# In main loop:
signal = await queue.wait(timeout=5.0)
if signal:
    await ev3.bark()  # React to Spike's completion
```

#### 3. Choreographed Pattern

```python
from core import ChoreographedPattern

# Pre-timed alternation (fixed delays, no runtime signals)
pattern = ChoreographedPattern(gap_ms=500)
await pattern.execute(robots, [
    ("spike", "beep", (880, 200)),
    ("ev3", "bark", ()),
])
```

## Utilities

### Graceful Shutdown

```python
from core.utils import run_async_with_cleanup

async def main():
    async with Conductor.from_config("config.yaml") as conductor:
        # work here
        pass

if __name__ == "__main__":
    run_async_with_cleanup(
        main(),
        cleanup_message="[Interrupted] Cleaning up...",
        done_message="[Done] Cleanup complete"
    )
```

Ensures:
- EV3 returns to menu on Ctrl+C
- Spike Prime disconnects cleanly
- All async resources released

## Platform Comparison

| Feature | EV3 | Spike Prime |
|---------|-----|-------------|
| **Connection** | SSH (Paramiko) | BLE (Bleak) |
| **Latency** | ~20-50ms (daemon) | ~50-300ms |
| **Daemon** | ✅ Yes (stdin/stdout) | ❌ No (no stdin) |
| **Streaming** | ✅ Real-time commands | ❌ Upload per action |
| **Startup Sound** | None | Melody per program |
| **Signals** | stdout | ConsoleNotification |

## Key Insights

1. **EV3 is simpler**: SSH + stdin/stdout = true bidirectional streaming
2. **Spike requires batching**: Minimize program starts = minimize melodies
3. **Use signals for collaboration**: `print()` + ConsoleNotification bridges the gap
4. **Queue for sync**: `asyncio.Queue` properly awaits signals before continuing

