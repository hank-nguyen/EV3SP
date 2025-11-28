#!/usr/bin/env python3
"""
Spike Prime Interface
---------------------
High-level interface for LEGO Spike Prime hub (App 3 firmware).
Provides abstracted control matching EV3 interface patterns.
"""

import os
import sys
import asyncio
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

# Load LEGO protocol modules
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
LEGO_PYTHON_DIR = os.path.join(ROOT_DIR, "protocols/spike-prime-protocol/examples/python")

import importlib.util

def _load_lego_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(LEGO_PYTHON_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_crc_module = _load_lego_module("lego_crc", "crc.py")
_cobs_module = _load_lego_module("lego_cobs", "cobs.py")
_messages_module = _load_lego_module("messages", "messages.py")

crc = _crc_module.crc
cobs = _cobs_module

# Import message classes
InfoRequest = _messages_module.InfoRequest
InfoResponse = _messages_module.InfoResponse
ClearSlotRequest = _messages_module.ClearSlotRequest
ClearSlotResponse = _messages_module.ClearSlotResponse
StartFileUploadRequest = _messages_module.StartFileUploadRequest
StartFileUploadResponse = _messages_module.StartFileUploadResponse
TransferChunkRequest = _messages_module.TransferChunkRequest
TransferChunkResponse = _messages_module.TransferChunkResponse
ProgramFlowRequest = _messages_module.ProgramFlowRequest
ProgramFlowResponse = _messages_module.ProgramFlowResponse
DeviceNotificationRequest = _messages_module.DeviceNotificationRequest
DeviceNotificationResponse = _messages_module.DeviceNotificationResponse
deserialize = _messages_module.deserialize

from bleak import BleakClient, BleakScanner

# BLE UUIDs for Spike App 3
SERVICE_UUID = "0000fd02-0000-1000-8000-00805f9b34fb"
RX_CHAR_UUID = "0000fd02-0001-1000-8000-00805f9b34fb"
TX_CHAR_UUID = "0000fd02-0002-1000-8000-00805f9b34fb"


# ============================================================
# LED Matrix Patterns (5x5)
# ============================================================

PATTERNS = {
    "happy": [
        (1, 1), (3, 1),           # eyes
        (0, 3), (4, 3),           # smile corners
        (1, 4), (2, 4), (3, 4),   # smile
    ],
    "sad": [
        (1, 1), (3, 1),           # eyes
        (1, 3), (2, 3), (3, 3),   # frown
        (0, 4), (4, 4),           # frown corners
    ],
    "neutral": [
        (1, 1), (3, 1),           # eyes
        (1, 3), (2, 3), (3, 3),   # straight mouth
    ],
    "angry": [
        (0, 0), (1, 1),           # left eyebrow
        (4, 0), (3, 1),           # right eyebrow
        (1, 3), (2, 3), (3, 3),   # frown
        (0, 4), (4, 4),           
    ],
    "surprised": [
        (1, 1), (3, 1),           # eyes
        (1, 3), (2, 3), (3, 3),   # O mouth
        (1, 4), (3, 4),
        (2, 2),
    ],
    "heart": [
        (1, 0), (3, 0),
        (0, 1), (2, 1), (4, 1),
        (0, 2), (4, 2),
        (1, 3), (3, 3),
        (2, 4),
    ],
    "check": [
        (4, 0),
        (3, 1),
        (2, 2),
        (1, 3), (0, 2),
    ],
    "x": [
        (0, 0), (4, 0),
        (1, 1), (3, 1),
        (2, 2),
        (1, 3), (3, 3),
        (0, 4), (4, 4),
    ],
}


def generate_display_program(pattern_name: str, brightness: int = 100) -> bytes:
    """Generate micropython code to display a pattern."""
    if pattern_name not in PATTERNS:
        # Try as text
        return f"""from hub import light_matrix
light_matrix.write("{pattern_name}")
import time
while True:
    time.sleep(1)
""".encode("utf8")
    
    pixels = PATTERNS[pattern_name]
    pixel_code = "\n".join([
        f"light_matrix.set_pixel({x}, {y}, {brightness})"
        for x, y in pixels
    ])
    
    return f"""from hub import light_matrix
import time

light_matrix.clear()
{pixel_code}

while True:
    time.sleep(1)
""".encode("utf8")


def generate_motor_program(port: str, speed: int, duration_ms: int) -> bytes:
    """Generate micropython code to run a motor."""
    return f"""from hub import port
import time

motor = port.{port.upper()}.motor
motor.run_for_degrees({int(speed * duration_ms / 1000)}, {speed})
time.sleep({duration_ms / 1000 + 0.5})
""".encode("utf8")


def generate_beep_program(frequency: int = 440, duration_ms: int = 500) -> bytes:
    """
    Generate micropython code to play a beep on hub's built-in speaker.
    
    Note: sound.beep() requires await in Spike App 3.
    Reference: protocols/spike-prime-protocol/examples/python/app.py
    """
    return f"""import runloop
from hub import sound

async def main():
    await sound.beep({frequency}, {duration_ms})

runloop.run(main())
""".encode("utf8")


def generate_melody_program(notes: list) -> bytes:
    """
    Generate micropython code to play a melody.
    
    Args:
        notes: List of (frequency, duration_ms) tuples
               e.g., [(440, 200), (494, 200), (523, 400)]
    
    Note: sound.beep() requires await in Spike App 3.
    """
    beeps = "\n    ".join([
        f"await sound.beep({freq}, {dur})"
        for freq, dur in notes
    ])
    return f"""import runloop
from hub import sound

async def main():
    {beeps}

runloop.run(main())
""".encode("utf8")


# Common melodies
MELODIES = {
    "happy": [(523, 150), (659, 150), (784, 300)],  # C-E-G
    "sad": [(392, 300), (349, 300), (330, 400)],     # G-F-E descending
    "alert": [(880, 100), (0, 50), (880, 100)],      # beep-beep
    "success": [(523, 150), (659, 150), (784, 150), (1047, 300)],  # C-E-G-C
    "error": [(200, 300), (150, 300)],               # low tones
    "startup": [(262, 100), (330, 100), (392, 100), (523, 200)],  # C-E-G-C
}


# ============================================================
# Spike Prime Interface
# ============================================================

@dataclass
class SpikeConfig:
    """Spike Prime connection configuration."""
    name: str = "Spike Prime"
    address: str = ""
    slot: int = 19  # Default program slot


class SpikeInterface:
    """
    High-level interface for Spike Prime hub.
    Matches EV3Interface patterns for consistency.
    """
    
    def __init__(self, address: str, name: str = "Spike Prime", slot: int = 19):
        self.address = address
        self.name = name
        self.slot = slot
        self._client: Optional[BleakClient] = None
        self._connected = False
        self._info_response = None
        self._pending_response = [None, None]
        self._rx_char = None
        self._tx_char = None
        self._console_callback = None  # For print() notifications from hub
    
    async def connect(self) -> bool:
        """Connect to the Spike Prime hub."""
        print(f"Connecting to {self.name} [{self.address}]...")
        
        try:
            self._client = BleakClient(self.address)
            await self._client.connect(timeout=10.0)
            
            service = self._client.services.get_service(SERVICE_UUID)
            self._rx_char = service.get_characteristic(RX_CHAR_UUID)
            self._tx_char = service.get_characteristic(TX_CHAR_UUID)
            
            await self._client.start_notify(self._tx_char, self._on_data)
            
            # Get hub info
            self._info_response = await self._send_request(InfoRequest(), InfoResponse)
            
            self._connected = True
            print(f"\033[36m✓ Connected to {self.name}\033[0m")
            return True
            
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the hub."""
        if self._client and self._connected:
            # Stop any running program
            try:
                await self._send_request(
                    ProgramFlowRequest(stop=True, slot=self.slot),
                    ProgramFlowResponse
                )
            except:
                pass
            
            try:
                await self._client.stop_notify(self._tx_char)
                await self._client.disconnect()
            except:
                pass
            
        self._connected = False
        print(f"✓ Disconnected from {self.name}")
    
    def _on_data(self, _, data: bytearray) -> None:
        """Handle incoming data from hub."""
        if data[-1] != 0x02:
            return
        
        unpacked = cobs.unpack(data)
        try:
            message = deserialize(unpacked)
            
            # Handle pending response
            if self._pending_response[0] is not None and message.ID == self._pending_response[0]:
                self._pending_response[1].set_result(message)
            
            # Handle console notifications (print from hub)
            if hasattr(message, 'text') and self._console_callback:
                self._console_callback(message.text)
                
        except:
            pass
    
    def set_console_callback(self, callback):
        """Set callback for console notifications (print from hub program)."""
        self._console_callback = callback
    
    async def _send_message(self, message) -> None:
        """Send a message to the hub."""
        payload = message.serialize()
        frame = cobs.pack(payload)
        packet_size = self._info_response.max_packet_size if self._info_response else len(frame)
        
        for i in range(0, len(frame), packet_size):
            packet = frame[i : i + packet_size]
            await self._client.write_gatt_char(self._rx_char, packet, response=False)
    
    async def _send_request(self, message, response_type, timeout: float = 5.0):
        """Send a message and wait for response."""
        self._pending_response = [response_type.ID, asyncio.Future()]
        await self._send_message(message)
        return await asyncio.wait_for(self._pending_response[1], timeout=timeout)
    
    async def upload_and_run(self, program: bytes) -> bool:
        """Upload a program and run it."""
        if not self._connected:
            return False
        
        try:
            # Stop any running program
            try:
                await self._send_request(
                    ProgramFlowRequest(stop=True, slot=self.slot),
                    ProgramFlowResponse
                )
            except:
                pass
            
            # Clear slot
            try:
                await self._send_request(ClearSlotRequest(self.slot), ClearSlotResponse)
            except:
                pass
            
            await asyncio.sleep(0.2)
            
            # Start upload
            program_crc = crc(program)
            await self._send_request(
                StartFileUploadRequest("program.py", self.slot, program_crc),
                StartFileUploadResponse
            )
            
            # Transfer chunks
            running_crc = 0
            chunk_size = self._info_response.max_chunk_size
            for i in range(0, len(program), chunk_size):
                chunk = program[i : i + chunk_size]
                running_crc = crc(chunk, running_crc)
                await self._send_request(
                    TransferChunkRequest(running_crc, chunk),
                    TransferChunkResponse
                )
            
            await asyncio.sleep(0.2)
            
            # Run program
            await self._send_request(
                ProgramFlowRequest(stop=False, slot=self.slot),
                ProgramFlowResponse
            )
            
            return True
            
        except Exception as e:
            print(f"Upload failed: {e}")
            return False
    
    async def show_display(self, pattern: str, brightness: int = 100) -> bool:
        """
        Show a pattern on the LED matrix.
        
        Args:
            pattern: Pattern name (happy, sad, neutral, angry, surprised, heart, check, x)
                     or text string to scroll
            brightness: LED brightness 0-100
        """
        program = generate_display_program(pattern, brightness)
        return await self.upload_and_run(program)
    
    async def run_motor(self, port: str, speed: int = 50, duration_ms: int = 1000) -> bool:
        """Run a motor on specified port."""
        program = generate_motor_program(port, speed, duration_ms)
        return await self.upload_and_run(program)
    
    async def beep(self, frequency: int = 440, duration_ms: int = 500) -> bool:
        """
        Play a beep on the hub's built-in speaker.
        
        Args:
            frequency: Frequency in Hz (e.g., 440 = A4, 523 = C5, 880 = A5)
            duration_ms: Duration in milliseconds
        """
        program = generate_beep_program(frequency, duration_ms)
        return await self.upload_and_run(program)
    
    async def play_melody(self, melody_name: str) -> bool:
        """
        Play a predefined melody.
        
        Args:
            melody_name: One of: happy, sad, alert, success, error, startup
        """
        if melody_name not in MELODIES:
            print(f"Unknown melody: {melody_name}")
            return False
        program = generate_melody_program(MELODIES[melody_name])
        return await self.upload_and_run(program)
    
    async def stop(self) -> bool:
        """Stop the current program."""
        try:
            await self._send_request(
                ProgramFlowRequest(stop=True, slot=self.slot),
                ProgramFlowResponse
            )
            return True
        except:
            return False
    
    async def clear_display(self) -> bool:
        """Clear the LED matrix."""
        program = b"""from hub import light_matrix
light_matrix.clear()
"""
        return await self.upload_and_run(program)
    
    # Context manager support
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


# ============================================================
# Scanning
# ============================================================

async def scan_for_hubs(timeout: float = 10.0) -> list:
    """Scan for Spike Prime hubs."""
    print(f"Scanning for Spike Prime hubs ({timeout}s)...")
    
    found = []
    
    def callback(device, adv_data):
        if SERVICE_UUID.lower() in [u.lower() for u in (adv_data.service_uuids or [])]:
            if device.address not in [d.address for d in found]:
                found.append(device)
                print(f"  ★ Found: {device.name or '(unnamed)'} [{device.address}]")
    
    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    
    return found


# ============================================================
# Quick Test
# ============================================================

async def test():
    """Quick test of the interface."""
    # Scan for hubs
    hubs = await scan_for_hubs(5)
    
    if not hubs:
        print("No hubs found!")
        return
    
    hub = hubs[0]
    print(f"\nUsing: {hub.name} [{hub.address}]")
    
    async with SpikeInterface(hub.address, hub.name) as spike:
        print("\nShowing happy face...")
        await spike.show_display("happy")
        await asyncio.sleep(2)
        
        print("Playing happy melody...")
        await spike.play_melody("happy")
        await asyncio.sleep(1)
        
        print("Showing heart...")
        await spike.show_display("heart")
        await asyncio.sleep(2)
        
        print("Beeping...")
        await spike.beep(880, 200)  # High A
        await asyncio.sleep(1)
        
        print("Stopping...")
        await spike.stop()
        
        print("Done!")


if __name__ == "__main__":
    asyncio.run(test())
