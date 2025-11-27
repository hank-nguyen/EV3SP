# LEGO® Education SPIKE™ Prime Protocol

Official protocol documentation and reference implementation for communicating with SPIKE™ Prime hubs over BLE (App 3 firmware).

**⚠️ ALWAYS reference this folder before coding Spike Prime features!**

## Quick Reference

### BLE UUIDs

| Item | UUID |
|------|------|
| **Service** | `0000FD02-0000-1000-8000-00805F9B34FB` |
| **RX** (hub receives) | `0000FD02-0001-1000-8000-00805F9B34FB` |
| **TX** (hub transmits) | `0000FD02-0002-1000-8000-00805F9B34FB` |

### Message Types (Most Used)

| ID | Message | Purpose |
|----|---------|---------|
| `0x00` | InfoRequest | Handshake (send first!) |
| `0x01` | InfoResponse | Hub capabilities (max chunk size, etc.) |
| `0x0C` | StartFileUploadRequest | Begin file upload |
| `0x0D` | StartFileUploadResponse | Upload ack |
| `0x10` | TransferChunkRequest | Send file data |
| `0x11` | TransferChunkResponse | Chunk ack |
| `0x1E` | ProgramFlowRequest | Start/stop program |
| `0x1F` | ProgramFlowResponse | Flow ack |
| `0x21` | **ConsoleNotification** | `print()` output from hub! |

### Encoding Steps

1. **COBS encode** - Escape bytes 0x00, 0x01, 0x02
2. **XOR with 0x03** - Avoid control characters
3. **Frame** - Optional `0x01` prefix + required `0x02` suffix

## File Structure

```
protocols/spike-prime-protocol/
├── README.md               # This file
├── docs/                   # Sphinx documentation source
│   └── source/
│       ├── connect.rst     # BLE connection setup
│       ├── encoding.rst    # COBS/framing algorithm
│       ├── messages.rst    # All message types
│       └── enums.rst       # Enum values (colors, faces, etc.)
└── examples/
    └── python/
        ├── app.py          # Example client (USE THIS!)
        ├── messages.py     # Message serialization
        ├── cobs.py         # COBS encode/decode
        └── crc.py          # CRC32 implementation
```

## Usage Examples

### From `examples/python/`

#### 1. Connecting and Handshake

```python
from bleak import BleakClient
import cobs
import messages

SERVICE_UUID = "0000FD02-0000-1000-8000-00805F9B34FB"
RX_UUID = "0000FD02-0001-1000-8000-00805F9B34FB"
TX_UUID = "0000FD02-0002-1000-8000-00805F9B34FB"

async def connect(address):
    client = BleakClient(address)
    await client.connect()
    await client.start_notify(TX_UUID, on_data)
    
    # Always send InfoRequest first!
    msg = messages.InfoRequest().serialize()
    await client.write_gatt_char(RX_UUID, cobs.pack(msg))
```

#### 2. Uploading a Program

```python
# From examples/python/app.py

async def upload_file(program: bytes, slot: int = 19, name: str = "program.py"):
    # Calculate CRC
    file_crc = crc32(program)
    
    # Start upload
    msg = messages.StartFileUploadRequest(name, slot, file_crc)
    await send_message(msg)
    response = await wait_response()  # StartFileUploadResponse
    
    # Transfer chunks
    running_crc = 0
    offset = 0
    while offset < len(program):
        chunk = program[offset:offset + max_chunk_size]
        running_crc = crc32(chunk, running_crc)
        
        msg = messages.TransferChunkRequest(running_crc, chunk)
        await send_message(msg)
        response = await wait_response()  # TransferChunkResponse
        
        offset += len(chunk)
    
    # Start program
    msg = messages.ProgramFlowRequest(stop=False, slot=slot)
    await send_message(msg)
```

#### 3. Receiving Console Output

```python
# ConsoleNotification receives print() from hub

def on_data(_, data: bytearray):
    message = cobs.unpack(bytes(data))
    msg = messages.deserialize(message)
    
    if isinstance(msg, messages.ConsoleNotification):
        print(f"Hub says: {msg.text}")
        # Use this for signaling! e.g., "DONE:0", "DONE:1"
```

## Key Insights for Coding

### 1. Always Start with InfoRequest

```python
# FIRST message after connect must be InfoRequest
msg = messages.InfoRequest().serialize()
await client.write_gatt_char(RX_UUID, cobs.pack(msg))
# Wait for InfoResponse to get max_chunk_size
```

### 2. Respect Max Chunk Size

```python
# InfoResponse tells you the max chunk size
info = await wait_for_info_response()
max_chunk = info.max_chunk_size  # Usually 512

# Split large programs into chunks of this size
```

### 3. Use ConsoleNotification for Signaling

```python
# In MicroPython on hub:
await sound.beep(880, 200)
print("DONE:0")  # ← Sent to host via ConsoleNotification

# On host, receive via TX characteristic notification
if msg.ID == 0x21:  # ConsoleNotification
    signal = msg.text  # "DONE:0"
```

### 4. COBS Encoding is Critical

```python
# Wrong: sending raw bytes
await client.write_gatt_char(RX_UUID, raw_message)  # ❌

# Correct: COBS encode + frame
await client.write_gatt_char(RX_UUID, cobs.pack(raw_message))  # ✓
```

### 5. Program Slots

- Slots 0-19 available
- Use slot 19 for temporary programs (our convention)
- Programs persist until overwritten or cleared

## Common Patterns in Our Codebase

### Location: `platforms/spike_prime/`

| File | Uses Protocol For |
|------|-------------------|
| `sp_interface.py` | Full message implementation, upload, flow control |
| `sp_fast.py` | Pre-upload optimization, sequence execution |

### Key Functions That Use Protocol

```python
# In sp_interface.py
async def upload_and_run(self, program: bytes) -> bool:
    # Uses: StartFileUploadRequest, TransferChunkRequest, ProgramFlowRequest

async def _on_data(self, _, data: bytearray):
    # Uses: ConsoleNotification for print() signals

# In sp_fast.py  
async def run_sequence(self, actions: list) -> float:
    # Generates MicroPython, uses upload_and_run
```

## Troubleshooting

### "No response from hub"
- Did you send `InfoRequest` first?
- Is COBS encoding applied?
- Did you enable TX notifications?

### "CRC mismatch"
- Ensure running CRC is updated for each chunk
- Use the CRC32 algorithm from `examples/python/crc.py`

### "Program shows slot number"
- Syntax error in uploaded program
- Check `await` for async functions (sound.beep, light_matrix.write)

### "ConsoleNotification not received"
- Add `time.sleep(0.1)` after `print()` in hub code
- Ensure TX characteristic notifications are enabled

## References

- **Full Documentation**: Build with `cd docs && make html`
- **Example Client**: `examples/python/app.py` - complete working example
- **Message Types**: `docs/source/messages.rst` - all message definitions
- **Encoding Details**: `docs/source/encoding.rst` - COBS algorithm

---

**Note**: This protocol is for SPIKE™ App 3 firmware. Earlier firmware versions use different protocols.
