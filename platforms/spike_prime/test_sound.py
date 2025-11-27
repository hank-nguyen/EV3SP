#!/usr/bin/env python3
"""
Spike Prime API Reference Tests
-------------------------------
Tests the correct Spike App 3 APIs.

Reference: lego_docs/examples/python/app.py

Key findings:
- sound.beep() requires AWAIT
- light_matrix.write() requires AWAIT  
- light_matrix.set_pixel() is SYNC
- light_matrix.clear() is SYNC
"""

import os
import sys
import asyncio
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

from platforms.spike_prime.sp_interface import SpikeInterface

ADDRESS = "E1BDF5C6-C666-4E77-A7E8-458FC0A9F809"
NAME = "Avatar Karo"

# Working API examples
TESTS = [
    ("sound_beep_await", b"""import runloop
from hub import sound

async def main():
    await sound.beep(880, 500)  # MUST use await

runloop.run(main())
"""),

    ("sound_melody", b"""import runloop
from hub import sound

async def main():
    await sound.beep(523, 200)  # C
    await sound.beep(659, 200)  # E
    await sound.beep(784, 200)  # G

runloop.run(main())
"""),

    ("display_setpixel_sync", b"""from hub import light_matrix
import time

light_matrix.clear()
# set_pixel is SYNC (no await)
for i in range(5):
    light_matrix.set_pixel(i, i, 100)
    light_matrix.set_pixel(4-i, i, 100)

while True:
    time.sleep(1)
"""),

    ("display_write_await", b"""import runloop
from hub import light_matrix

async def main():
    await light_matrix.write("HI")  # MUST use await

runloop.run(main())
"""),
]


async def main():
    print("=" * 60)
    print("SPIKE PRIME API REFERENCE TESTS")
    print("=" * 60)
    print("Reference: lego_docs/examples/python/app.py")
    print()
    
    async with SpikeInterface(ADDRESS, NAME) as spike:
        for name, program in TESTS:
            print(f"\n{'='*50}")
            print(f"TEST: {name}")
            print(f"{'='*50}")
            print(program.decode())
            
            input("Press Enter to run...")
            
            t0 = time.time()
            await spike.upload_and_run(program)
            lat = (time.time() - t0) * 1000
            print(f"✓ Uploaded & started ({lat:.0f}ms)")
            
            await asyncio.sleep(2)
            
            # Stop before next test
            try:
                await spike.stop()
            except:
                pass
            await asyncio.sleep(0.3)
    
    print("\n" + "=" * 60)
    print("All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

