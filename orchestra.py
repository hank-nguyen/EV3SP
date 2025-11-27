#!/usr/bin/env python3
"""
🎼 Orchestra - LEGO Robotics Interactive Shell
===============================================

Unified terminal for controlling EV3 and Spike Prime robots.

Usage:
    # Interactive shell (connect manually)
    python orchestra.py
    
    # Connect to EV3 on startup
    python orchestra.py --ev3 192.168.68.111
    
    # Connect to Spike Prime on startup
    python orchestra.py --spike E1BDF5C6-C666-4E77-A7E8-458FC0A9F809 --spike-name "Avatar Karo"
    
    # Connect to both
    python orchestra.py --ev3 192.168.68.111 --spike E1BDF5C6-... --spike-name "Avatar Karo"
    
    # Use config file
    python orchestra.py --config projects/orchestra/configs/config.yaml

Inside the shell:
    ev3 beep           # Beep on EV3
    sp display heart   # Show heart on Spike Prime
    all status         # Get status from all devices
    beep high          # Beep on all devices
    help               # Show all commands
    quit               # Exit

Examples:
    [ev3 sp] ⚡ ev3 bark
      ev3: OK (32ms)
    
    [ev3 sp] ⚡ sp display happy
      sp: OK (15ms)
    
    [ev3 sp] ⚡ all beep
      ev3: OK (28ms)
      sp: OK (12ms)
"""

import os
import sys
import asyncio
import argparse

# Add root to path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)


def parse_args():
    """Parse command line arguments (before async to handle --help cleanly)."""
    parser = argparse.ArgumentParser(
        description="🎼 Orchestra - LEGO Robotics Interactive Shell",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --ev3 192.168.68.111
  %(prog)s --spike E1BDF5C6-... --spike-name "Avatar Karo"
  %(prog)s --ev3 192.168.68.111 --spike E1BDF5C6-... --spike-name "Avatar Karo"
        """
    )
    
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml"
    )
    
    parser.add_argument(
        "--ev3",
        metavar="HOST",
        help="EV3 hostname or IP address"
    )
    
    parser.add_argument(
        "--spike",
        metavar="ADDRESS",
        help="Spike Prime BLE address"
    )
    
    parser.add_argument(
        "--spike-name",
        default="Spike Prime",
        metavar="NAME",
        help="Spike Prime hub name (default: 'Spike Prime')"
    )
    
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Skip the ASCII banner"
    )
    
    return parser.parse_args()


async def main(args):
    """Main entry point."""
    from core.shell import OrchestraShell, Colors, colored
    
    # Create shell
    shell = OrchestraShell(args.config)
    
    if args.no_banner:
        shell.BANNER = ""
    
    # Connect to specified devices
    if args.config:
        # Load from config
        print(colored("[Orchestra] Loading from config...", Colors.CYAN))
        # TODO: Implement config loading
        await shell.connect(
            ev3_host=args.ev3,
            spike_address=args.spike,
            spike_name=args.spike_name,
        )
    elif args.ev3 or args.spike:
        await shell.connect(
            ev3_host=args.ev3,
            spike_address=args.spike,
            spike_name=args.spike_name,
        )
    
    # Run interactive loop
    await shell.run()


if __name__ == "__main__":
    # Parse args BEFORE async (handles --help without async issues)
    args = parse_args()
    
    # Now run async
    from core.utils import run_async_with_cleanup
    run_async_with_cleanup(
        main(args),
        cleanup_message="[Orchestra] Shutting down...",
        done_message="[Orchestra] Goodbye! 🎼"
    )

