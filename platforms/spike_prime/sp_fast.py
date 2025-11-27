#!/usr/bin/env python3
"""
Spike Prime Fast Interface
--------------------------
Low-latency control by pre-uploading programs to slots.

Strategy:
1. At connect: Upload action programs to slots 0-9
2. To execute: Just "start slot X" (~50ms vs ~600ms upload)
"""

import os
import sys
import asyncio
import time
from typing import Dict, Optional

# Add root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

from platforms.spike_prime.sp_interface import (
    SpikeInterface,
    crc, cobs,
    StartFileUploadRequest, StartFileUploadResponse,
    TransferChunkRequest, TransferChunkResponse,
    ClearSlotRequest, ClearSlotResponse,
    ProgramFlowRequest, ProgramFlowResponse,
    generate_beep_program,
    generate_display_program,
    PATTERNS,
)


# Import PATTERNS from sp_interface
from platforms.spike_prime.sp_interface import PATTERNS

# ============================================================
# Program Generators (Spike App 3 API)
# ============================================================
# Reference: lego_docs/examples/python/app.py
# 
# Spike App 3 API Rules:
# - sound.beep() requires AWAIT: `await sound.beep(freq, duration)`
# - light_matrix.write() requires AWAIT: `await light_matrix.write("text")`
# - light_matrix.set_pixel() is SYNC: `light_matrix.set_pixel(x, y, brightness)`
# - light_matrix.clear() is SYNC: `light_matrix.clear()`
# - Async functions need: `import runloop` + `runloop.run(main())`
# ============================================================


def _fast_beep(freq: int, dur: int) -> bytes:
    """
    Generate beep program. Sound API requires await.
    
    Args:
        freq: Frequency in Hz (e.g., 440=A4, 880=A5)
        dur: Duration in milliseconds
    """
    return f"""import runloop
from hub import sound

async def main():
    await sound.beep({freq}, {dur})

runloop.run(main())
""".encode("utf8")


def _fast_display(pattern_name: str) -> bytes:
    """
    Generate display program.
    
    - For patterns (happy, sad, etc.): Use sync set_pixel() with while loop
    - For text: Use async write()
    """
    if pattern_name not in PATTERNS:
        # Text - use async write
        return f"""import runloop
from hub import light_matrix

async def main():
    await light_matrix.write("{pattern_name}")

runloop.run(main())
""".encode("utf8")
    
    # Pattern - use sync set_pixel
    pixels = PATTERNS[pattern_name]
    pixel_code = "\n".join([
        f"light_matrix.set_pixel({x}, {y}, 100)"
        for x, y in pixels
    ])
    return f"""from hub import light_matrix
import time

light_matrix.clear()
{pixel_code}

# Keep display on
while True:
    time.sleep(1)
""".encode("utf8")


# Pre-defined action programs (uploaded to slots at connect)
# NOTE: Spike App 3 might use 0-100 scale (not 0-10 like Robot Inventor)
# NOTE: The startup chirp cannot be disabled programmatically (firmware-level)
ACTION_PROGRAMS = {
    "beep_high": b"""import runloop
from hub import sound
sound.volume(100)  # Max volume (trying 0-100 scale)

async def main():
    await sound.beep(880, 300)

runloop.run(main())
""",
    "beep_med": b"""import runloop
from hub import sound
sound.volume(100)

async def main():
    await sound.beep(440, 300)

runloop.run(main())
""",
    "beep_low": b"""import runloop
from hub import sound
sound.volume(100)

async def main():
    await sound.beep(220, 300)

runloop.run(main())
""",
    "beep_c": b"""import runloop
from hub import sound
sound.volume(100)

async def main():
    await sound.beep(523, 300)  # C5

runloop.run(main())
""",
    "beep_e": b"""import runloop
from hub import sound
sound.volume(100)

async def main():
    await sound.beep(659, 300)  # E5

runloop.run(main())
""",
    "beep_g": b"""import runloop
from hub import sound
sound.volume(100)

async def main():
    await sound.beep(784, 300)  # G5

runloop.run(main())
""",
    "happy": _fast_display("happy"),
    "sad": _fast_display("sad"),
    "heart": _fast_display("heart"),
    "neutral": _fast_display("neutral"),
    "angry": _fast_display("angry"),
    "surprised": _fast_display("surprised"),
    "check": _fast_display("check"),
    "clear": b"""from hub import light_matrix
light_matrix.clear()
""",
    "stop": b"""pass
""",
}

# Map action names to slot numbers
ACTION_SLOTS = {name: i for i, name in enumerate(ACTION_PROGRAMS.keys())}


class SpikeFastInterface(SpikeInterface):
    """
    Fast Spike Prime interface with pre-uploaded programs.
    
    Latency comparison:
    - Regular: ~600ms (upload + run)
    - Fast: ~50ms (just run pre-uploaded)
    """
    
    def __init__(self, address: str, name: str = "Spike Prime"):
        super().__init__(address, name, slot=0)
        self._programs_uploaded = False
        self._action_slots = {}
    
    async def connect(self, preload: bool = False) -> bool:
        """
        Connect to Spike Prime.
        
        Args:
            preload: If True, pre-upload action programs (causes melodies during upload).
                    If False (default), skip pre-upload to minimize melodies.
        """
        result = await super().connect()
        if result and preload:
            await self._preload_programs()
        elif result:
            # Mark as ready without pre-upload
            self._programs_uploaded = False
            print("[SpikeFast] Connected (no pre-upload = no melody yet)")
        return result
    
    async def _preload_programs(self) -> None:
        """Upload all action programs to slots."""
        print(f"[SpikeFast] Pre-uploading {len(ACTION_PROGRAMS)} programs...")
        
        t0 = time.time()
        
        for name, program in ACTION_PROGRAMS.items():
            slot = ACTION_SLOTS[name]
            try:
                await self._upload_to_slot(slot, program)
                self._action_slots[name] = slot
                print(f"  ✓ Slot {slot}: {name}")
            except Exception as e:
                print(f"  ✗ Slot {slot}: {name} - {e}")
        
        upload_time = (time.time() - t0) * 1000
        print(f"[SpikeFast] Pre-upload complete ({upload_time:.0f}ms)")
        self._programs_uploaded = True
    
    async def _upload_to_slot(self, slot: int, program: bytes) -> None:
        """Upload a program to a specific slot."""
        # Clear slot
        try:
            await self._send_request(ClearSlotRequest(slot), ClearSlotResponse)
        except:
            pass
        
        await asyncio.sleep(0.1)
        
        # Upload
        program_crc = crc(program)
        await self._send_request(
            StartFileUploadRequest("program.py", slot, program_crc),
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
    
    async def fast_action(self, action: str, wait_response: bool = False) -> float:
        """
        Execute a pre-uploaded action. Returns latency in ms.
        
        ⚠️ WARNING: Each call starts a new program = 1 MELODY!
        Use run_sequence() to batch multiple actions = 1 melody total.
        
        Args:
            action: Action name
            wait_response: If False, fire-and-forget (faster). If True, wait for ack.
        
        Available actions: beep_high, beep_med, beep_low, beep_c, beep_e, beep_g,
                          happy, sad, heart, neutral, angry, surprised, check, clear, stop
        """
        if not self._programs_uploaded:
            # Auto-upload this single action (causes 1 melody)
            return await self._run_single_action(action)
        
        if action not in self._action_slots:
            raise ValueError(f"Unknown action: {action}. Available: {list(self._action_slots.keys())}")
        
        slot = self._action_slots[action]
        
        t0 = time.time()
        
        if wait_response:
            await self._send_request(
                ProgramFlowRequest(stop=False, slot=slot),
                ProgramFlowResponse
            )
        else:
            await self._send_message(ProgramFlowRequest(stop=False, slot=slot))
        
        latency = (time.time() - t0) * 1000
        return latency
    
    async def _run_single_action(self, action: str) -> float:
        """Run a single action by uploading its program (causes 1 melody)."""
        t0 = time.time()
        
        if action in ACTION_PROGRAMS:
            program = ACTION_PROGRAMS[action]
        elif action.startswith("beep_"):
            # Parse beep_XXX where XXX is frequency
            freq = int(action.split("_")[1]) if action.split("_")[1].isdigit() else 440
            program = f"""import runloop
from hub import sound
sound.volume(100)
async def main():
    await sound.beep({freq}, 300)
runloop.run(main())
""".encode("utf8")
        else:
            raise ValueError(f"Unknown action: {action}")
        
        await self._upload_to_slot(18, program)
        await self._send_message(ProgramFlowRequest(stop=False, slot=18))
        
        return (time.time() - t0) * 1000
    
    # Convenience methods
    async def beep(self, pitch: str = "high") -> float:
        """Quick beep. pitch: high, med, low"""
        return await self.fast_action(f"beep_{pitch}")
    
    async def show(self, pattern: str) -> float:
        """Quick display. pattern: happy, sad, heart, neutral"""
        return await self.fast_action(pattern)
    
    async def run_sequence(self, actions: list, delay_ms: int = 100) -> float:
        """
        Run multiple actions in ONE program (only ONE startup melody).
        
        Args:
            actions: List of action tuples, e.g. [("beep", 880, 200), ("beep", 440, 200)]
            delay_ms: Delay between actions in ms
        
        Returns:
            Total latency in ms
        """
        # Generate program with all actions
        code_lines = [
            "import runloop",
            "from hub import sound, light_matrix",
            "import time",
            "sound.volume(100)",  # Max volume (0-100 scale for Spike App 3)
            "",
            "async def main():",
        ]
        
        for action in actions:
            if action[0] == "beep":
                freq = action[1] if len(action) > 1 else 440
                dur = action[2] if len(action) > 2 else 200
                code_lines.append(f"    await sound.beep({freq}, {dur})")
            elif action[0] == "display":
                text = action[1] if len(action) > 1 else "Hi"
                code_lines.append(f'    await light_matrix.write("{text}")')
            elif action[0] == "delay":
                ms = action[1] if len(action) > 1 else 100
                code_lines.append(f"    time.sleep({ms/1000})")
            
            if delay_ms > 0:
                code_lines.append(f"    time.sleep({delay_ms/1000})")
        
        code_lines.append("")
        code_lines.append("runloop.run(main())")
        
        program = "\n".join(code_lines).encode("utf8")
        
        t0 = time.time()
        
        # Upload and run
        await self._upload_to_slot(18, program)  # Use slot 18 for sequences
        await self._send_message(ProgramFlowRequest(stop=False, slot=18))
        
        latency = (time.time() - t0) * 1000
        return latency
    
    async def beep_sequence(self, count: int = 3, freq: int = 880, dur: int = 200, delay_ms: int = 300) -> float:
        """
        Play multiple beeps with only ONE startup melody.
        
        Args:
            count: Number of beeps
            freq: Frequency in Hz
            dur: Duration of each beep in ms
            delay_ms: Delay between beeps in ms
        """
        actions = [("beep", freq, dur) for _ in range(count)]
        return await self.run_sequence(actions, delay_ms=delay_ms)
    
    async def run_interactive_sequence(self, actions: list, on_action_done: callable = None) -> float:
        """
        Run actions with callbacks after each one - TRUE collaboration!
        
        Uses print() in Spike program + ConsoleNotification to signal completion.
        Host awaits each signal, then calls on_action_done() synchronously.
        
        Args:
            actions: List of action tuples [("beep", 880, 200), ...]
            on_action_done: Async callback called after each action completes
        
        Returns:
            Total latency in ms
        """
        # Generate program that prints "DONE:{n}" after each action
        # Add delay AFTER print to give EV3 time to respond before next beep
        code_lines = [
            "import runloop",
            "from hub import sound, light_matrix",
            "import time",
            "sound.volume(100)",
            "",
            "async def main():",
        ]
        
        for i, action in enumerate(actions):
            if action[0] == "beep":
                freq = action[1] if len(action) > 1 else 440
                dur = action[2] if len(action) > 2 else 200
                code_lines.append(f"    await sound.beep({freq}, {dur})")
            elif action[0] == "display":
                text = action[1] if len(action) > 1 else "Hi"
                code_lines.append(f'    await light_matrix.write("{text}")')
            
            # Print completion signal after each action
            code_lines.append(f'    print("DONE:{i}")')
            # Give EV3 time to respond before next action (1 second gap)
            code_lines.append(f"    time.sleep(1.0)")
        
        code_lines.append("")
        code_lines.append("runloop.run(main())")
        
        program = "\n".join(code_lines).encode("utf8")
        
        t0 = time.time()
        
        # Use queue for proper synchronization
        signal_queue = asyncio.Queue()
        
        # Set up console callback to queue signals
        def on_console(text: str):
            if "DONE:" in text:
                try:
                    idx = int(text.split("DONE:")[1].strip())
                    signal_queue.put_nowait(idx)
                except:
                    pass
        
        # Register callback
        self.set_console_callback(on_console)
        
        # Upload and run
        print(f"  [Spike] Uploading interactive program ({len(actions)} actions)...")
        await self._upload_to_slot(17, program)
        await self._send_message(ProgramFlowRequest(stop=False, slot=17))
        print(f"  [Spike] Program started, listening for signals...")
        
        # Wait for each signal and trigger callback
        completed = 0
        for i in range(len(actions)):
            try:
                idx = await asyncio.wait_for(signal_queue.get(), timeout=5.0)
                completed += 1
                print(f"  [Spike→Host] Signal: DONE:{idx}")
                
                if on_action_done:
                    await on_action_done(completed)  # AWAIT the callback!
                    
            except asyncio.TimeoutError:
                print(f"  [Spike] Timeout waiting for signal {i}")
                break
        
        # Clear callback
        self.set_console_callback(None)
        
        return (time.time() - t0) * 1000
    
    async def flow(self) -> None:
        """
        Interactive flow mode - type commands, see results.
        Similar to EV3 puppy flow mode.
        """
        print("=" * 50)
        print("SPIKE PRIME FLOW MODE")
        print("=" * 50)
        print()
        print("Sound commands:")
        print("  beep [high|med|low|c|e|g] - play beep")
        print()
        print("Display commands:")
        print("  happy/sad/angry/surprised - faces")
        print("  heart/neutral/check       - patterns")
        print("  clear                     - clear display")
        print()
        print("Other:")
        print("  status  - show available actions")
        print("  quit    - disconnect")
        print("-" * 50)
        
        while self._connected:
            try:
                cmd = input("\n> ").strip()
                
                if not cmd:
                    continue
                
                if cmd.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break
                
                if cmd.lower() == "status":
                    print(f"Available actions: {list(self._action_slots.keys())}")
                    continue
                
                if cmd.lower() == "help":
                    print("Commands: beep, happy, sad, heart, neutral, clear, stop, quit")
                    continue
                
                # Parse command and options
                parts = cmd.split()
                action = parts[0].lower()
                wait = "--wait" in parts
                
                # Handle beep with pitch
                if action == "beep":
                    pitch = "high"
                    for p in parts[1:]:
                        if p in ("high", "med", "low"):
                            pitch = p
                    action = f"beep_{pitch}"
                
                # Execute
                if action in self._action_slots:
                    t0 = time.time()
                    await self.fast_action(action, wait_response=wait)
                    latency = (time.time() - t0) * 1000
                    mode = "ack" if wait else "fire"
                    print(f"[Spike] OK: {action} ({latency:.0f}ms, {mode})")
                else:
                    print(f"Unknown: {action}. Try: {list(self._action_slots.keys())}")
                    
            except KeyboardInterrupt:
                print("\n\nInterrupted.")
                break
            except EOFError:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"[Error] {e}")


# ============================================================
# Test
# ============================================================

async def test_fast():
    """Test fast interface latency."""
    print("=" * 60)
    print("SPIKE FAST INTERFACE TEST")
    print("=" * 60)
    
    ADDRESS = "E1BDF5C6-C666-4E77-A7E8-458FC0A9F809"
    NAME = "Avatar Karo"
    
    async with SpikeFastInterface(ADDRESS, NAME) as spike:
        print()
        print("Testing latency (pre-uploaded programs):")
        print("-" * 40)
        
        # Test multiple beeps
        latencies = []
        for i in range(5):
            lat = await spike.beep("high")
            latencies.append(lat)
            print(f"  beep {i+1}: {lat:.0f}ms")
            await asyncio.sleep(0.3)
        
        avg = sum(latencies) / len(latencies)
        print(f"\nAverage latency: {avg:.0f}ms")
        
        print()
        print("Testing display:")
        for pattern in ["happy", "heart", "sad", "neutral"]:
            lat = await spike.show(pattern)
            print(f"  {pattern}: {lat:.0f}ms")
            await asyncio.sleep(1)
        
        await spike.fast_action("clear")
    
    print()
    print("✓ Test complete!")


async def benchmark():
    """Compare fast vs regular interface."""
    print("=" * 60)
    print("BENCHMARK: Regular vs Fast (with response) vs Fire-and-Forget")
    print("=" * 60)
    
    ADDRESS = "E1BDF5C6-C666-4E77-A7E8-458FC0A9F809"
    NAME = "Avatar Karo"
    
    # Test regular interface
    print("\n[1] Regular Interface (upload each time)")
    regular_times = []
    async with SpikeInterface(ADDRESS, NAME) as spike:
        for i in range(3):
            t0 = time.time()
            await spike.beep(880, 150)
            lat = (time.time() - t0) * 1000
            regular_times.append(lat)
            print(f"  beep {i+1}: {lat:.0f}ms")
            await asyncio.sleep(0.5)
    
    await asyncio.sleep(1)
    
    # Test fast interface with response
    print("\n[2] Fast Interface (pre-upload, wait response)")
    fast_times = []
    async with SpikeFastInterface(ADDRESS, NAME) as spike:
        await spike.fast_action("stop", wait_response=True)
        await asyncio.sleep(0.3)
        
        for i in range(5):
            lat = await spike.fast_action("beep_high", wait_response=True)
            fast_times.append(lat)
            print(f"  beep {i+1}: {lat:.0f}ms")
            await asyncio.sleep(0.5)
    
    await asyncio.sleep(1)
    
    # Test fire-and-forget
    print("\n[3] Fire-and-Forget (no response wait)")
    fire_times = []
    async with SpikeFastInterface(ADDRESS, NAME) as spike:
        await asyncio.sleep(0.3)
        
        for i in range(5):
            lat = await spike.fast_action("beep_high", wait_response=False)
            fire_times.append(lat)
            print(f"  beep {i+1}: {lat:.0f}ms")
            await asyncio.sleep(0.5)
    
    print()
    print("=" * 60)
    print(f"Regular avg:        {sum(regular_times)/len(regular_times):.0f}ms")
    print(f"Fast (wait) avg:    {sum(fast_times)/len(fast_times):.0f}ms")
    print(f"Fire-forget avg:    {sum(fire_times)/len(fire_times):.0f}ms")
    print("-" * 60)
    reg_avg = sum(regular_times)/len(regular_times)
    print(f"Fast speedup:       {reg_avg / (sum(fast_times)/len(fast_times)):.1f}x")
    print(f"Fire-forget speedup: {reg_avg / (sum(fire_times)/len(fire_times)):.1f}x")
    print("=" * 60)


async def flow_mode():
    """Run interactive flow mode."""
    ADDRESS = "E1BDF5C6-C666-4E77-A7E8-458FC0A9F809"
    NAME = "Avatar Karo"
    
    async with SpikeFastInterface(ADDRESS, NAME) as spike:
        await spike.flow()
    
    print("✓ Disconnected")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "benchmark":
            asyncio.run(benchmark())
        elif sys.argv[1] == "flow":
            asyncio.run(flow_mode())
        else:
            print("Usage: python sp_fast.py [flow|benchmark]")
    else:
        asyncio.run(test_fast())

