"""
Collaboration Patterns
----------------------
Patterns for real-time collaboration between multiple robots.

Key insight: Spike Prime can only receive commands when NO program is running.
Once a program starts, we can't send new commands. Starting a new program = melody.

Solutions:
1. Batch all Spike actions into ONE program → 1 melody total
2. Use print() in Spike + ConsoleNotification for signaling → enables real collaboration
3. Use asyncio.Queue for proper synchronization between robots
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Callable, Optional, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class Signal:
    """A signal from one robot to the orchestrator."""
    source: str          # Robot name
    action_index: int    # Which action just completed
    data: Any = None     # Optional payload


class SignalQueue:
    """
    Thread-safe async queue for robot signals.
    
    Usage:
        queue = SignalQueue()
        
        # Producer (in callback from robot):
        queue.put(Signal("spike", 0))
        
        # Consumer (in main orchestration):
        signal = await queue.wait(timeout=5.0)
    """
    
    def __init__(self):
        self._queue = asyncio.Queue()
    
    def put(self, signal: Signal) -> None:
        """Put a signal into the queue (non-blocking, thread-safe)."""
        try:
            self._queue.put_nowait(signal)
        except asyncio.QueueFull:
            pass  # Drop if full (shouldn't happen)
    
    async def wait(self, timeout: float = 5.0) -> Optional[Signal]:
        """Wait for a signal with timeout. Returns None on timeout."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
    
    def clear(self) -> None:
        """Clear all pending signals."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class CollaborationPattern(ABC):
    """
    Abstract base for collaboration patterns.
    
    A collaboration pattern defines how multiple robots coordinate their actions.
    """
    
    @abstractmethod
    async def execute(self, robots: dict, actions: List[Tuple[str, str, tuple]]) -> float:
        """
        Execute the collaboration pattern.
        
        Args:
            robots: Dict of robot_name -> interface
            actions: List of (robot_name, action_name, args)
        
        Returns:
            Total execution time in ms
        """
        pass


class ParallelPattern(CollaborationPattern):
    """
    Run all actions in parallel, no coordination.
    
    Best for: Independent actions that don't need synchronization.
    Latency: Lowest (all start at once).
    
    Timeline:
        Robot A: [action 1] [action 2] [action 3]
        Robot B: [action 1] [action 2] [action 3]
                 ↑ both start at same time
    """
    
    async def execute(self, robots: dict, actions: List[Tuple[str, str, tuple]]) -> float:
        import time
        t0 = time.time()
        
        async def run_action(robot_name: str, action: str, args: tuple):
            robot = robots.get(robot_name)
            if robot and hasattr(robot, action):
                method = getattr(robot, action)
                if asyncio.iscoroutinefunction(method):
                    return await method(*args)
                else:
                    return method(*args)
        
        tasks = [run_action(r, a, args) for r, a, args in actions]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return (time.time() - t0) * 1000


class ChoreographedPattern(CollaborationPattern):
    """
    Pre-timed alternation using built-in delays.
    
    Best for: When you know exact timing, no runtime signals needed.
    Latency: Medium (delays are fixed, not adaptive).
    
    Timeline:
        Robot A: [beep]----[beep]----[beep]
        Robot B: ----[woof]----[woof]----[woof]
                 (timing pre-calculated)
    """
    
    def __init__(self, gap_ms: int = 500):
        self.gap_ms = gap_ms
    
    async def execute(self, robots: dict, actions: List[Tuple[str, str, tuple]]) -> float:
        import time
        t0 = time.time()
        
        # Group actions by robot
        by_robot = {}
        for robot_name, action, args in actions:
            if robot_name not in by_robot:
                by_robot[robot_name] = []
            by_robot[robot_name].append((action, args))
        
        # Create choreographed tasks with staggered timing
        async def run_with_offset(robot_name: str, actions: list, offset_ms: int):
            await asyncio.sleep(offset_ms / 1000)
            robot = robots.get(robot_name)
            for action, args in actions:
                if robot and hasattr(robot, action):
                    method = getattr(robot, action)
                    if asyncio.iscoroutinefunction(method):
                        await method(*args)
                    else:
                        method(*args)
                await asyncio.sleep(self.gap_ms / 1000)
        
        # Stagger starts
        tasks = []
        offset = 0
        for robot_name, robot_actions in by_robot.items():
            tasks.append(run_with_offset(robot_name, robot_actions, offset))
            offset += self.gap_ms // 2  # Half-gap stagger
        
        await asyncio.gather(*tasks)
        
        return (time.time() - t0) * 1000


class SignalBasedPattern(CollaborationPattern):
    """
    True real-time collaboration using signals.
    
    Best for: When Robot A must wait for Robot B to complete before continuing.
    Latency: Highest (waits for actual completion), but most accurate.
    
    How it works:
    1. Robot A does action, signals "DONE"
    2. Host receives signal, tells Robot B to act
    3. Robot B completes, repeat
    
    Timeline:
        Robot A: [beep]→signal→[beep]→signal→[beep]→signal
        Robot B:       ←signal←[woof]←signal←[woof]←signal←[woof]
                 (real-time coordination)
    """
    
    def __init__(self, signal_queue: SignalQueue = None):
        self.signal_queue = signal_queue or SignalQueue()
    
    async def execute(self, robots: dict, actions: List[Tuple[str, str, tuple]]) -> float:
        import time
        t0 = time.time()
        
        # This is the pattern used in run_interactive_sequence
        # Actual implementation depends on platform capabilities
        
        for robot_name, action, args in actions:
            robot = robots.get(robot_name)
            if robot and hasattr(robot, action):
                method = getattr(robot, action)
                if asyncio.iscoroutinefunction(method):
                    await method(*args)
                else:
                    method(*args)
            
            # Wait for signal if needed
            signal = await self.signal_queue.wait(timeout=5.0)
            if signal:
                # Could trigger follow-up actions here
                pass
        
        return (time.time() - t0) * 1000


def create_batched_program(actions: List[Tuple[str, Any]], platform: str = "spike") -> str:
    """
    Create a single program that executes multiple actions.
    
    Key insight: 1 program = 1 startup melody (Spike Prime).
    Batching reduces total melodies to 1.
    
    Args:
        actions: List of (action_type, *args) tuples
        platform: "spike" or "ev3"
    
    Returns:
        Program code as string
    """
    if platform == "spike":
        lines = [
            "import runloop",
            "from hub import sound, light_matrix",
            "import time",
            "sound.volume(100)",
            "",
            "async def main():",
        ]
        
        for i, action in enumerate(actions):
            action_type = action[0]
            
            if action_type == "beep":
                freq = action[1] if len(action) > 1 else 440
                dur = action[2] if len(action) > 2 else 200
                lines.append(f"    await sound.beep({freq}, {dur})")
            
            elif action_type == "display":
                text = action[1] if len(action) > 1 else "Hi"
                lines.append(f'    await light_matrix.write("{text}")')
            
            elif action_type == "delay":
                ms = action[1] if len(action) > 1 else 100
                lines.append(f"    time.sleep({ms / 1000})")
            
            elif action_type == "signal":
                # Print for ConsoleNotification
                lines.append(f'    print("DONE:{i}")')
                lines.append(f"    time.sleep(0.1)")  # BLE transmission delay
        
        lines.append("")
        lines.append("runloop.run(main())")
        
        return "\n".join(lines)
    
    else:
        raise NotImplementedError(f"Platform {platform} not supported")

