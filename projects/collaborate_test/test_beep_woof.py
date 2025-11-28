#!/usr/bin/env python3
"""
Collaborate Test: SP beep beep beep + EV3 woof woof woof
--------------------------------------------------------
Parallel control of Spike Prime and EV3 with lowest latency.

Usage:
    python test_beep_woof.py           # Default test
    python test_beep_woof.py --sync    # Synchronized (same time)
    python test_beep_woof.py --seq     # Sequential (alternating)
"""

import os
import sys
import asyncio
import time
import argparse

# Add root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

from collaborate_test import Conductor
from core.utils import run_async_with_cleanup

# Absolute path to this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "configs/config.yaml")


async def test_parallel():
    """
    Test: Run SP beeps and EV3 woofs in parallel.
    ALL Spike actions in ONE program = 1 MELODY ONLY!
    """
    print("=" * 60)
    print("COLLABORATE TEST: Parallel SP beep + EV3 woof")
    print("=" * 60)
    print("Strategy: ALL Spike beeps in ONE program = 1 melody!")
    
    async with Conductor.from_config(CONFIG_PATH) as conductor:
        print("\n[Test] Starting parallel sequences...")
        print("-" * 60)
        
        t0 = time.time()
        
        # Run ALL actions in parallel - Spike batches all beeps
        await asyncio.gather(
            spike_all_beeps(conductor, rounds=1, beeps_per_round=3),
            ev3_woofs(conductor, count=3),
        )
        
        total = (time.time() - t0) * 1000
        print("-" * 60)
        print(f"Total time: {total:.0f}ms")
        print("✓ Only 1 melody played!")
    
    print("\n✓ Test complete!")


async def test_synchronized():
    """
    Test: 3 rounds of synchronized beeps + woofs.
    ALL Spike beeps in ONE program = ONLY 1 MELODY TOTAL!
    """
    print("=" * 60)
    print("COLLABORATE TEST: 3 Rounds of Synchronized beep + woof")
    print("=" * 60)
    
    async with Conductor.from_config(CONFIG_PATH) as conductor:
        print("\n[Test] Strategy: 1 MELODY TOTAL")
        print("  - Spike: ALL 9 beeps in ONE program (uploaded once)")
        print("  - EV3: 9 barks via daemon")
        print("-" * 60)
        
        total_t0 = time.time()
        
        # Run ALL beeps in parallel with ALL woofs
        # Spike: 9 beeps total (3 rounds × 3 beeps) = 1 melody only!
        await asyncio.gather(
            spike_all_beeps(conductor, rounds=3, beeps_per_round=3),
            ev3_all_woofs(conductor, rounds=3, woofs_per_round=3),
        )
        
        total = (time.time() - total_t0) * 1000
        print("-" * 60)
        print(f"Total time: {total:.0f}ms")
        print("✓ Only 1 melody played!")
    
    print("\n✓ Test complete!")


async def spike_all_beeps(conductor: Conductor, rounds: int = 3, beeps_per_round: int = 3):
    """
    All Spike beeps in ONE program = 1 melody only!
    """
    total_beeps = rounds * beeps_per_round
    
    # Build all beeps with pauses between rounds
    actions = []
    for r in range(rounds):
        for b in range(beeps_per_round):
            actions.append(("beep", 880, 200))
        if r < rounds - 1:
            actions.append(("delay", 500))  # Pause between rounds
    
    print(f"  [Spike] Uploading {total_beeps} beeps as ONE program...")
    t0 = time.time()
    
    state = conductor.devices.get("spike")
    if state and state.connected:
        latency = await state.interface.run_sequence(actions, delay_ms=200)
        print(f"  [Spike] All {total_beeps} beeps done: {latency:.0f}ms (1 melody!)")


async def ev3_all_woofs(conductor: Conductor, rounds: int = 3, woofs_per_round: int = 3):
    """All EV3 woofs via daemon."""
    total_woofs = rounds * woofs_per_round
    
    for r in range(rounds):
        for w in range(woofs_per_round):
            t0 = time.time()
            await conductor.send("ev3", "bark")
            latency = (time.time() - t0) * 1000
            print(f"  [EV3] woof {r*woofs_per_round + w + 1}/{total_woofs}: {latency:.0f}ms")
            await asyncio.sleep(0.2)
        
        if r < rounds - 1:
            await asyncio.sleep(0.3)  # Pause between rounds


async def test_sequential():
    """
    Test: TRUE alternating beep/woof with REAL COLLABORATION!
    
    Technique: Spike signals completion via print(), host triggers EV3
    - Spike beeps → print("DONE") → host receives → tells EV3 to bark
    - Result: REAL beep-woof-beep-woof alternation with 1 melody!
    """
    print("=" * 60)
    print("COLLABORATE TEST: REAL Collaboration (1 melody!)")
    print("=" * 60)
    print("Technique: Spike signals completion, host triggers EV3")
    print("  Spike beeps → signals DONE → Host → EV3 barks")
    print("  Result: TRUE alternating beep-woof-beep-woof")
    
    async with Conductor.from_config(CONFIG_PATH) as conductor:
        print("\n[Test] Starting real collaboration...")
        print("-" * 60)
        
        t0 = time.time()
        beep_count = [0]
        
        async def on_beep_done(n):
            """Called after each Spike beep completes."""
            beep_count[0] = n
            print(f"  [Spike] Beep {n} done, triggering EV3...")
            t1 = time.time()
            await conductor.send("ev3", "bark")
            latency = (time.time() - t1) * 1000
            print(f"  [EV3] Woof {n}: {latency:.0f}ms")
        
        # Run interactive sequence - Spike beeps, host triggers EV3 after each
        state = conductor.devices.get("spike")
        if state and state.connected:
            actions = [("beep", 880, 200) for _ in range(3)]
            await state.interface.run_interactive_sequence(actions, on_beep_done)
        
        total = (time.time() - t0) * 1000
        print("-" * 60)
        print(f"Total time: {total:.0f}ms")
        print(f"✓ Only 1 melody, {beep_count[0]} real alternations!")
    
    print("\n✓ Test complete!")


async def ev3_woofs(conductor: Conductor, count: int = 3):
    """EV3: woof woof woof via daemon (no melody issue)."""
    for i in range(count):
        t0 = time.time()
        await conductor.send("ev3", "bark")
        latency = (time.time() - t0) * 1000
        print(f"  [EV3] woof {i+1}: {latency:.0f}ms")
        await asyncio.sleep(0.3)


async def main():
    parser = argparse.ArgumentParser(description="Collaborate test beep/woof")
    parser.add_argument("--sync", action="store_true", help="Synchronized test")
    parser.add_argument("--seq", action="store_true", help="Sequential test")
    args = parser.parse_args()
    
    if args.sync:
        await test_synchronized()
    elif args.seq:
        await test_sequential()
    else:
        await test_parallel()


if __name__ == "__main__":
    run_async_with_cleanup(
        main(),
        cleanup_message="[Interrupted] Cleaning up (EV3 → menu)...",
        done_message="[Done] Cleanup complete"
    )

