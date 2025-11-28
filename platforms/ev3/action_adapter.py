#!/usr/bin/env python3
"""
EV3 Action Adapter
------------------
Translates high-level project actions to generic daemon commands.

This adapter sits between projects and the daemon, allowing:
- Projects to define actions in YAML files
- Automatic translation to low-level motor/sensor commands
- No project-specific code in the daemon

Architecture:
    Project (puppy.py)      Action Adapter           Daemon
    ─────────────────      ──────────────           ──────
    execute("sitdown") ──► load actions.yaml ──► [motor D -25, motor A -25, stop]
                           translate action         send each command

Usage:
    # Load actions from YAML
    adapter = ActionAdapter.from_yaml("projects/puppy/configs/actions.yaml")
    
    # Or define inline
    adapter = ActionAdapter({
        "sitdown": [("eyes sleepy", 0), ("motor D -25", 0), ("stop", 0)],
    })
    
    # Translate action to commands
    commands = adapter.translate("sitdown")
    # Returns: [("eyes sleepy", 0), ("motor D -25", 0), ("stop", 0)]
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Callable, Any

# Optional YAML support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class ActionStep:
    """Single step in an action sequence."""
    command: str        # Daemon command (e.g., "motor D -25")
    delay_ms: int = 0   # Delay after this command (ms)


@dataclass
class ActionDefinition:
    """Definition of a high-level action."""
    name: str
    steps: List[ActionStep]
    description: str = ""


class ActionAdapter:
    """
    Translates high-level actions to daemon command sequences.
    
    Supports loading from:
    - Python dict
    - YAML file
    - JSON file
    """
    
    def __init__(self, actions: Optional[Dict[str, List[Tuple[str, int]]]] = None):
        """
        Initialize with action definitions.
        
        Args:
            actions: Dict mapping action names to list of (command, delay_ms) tuples
        """
        self._actions: Dict[str, ActionDefinition] = {}
        
        if actions:
            for name, steps in actions.items():
                self.register(name, steps)
    
    def register(self, name: str, steps: List[Tuple[str, int]], description: str = ""):
        """
        Register an action.
        
        Args:
            name: Action name (e.g., "sitdown")
            steps: List of (command, delay_ms) tuples
            description: Human-readable description
        """
        action_steps = [ActionStep(cmd, delay) for cmd, delay in steps]
        self._actions[name] = ActionDefinition(name, action_steps, description)
    
    def translate(self, action: str) -> Optional[List[Tuple[str, int]]]:
        """
        Translate action to command sequence.
        
        Args:
            action: Action name
            
        Returns:
            List of (command, delay_ms) tuples, or None if unknown action
        """
        if action not in self._actions:
            return None
        
        return [(step.command, step.delay_ms) for step in self._actions[action].steps]
    
    def has_action(self, action: str) -> bool:
        """Check if action is registered."""
        return action in self._actions
    
    def list_actions(self) -> List[str]:
        """List all registered action names."""
        return list(self._actions.keys())
    
    def get_description(self, action: str) -> str:
        """Get action description."""
        if action in self._actions:
            return self._actions[action].description
        return ""
    
    @classmethod
    def from_yaml(cls, path: str) -> "ActionAdapter":
        """
        Load actions from YAML file.
        
        YAML format:
            actions:
              sitdown:
                description: "Sit down"
                steps:
                  - command: "eyes sleepy"
                    delay: 0
                  - command: "motor D -25"
                    delay: 0
                  - command: "motor A -25"
                    delay: 800
                  - command: "stop"
                    delay: 0
        
        Or simple format:
            actions:
              sitdown:
                - ["eyes sleepy", 0]
                - ["motor D -25", 0]
                - ["motor A -25", 800]
                - ["stop", 0]
        """
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML required for YAML loading: pip install pyyaml")
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        adapter = cls()
        
        actions_data = data.get('actions', data)  # Support root-level or under 'actions'
        
        for name, definition in actions_data.items():
            if isinstance(definition, list):
                # Simple format: list of [command, delay] arrays
                steps = []
                for item in definition:
                    if isinstance(item, list) and len(item) >= 1:
                        cmd = item[0]
                        delay = item[1] if len(item) > 1 else 0
                        steps.append((cmd, delay))
                    elif isinstance(item, dict):
                        cmd = item.get('command', item.get('cmd', ''))
                        delay = item.get('delay', item.get('delay_ms', 0))
                        steps.append((cmd, delay))
                adapter.register(name, steps)
            elif isinstance(definition, dict):
                # Full format with description
                description = definition.get('description', '')
                steps_data = definition.get('steps', [])
                steps = []
                for item in steps_data:
                    if isinstance(item, list) and len(item) >= 1:
                        cmd = item[0]
                        delay = item[1] if len(item) > 1 else 0
                        steps.append((cmd, delay))
                    elif isinstance(item, dict):
                        cmd = item.get('command', item.get('cmd', ''))
                        delay = item.get('delay', item.get('delay_ms', 0))
                        steps.append((cmd, delay))
                adapter.register(name, steps, description)
        
        return adapter
    
    @classmethod
    def from_dict(cls, actions: Dict[str, List[Tuple[str, int]]]) -> "ActionAdapter":
        """Create adapter from dictionary."""
        return cls(actions)


# =============================================================================
# Pre-defined Action Sets (can be used as defaults or examples)
# =============================================================================

# Puppy robot actions (EV3 with legs on D/A and head on C)
PUPPY_ACTIONS = {
    "sitdown": [
        ("eyes sleepy", 0),
        ("motor D -25", 0),
        ("motor A -25", 800),
        ("stop", 0),
    ],
    "standup": [
        ("eyes neutral", 0),
        ("motor D 80 500", 0),
        ("motor A 80 500", 300),
        ("motor D 60 500", 0),
        ("motor A 60 500", 300),
        ("motor D 40 700", 0),
        ("motor A 40 700", 0),
    ],
    "bark": [
        ("eyes surprised", 0),
        ("speak woof woof", 0),
    ],
    "stretch": [
        ("eyes sleepy", 0),
        ("motor D 30 300", 0),
        ("motor A 30 300", 300),
        ("motor D 25 400", 0),
        ("motor A 25 400", 300),
        ("motor D 30 600", 0),
        ("motor A 30 600", 300),
        ("motor D -30 600", 0),
        ("motor A -30 600", 300),
        ("eyes neutral", 0),
    ],
    "hop": [
        ("eyes surprised", 0),
        ("motor D 50", 0),
        ("motor A 50", 200),
        ("stop", 200),
        ("motor D -25", 0),
        ("motor A -25", 200),
        ("stop", 0),
    ],
    "head_up": [
        ("eyes neutral", 0),
        ("motor C 15 400", 0),
    ],
    "head_down": [
        ("eyes sleepy", 0),
        ("motor C -15 400", 0),
    ],
    "happy": [
        ("eyes happy", 0),
        ("speak woof", 0),
        ("motor D 50", 0),
        ("motor A 50", 200),
        ("stop", 200),
        ("motor D -25", 0),
        ("motor A -25", 200),
        ("stop", 0),
        ("speak woof", 0),
    ],
    "angry": [
        ("eyes angry", 0),
        ("speak grrr", 0),
        ("motor D 30 300", 0),
        ("motor A 30 300", 300),
        ("motor D 25 400", 0),
        ("motor A 25 400", 0),
        ("speak woof woof", 0),
    ],
    "sleep": [
        ("eyes sleepy", 0),
        ("motor D -25", 0),
        ("motor A -25", 1000),
        ("stop", 0),
        ("display Zzz...", 0),
    ],
    "wakeup": [
        ("eyes surprised", 0),
        ("beep 880 200", 0),
        ("motor D 50 300", 0),
        ("motor A 50 300", 300),
        ("eyes neutral", 0),
    ],
}


def get_puppy_adapter() -> ActionAdapter:
    """Get pre-configured puppy action adapter."""
    return ActionAdapter(PUPPY_ACTIONS)


# =============================================================================
# Convenience function for EV3MicroPython integration
# =============================================================================

async def execute_with_adapter(
    ev3,  # EV3MicroPython instance
    action: str,
    adapter: ActionAdapter,
    verbose: bool = False
) -> Tuple[str, float]:
    """
    Execute action using adapter translation.
    
    Args:
        ev3: EV3MicroPython instance
        action: Action name to execute
        adapter: ActionAdapter with action definitions
        verbose: Print each command
        
    Returns:
        Tuple of (result, total_latency_ms)
    """
    import time
    
    commands = adapter.translate(action)
    
    if commands is None:
        # Not a translated action, send directly
        return await ev3.send(action)
    
    total_latency = 0.0
    responses = []
    
    for cmd, delay_ms in commands:
        response, latency = await ev3.send(cmd)
        responses.append(response)
        total_latency += latency
        
        if verbose:
            print(f"  {cmd} -> {response} ({latency:.1f}ms)")
        
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
    
    # Return combined result
    if all("OK" in r or r.startswith("OK") for r in responses):
        return "OK", total_latency
    else:
        return "; ".join(responses), total_latency

