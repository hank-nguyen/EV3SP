# EV3 Platform

LEGO Mindstorms EV3 implementation using ev3dev (Linux-based firmware).

## Requirements

- EV3 Brick with [ev3dev](https://www.ev3dev.org/) SD card
- WiFi dongle (e.g., EDIMAX)
- SSH access enabled

## Connection

```bash
# Default credentials
ssh robot@ev3dev.local  # or IP: 192.168.68.111
# Password: maker
```

## Architecture

```
┌─────────────┐     SSH      ┌─────────────────┐
│   Host PC   │ ──────────── │   EV3 (ev3dev)  │
│  (Python)   │   Paramiko   │    Linux 4.x    │
└─────────────┘              └─────────────────┘
       │                              │
       │ stdin/stdout                 │
       ▼                              ▼
 ┌───────────┐                ┌──────────────┐
 │  Session  │ ◄───────────── │   daemon.py  │
 │  Manager  │    text cmds   │  (persistent)│
 └───────────┘                └──────────────┘
                                     │
                                     ▼
                              ┌──────────────┐
                              │  Hardware    │
                              │ (motors,     │
                              │  sensors,    │
                              │  sound,      │
                              │  display)    │
                              └──────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `ev3_interface.py` | `RobotInterface` implementation (SSH, file upload) |
| `ev3_daemon.py` | Generic daemon template |
| `ev3_client.py` | Low-level SSH wrapper |

## Usage

### Basic Interface

```python
from platforms.ev3 import EV3Interface

with EV3Interface("192.168.68.111", "robot", "maker") as ev3:
    ev3.upload_file("my_script.py", "my_script.py")
    stdout, stderr, code = ev3.execute_command("python3 my_script.py")
```

### Daemon Session (Low Latency)

```python
from platforms.ev3 import EV3Interface, EV3DaemonSession

interface = EV3Interface("192.168.68.111", "robot", "maker")

# Daemon script runs on EV3, accepts commands via stdin
daemon_code = '''
import sys
while True:
    cmd = input()
    if cmd == "beep":
        # play sound
        print("OK")
    elif cmd == "quit":
        break
'''

session = EV3DaemonSession(interface, "my_daemon.py", "maker")
session.start(daemon_code)

# Now send commands with ~30ms latency
session.send("beep")  # Returns "OK"
session.send("quit")
```

## Daemon Protocol

### Command Format
```
Host → EV3:  command_name [args...]\n
EV3 → Host:  OK\n           (success)
             ERR: message\n (failure)
```

### Example Daemon

```python
#!/usr/bin/env python3
"""Minimal EV3 daemon template."""

import sys
from ev3dev2.sound import Sound
from ev3dev2.display import Display

sound = Sound()
display = Display()

ACTIONS = {
    "beep": lambda: sound.beep(),
    "speak": lambda text: sound.speak(text),
    "status": lambda: "running",
}

print("READY", flush=True)

while True:
    try:
        line = input()
        parts = line.strip().split()
        cmd = parts[0] if parts else ""
        args = parts[1:] if len(parts) > 1 else []
        
        if cmd == "quit":
            break
        elif cmd in ACTIONS:
            result = ACTIONS[cmd](*args) if args else ACTIONS[cmd]()
            print("OK" if result is None else result, flush=True)
        else:
            print(f"ERR: Unknown command: {cmd}", flush=True)
            
    except EOFError:
        break
    except Exception as e:
        print(f"ERR: {e}", flush=True)
```

## Display Control

The EV3 runs `brickman` (graphical menu) by default. To use custom display:

```python
import subprocess

def stop_brickman():
    subprocess.run(["sudo", "-S", "systemctl", "stop", "brickman"], 
                   input=b"maker\n")

def start_brickman():
    subprocess.run(["sudo", "-S", "systemctl", "start", "brickman"],
                   input=b"maker\n")

# In daemon:
stop_brickman()
try:
    # custom display code
finally:
    start_brickman()  # Always restore!
```

## Python 3.4 Compatibility

ev3dev uses Python 3.4. Avoid:

```python
# ❌ No f-strings
print(f"Value: {x}")

# ✅ Use format
print("Value: {}".format(x))

# ❌ No async/await
async def foo(): ...

# ✅ Use threading or callbacks
```

## Latency Benchmarks

| Mode | Latency | Use Case |
|------|---------|----------|
| Execute command | 1-2s | One-off scripts |
| Daemon (first) | 200ms | Session init |
| Daemon (subsequent) | 20-50ms | Real-time control |

## Troubleshooting

### Connection refused
```bash
# Check EV3 is on network
ping ev3dev.local  # or IP

# Check SSH service
ssh robot@192.168.68.111
```

### brickman doesn't restart
```bash
# SSH into EV3
sudo systemctl start brickman
```

### Display not updating
```python
# Must call update() after drawing
display.update()
```

