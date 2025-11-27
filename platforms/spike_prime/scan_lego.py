#!/usr/bin/env python3
"""Scan for LEGO hubs - searches by name and service UUID."""

import asyncio
from bleak import BleakScanner

# LEGO Wireless Protocol 3.0 Service UUID
LEGO_SERVICE_UUID = "00001623-1212-efde-1623-785feabcd123"

# Known hub names (add your custom names here)
KNOWN_NAMES = [
    "LEGO Hub", "LEGO Technic Hub", "Pybricks Hub", 
    "SPIKE Prime Hub", "Avatar Karo",  # Your hub!
]

async def scan_lego():
    print("Scanning for LEGO hubs (15 seconds)...")
    print(f"Looking for names: {KNOWN_NAMES}")
    print()
    
    found_lego = []
    
    def detection_callback(device, advertisement_data):
        name = device.name or ""
        service_uuids = [u.lower() for u in (advertisement_data.service_uuids or [])]
        
        # Match by name OR service UUID
        is_lego = (
            any(known in name for known in KNOWN_NAMES) or
            LEGO_SERVICE_UUID.lower() in service_uuids or
            "avatar" in name.lower() or
            "karo" in name.lower()
        )
        
        if is_lego and device.address not in [d.address for d in found_lego]:
            found_lego.append(device)
            print(f"  ★ Found: {name or '(unnamed)'} [{device.address}]")
    
    scanner = BleakScanner(detection_callback=detection_callback)
    
    await scanner.start()
    await asyncio.sleep(15)
    await scanner.stop()
    
    print()
    if found_lego:
        print(f"=== Found {len(found_lego)} LEGO hub(s) ===")
        for d in found_lego:
            print(f"  {d.name or '(unnamed)':<25} {d.address}")
        return found_lego
    else:
        print("❌ No LEGO hubs found via BLE scan.")
        print()
        print("Note: Spike App 3 firmware may not broadcast via BLE.")
        print("The hub connects to the app, but may not be discoverable by Python.")
    
    return []

if __name__ == "__main__":
    asyncio.run(scan_lego())
