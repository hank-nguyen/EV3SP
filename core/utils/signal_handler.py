#!/usr/bin/env python3
"""
Signal Handler Utilities
------------------------
Graceful Ctrl+C handling for async programs.
Ensures cleanup (e.g., EV3 returns to menu) on interrupt.

Usage:
    from core.utils import run_async_with_cleanup
    
    async def main():
        async with SomeResource() as resource:
            # do work
            pass
    
    if __name__ == "__main__":
        run_async_with_cleanup(main())

Or with explicit cleanup:

    from core.utils import AsyncCleanupContext
    
    async def main():
        ctx = AsyncCleanupContext()
        conductor = Conductor()
        ctx.register(conductor.disconnect_all)
        
        try:
            await conductor.connect_all()
            # do work
        finally:
            await ctx.cleanup()
    
    if __name__ == "__main__":
        run_async_with_cleanup(main())
"""

import asyncio
import signal
import sys
from typing import Callable, Coroutine, Any, List, Optional


class AsyncCleanupContext:
    """
    Context for registering cleanup functions that run on interrupt.
    
    Usage:
        ctx = AsyncCleanupContext()
        ctx.register(my_cleanup_func)  # async or sync
        
        # Later, on interrupt:
        await ctx.cleanup()
    """
    
    def __init__(self):
        self._cleanups: List[Callable] = []
        self._cleaned = False
    
    def register(self, cleanup_func: Callable):
        """Register a cleanup function (async or sync)."""
        self._cleanups.append(cleanup_func)
    
    async def cleanup(self):
        """Run all registered cleanup functions."""
        if self._cleaned:
            return
        self._cleaned = True
        
        for func in reversed(self._cleanups):
            try:
                result = func()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"[Cleanup Error] {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


def run_async_with_cleanup(
    coro: Coroutine,
    cleanup_message: str = "[Interrupted] Cleaning up...",
    done_message: str = "[Done] Cleanup complete"
) -> Any:
    """
    Run an async coroutine with proper Ctrl+C handling.
    
    Ensures that:
    1. SIGINT (Ctrl+C) cancels the task gracefully
    2. Async context managers have their __aexit__ called
    3. Resources are cleaned up properly
    
    Args:
        coro: The async coroutine to run
        cleanup_message: Message to print when interrupted
        done_message: Message to print after cleanup
    
    Returns:
        The result of the coroutine, or None if interrupted
    
    Usage:
        async def main():
            async with Conductor() as conductor:
                # work here
                pass
        
        if __name__ == "__main__":
            run_async_with_cleanup(main())
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    main_task = loop.create_task(coro)
    
    def handle_sigint():
        print(f"\n{cleanup_message}")
        main_task.cancel()
    
    # Register signal handler
    try:
        loop.add_signal_handler(signal.SIGINT, handle_sigint)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        pass
    
    result = None
    try:
        result = loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        # Task was cancelled by signal handler
        # Cleanup should have happened in __aexit__ or finally blocks
        print(done_message)
    except KeyboardInterrupt:
        # Fallback for platforms without signal handlers
        print(f"\n{cleanup_message}")
        main_task.cancel()
        try:
            loop.run_until_complete(main_task)
        except asyncio.CancelledError:
            pass
        print(done_message)
    finally:
        # Cleanup any remaining tasks
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except:
            pass
        loop.close()
    
    return result


# Convenience function for simple scripts
def setup_interrupt_handler(cleanup_func: Callable = None):
    """
    Setup a basic interrupt handler for sync code.
    
    Args:
        cleanup_func: Optional function to call on interrupt
    
    Usage:
        def cleanup():
            print("Cleaning up...")
        
        setup_interrupt_handler(cleanup)
        
        # Your code here
    """
    def handler(signum, frame):
        print("\n[Interrupted]")
        if cleanup_func:
            try:
                cleanup_func()
            except:
                pass
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handler)

