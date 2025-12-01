#!/usr/bin/env python3
"""
EV3 Puppy Robot Controller
--------------------------
Flexible controller with CLI actions and Hydra configuration.
Compatible with both local EV3 execution and remote control.

Default: MicroPython interface (USB/WiFi TCP) with ~1-15ms latency.
Legacy: SSH interface available with transport="ssh".

Usage:
    python puppy.py action=standup                    # Stand up (MicroPython)
    python puppy.py action=sitdown                    # Sit down
    python puppy.py action=bark                       # Bark
    python puppy.py action=stretch                    # Stretch
    python puppy.py action=hop                        # Hop
    python puppy.py action=sleep                      # Go to sleep
    python puppy.py action=wakeup                     # Wake up
    python puppy.py action=stream                     # Stream sensor data
    python puppy.py connection=local action=run       # Run on EV3 directly

Prerequisites:
    - EV3 running Pybricks MicroPython with pybricks_daemon.py
    - Or EV3 running ev3dev with puppy_daemon.py (legacy SSH mode)
"""

import asyncio
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

# Add root directory to path for imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

# Check if running on EV3 (pybricks) or host machine
try:
    from pybricks.hubs import EV3Brick
    from pybricks.ev3devices import Motor, ColorSensor, TouchSensor
    from pybricks.parameters import Port, Button, Color, Direction
    from pybricks.media.ev3dev import Image, ImageFile, SoundFile
    from pybricks.tools import wait, StopWatch
    import urandom
    ON_EV3 = True
except ImportError:
    ON_EV3 = False
    urandom = random

# Hydra import (optional, graceful fallback)
try:
    import hydra
    from omegaconf import DictConfig, OmegaConf
    HYDRA_AVAILABLE = True
except ImportError:
    HYDRA_AVAILABLE = False
    DictConfig = dict

# Import from platforms (host-side only)
try:
    from platforms.ev3.ev3_micropython import EV3MicroPython, EV3Config
    EV3_MICROPYTHON_AVAILABLE = True
except ImportError:
    EV3_MICROPYTHON_AVAILABLE = False

# Legacy SSH interface (fallback)
try:
    from platforms.ev3.ev3_interface import EV3Interface, EV3DaemonSession
    EV3_INTERFACE_AVAILABLE = True
except ImportError:
    EV3_INTERFACE_AVAILABLE = False


class Action(Enum):
    """Available puppy actions."""
    RUN = "run"
    FLOW = "flow"
    STANDUP = "standup"
    SITDOWN = "sitdown"
    BARK = "bark"
    STRETCH = "stretch"
    HOP = "hop"
    SLEEP = "sleep"
    WAKEUP = "wakeup"
    ADJUST_HEAD = "adjust_head"
    HEAD_UP = "head_up"
    HEAD_DOWN = "head_down"
    HAPPY = "happy"
    ANGRY = "angry"
    PLAYFUL = "playful"
    STREAM = "stream"
    STATUS = "status"


@dataclass
class PuppyConfig:
    """Puppy configuration with defaults."""
    # Motion
    half_up_angle: int = 25
    stand_up_angle: int = 65
    stretch_angle: int = 125
    head_up_angle: int = 0
    head_down_angle: int = -40
    leg_speed: int = 100
    head_speed: int = 20
    
    # Behavior
    idle_timeout_ms: int = 30000
    pet_decay_ms: int = 15000
    feed_decay_ms: int = 15000
    pet_target_min: int = 3
    pet_target_max: int = 6
    feed_target_min: int = 2
    feed_target_max: int = 4
    
    # Streaming
    stream_interval_ms: int = 100
    
    @classmethod
    def from_hydra(cls, cfg: DictConfig) -> "PuppyConfig":
        """Create config from Hydra DictConfig."""
        return cls(
            half_up_angle=cfg.motion.get("half_up_angle", 25),
            stand_up_angle=cfg.motion.get("stand_up_angle", 65),
            stretch_angle=cfg.motion.get("stretch_angle", 125),
            head_up_angle=cfg.motion.get("head_up_angle", 0),
            head_down_angle=cfg.motion.get("head_down_angle", -40),
            leg_speed=cfg.motion.get("leg_speed", 100),
            head_speed=cfg.motion.get("head_speed", 20),
            idle_timeout_ms=cfg.behavior.get("idle_timeout_ms", 30000),
            pet_decay_ms=cfg.behavior.get("pet_decay_ms", 15000),
            feed_decay_ms=cfg.behavior.get("feed_decay_ms", 15000),
            pet_target_min=cfg.behavior.get("pet_target_min", 3),
            pet_target_max=cfg.behavior.get("pet_target_max", 6),
            feed_target_min=cfg.behavior.get("feed_target_min", 2),
            feed_target_max=cfg.behavior.get("feed_target_max", 4),
            stream_interval_ms=cfg.streaming.get("interval_ms", 100),
        )


class Puppy:
    """EV3 Puppy robot controller with CLI-compatible actions."""

    # Eye images (only available on EV3)
    NEUTRAL_EYES = None
    TIRED_EYES = None
    TIRED_LEFT_EYES = None
    TIRED_RIGHT_EYES = None
    SLEEPING_EYES = None
    HURT_EYES = None
    ANGRY_EYES = None
    HEART_EYES = None
    SQUINTY_EYES = None

    def __init__(self, config: Optional[PuppyConfig] = None):
        self.config = config or PuppyConfig()
        self._running = False
        self._streaming = False
        
        if ON_EV3:
            self._init_ev3_hardware()
        else:
            self._init_mock_hardware()
        
        # State
        self.pet_target = 0
        self.feed_target = 0
        self.pet_count = 0
        self.feed_count = 0
        self._behavior = None
        self._behavior_changed = False
        self._eyes = None
        self.prev_petted = None
        self.prev_color = None

    def _init_ev3_hardware(self):
        """Initialize real EV3 hardware."""
        self.ev3 = EV3Brick()
        
        # Motors
        self.left_leg_motor = Motor(Port.D, Direction.COUNTERCLOCKWISE)
        self.right_leg_motor = Motor(Port.A, Direction.COUNTERCLOCKWISE)
        self.head_motor = Motor(Port.C, Direction.COUNTERCLOCKWISE,
                                gears=[[1, 24], [12, 36]])
        
        # Sensors
        self.color_sensor = ColorSensor(Port.S4)
        self.touch_sensor = TouchSensor(Port.S1)
        
        # Timers
        self.pet_count_timer = StopWatch()
        self.feed_count_timer = StopWatch()
        self.count_changed_timer = StopWatch()
        self.eyes_timer_1 = StopWatch()
        self.eyes_timer_2 = StopWatch()
        self.playful_timer = StopWatch()
        
        self.eyes_timer_1_end = 0
        self.eyes_timer_2_end = 0
        self.playful_bark_interval = None
        
        # Load eye images
        Puppy.NEUTRAL_EYES = Image(ImageFile.NEUTRAL)
        Puppy.TIRED_EYES = Image(ImageFile.TIRED_MIDDLE)
        Puppy.TIRED_LEFT_EYES = Image(ImageFile.TIRED_LEFT)
        Puppy.TIRED_RIGHT_EYES = Image(ImageFile.TIRED_RIGHT)
        Puppy.SLEEPING_EYES = Image(ImageFile.SLEEPING)
        Puppy.HURT_EYES = Image(ImageFile.HURT)
        Puppy.ANGRY_EYES = Image(ImageFile.ANGRY)
        Puppy.HEART_EYES = Image(ImageFile.LOVE)
        Puppy.SQUINTY_EYES = Image(ImageFile.TEAR)
        Puppy.SQUINTY_EYES.draw_box(120, 60, 140, 85, fill=True, color=Color.WHITE)

    def _init_mock_hardware(self):
        """Initialize mock hardware for testing off-EV3."""
        self.ev3 = None
        self.left_leg_motor = None
        self.right_leg_motor = None
        self.head_motor = None
        self.color_sensor = None
        self.touch_sensor = None
        
        # Mock timers
        self._mock_timers = {}
        self.pet_count_timer = self._create_mock_timer("pet")
        self.feed_count_timer = self._create_mock_timer("feed")
        self.count_changed_timer = self._create_mock_timer("count")
        self.eyes_timer_1 = self._create_mock_timer("eyes1")
        self.eyes_timer_2 = self._create_mock_timer("eyes2")
        self.playful_timer = self._create_mock_timer("playful")
        
        self.eyes_timer_1_end = 0
        self.eyes_timer_2_end = 0
        self.playful_bark_interval = None

    def _create_mock_timer(self, name: str):
        """Create a mock timer object."""
        class MockTimer:
            def __init__(self):
                self._start = time.time() * 1000
            def time(self):
                return (time.time() * 1000) - self._start
            def reset(self):
                self._start = time.time() * 1000
        return MockTimer()

    def _wait(self, ms: int):
        """Wait for specified milliseconds."""
        if ON_EV3:
            wait(ms)
        else:
            time.sleep(ms / 1000.0)

    def _print(self, msg: str):
        """Print status message."""
        print(f"[Puppy] {msg}")

    # -------------------------------------------------------------------------
    # Public Actions (CLI-compatible)
    # -------------------------------------------------------------------------

    def stand_up(self):
        """Make the puppy stand up."""
        self._print("Standing up...")
        if ON_EV3:
            cfg = self.config
            self.left_leg_motor.run_target(cfg.leg_speed, cfg.half_up_angle, wait=False)
            self.right_leg_motor.run_target(cfg.leg_speed, cfg.half_up_angle)
            while not self.left_leg_motor.control.done():
                wait(100)
            self.left_leg_motor.run_target(50, cfg.stand_up_angle, wait=False)
            self.right_leg_motor.run_target(50, cfg.stand_up_angle)
            while not self.left_leg_motor.control.done():
                wait(100)
            wait(500)
        self._print("Standing up... done")

    def sit_down(self):
        """Make the puppy sit down."""
        self._print("Sitting down...")
        if ON_EV3:
            self.left_leg_motor.run(-50)
            self.right_leg_motor.run(-50)
            wait(1000)
            self.left_leg_motor.stop()
            self.right_leg_motor.stop()
            wait(100)
        self._print("Sitting down... done")

    def stretch(self):
        """Make the puppy stretch."""
        self._print("Stretching...")
        self.stand_up()
        if ON_EV3:
            cfg = self.config
            self.left_leg_motor.run_target(cfg.leg_speed, cfg.stretch_angle, wait=False)
            self.right_leg_motor.run_target(cfg.leg_speed, cfg.stretch_angle)
            while not self.left_leg_motor.control.done():
                wait(100)
            self.ev3.speaker.play_file(SoundFile.DOG_WHINE)
            self.left_leg_motor.run_target(cfg.leg_speed, cfg.stand_up_angle, wait=False)
            self.right_leg_motor.run_target(cfg.leg_speed, cfg.stand_up_angle)
            while not self.left_leg_motor.control.done():
                wait(100)
        self._print("Stretching... done")

    def hop(self):
        """Make the puppy hop."""
        self._print("Hopping...")
        if ON_EV3:
            self.left_leg_motor.run(500)
            self.right_leg_motor.run(500)
            wait(275)
            self.left_leg_motor.hold()
            self.right_leg_motor.hold()
            wait(275)
            self.left_leg_motor.run(-50)
            self.right_leg_motor.run(-50)
            wait(275)
            self.left_leg_motor.stop()
            self.right_leg_motor.stop()
        self._print("Hopping... done")

    def bark(self, count: int = 1):
        """Make the puppy bark."""
        self._print(f"Barking {count}x...")
        if ON_EV3:
            for _ in range(count):
                self.ev3.speaker.play_file(SoundFile.DOG_BARK_1)
                wait(500)
        self._print("Barking... done")

    def head_up(self):
        """Move head up."""
        self._print("Head up...")
        if ON_EV3:
            self.head_motor.run_target(self.config.head_speed, self.config.head_up_angle)
        self._print("Head up... done")

    def head_down(self):
        """Move head down."""
        self._print("Head down...")
        if ON_EV3:
            self.head_motor.run_target(self.config.head_speed, self.config.head_down_angle)
        self._print("Head down... done")

    def adjust_head(self):
        """Interactive head adjustment using EV3 buttons."""
        if not ON_EV3:
            self._print("adjust_head requires running on EV3")
            return
        
        self._print("Adjusting head (UP/DOWN buttons, CENTER to confirm)...")
        self.ev3.screen.load_image(ImageFile.EV3_ICON)
        self.ev3.light.on(Color.ORANGE)
        
        while True:
            buttons = self.ev3.buttons.pressed()
            if Button.CENTER in buttons:
                break
            elif Button.UP in buttons:
                self.head_motor.run(20)
            elif Button.DOWN in buttons:
                self.head_motor.run(-20)
            else:
                self.head_motor.stop()
            wait(100)
        
        self.head_motor.stop()
        self.head_motor.reset_angle(0)
        self.ev3.light.on(Color.GREEN)
        self._print("Head adjustment... done")

    def go_to_sleep(self):
        """Make the puppy go to sleep."""
        self._print("Going to sleep...")
        if ON_EV3:
            self.eyes = self.TIRED_EYES
            self.sit_down()
            self.head_down()
            self.eyes = self.SLEEPING_EYES
            self.ev3.speaker.play_file(SoundFile.SNORING)
        self._print("Zzz...")

    def wake_up(self):
        """Wake up the puppy."""
        self._print("Waking up...")
        if ON_EV3:
            self.eyes = self.TIRED_EYES
            self.ev3.speaker.play_file(SoundFile.DOG_WHINE)
        self.head_up()
        self.sit_down()
        self.stretch()
        self._wait(1000)
        self.stand_up()
        self._print("Awake!")

    def act_happy(self):
        """Make the puppy act happy."""
        self._print("Happy!")
        if ON_EV3:
            self.eyes = self.HEART_EYES
        self.sit_down()
        for _ in range(3):
            self.bark()
            self.hop()
        self._wait(500)
        self.sit_down()

    def act_angry(self):
        """Make the puppy act angry."""
        self._print("Angry!")
        if ON_EV3:
            self.eyes = self.ANGRY_EYES
            self.ev3.speaker.play_file(SoundFile.DOG_GROWL)
        self.stand_up()
        self._wait(1500)
        self.bark()

    def act_playful(self):
        """Make the puppy act playful."""
        self._print("Playful!")
        if ON_EV3:
            self.eyes = self.NEUTRAL_EYES
        self.stand_up()
        self.bark(2)
        self.hop()

    # -------------------------------------------------------------------------
    # Streaming
    # -------------------------------------------------------------------------

    def get_status(self) -> dict:
        """Get current puppy status."""
        status = {
            "timestamp": time.time(),
            "on_ev3": ON_EV3,
            "motors": {},
            "sensors": {},
            "state": {
                "pet_count": self.pet_count,
                "feed_count": self.feed_count,
                "pet_target": self.pet_target,
                "feed_target": self.feed_target,
            }
        }
        
        if ON_EV3:
            status["motors"] = {
                "left_leg": {"position": self.left_leg_motor.angle()},
                "right_leg": {"position": self.right_leg_motor.angle()},
                "head": {"position": self.head_motor.angle()},
            }
            status["sensors"] = {
                "touch": {"pressed": self.touch_sensor.pressed()},
                "color": {"color": str(self.color_sensor.color())},
            }
        
        return status

    def stream(self, callback: Optional[Callable] = None, duration_s: float = 0):
        """Stream status data."""
        self._print(f"Streaming (interval={self.config.stream_interval_ms}ms)...")
        self._streaming = True
        interval = self.config.stream_interval_ms / 1000.0
        start = time.time()
        
        try:
            while self._streaming:
                status = self.get_status()
                if callback:
                    callback(status)
                else:
                    print(json.dumps(status))
                
                if duration_s > 0 and (time.time() - start) >= duration_s:
                    break
                
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        
        self._streaming = False
        self._print("Streaming stopped")

    def stop_streaming(self):
        """Stop streaming."""
        self._streaming = False

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def behavior(self):
        return self._behavior

    @behavior.setter
    def behavior(self, value):
        if self._behavior != value:
            self._behavior = value
            self._behavior_changed = True

    @property
    def did_behavior_change(self):
        if self._behavior_changed:
            self._behavior_changed = False
            return True
        return False

    @property
    def eyes(self):
        return self._eyes

    @eyes.setter
    def eyes(self, value):
        if value != self._eyes and ON_EV3:
            self._eyes = value
            if value is not None:
                self.ev3.screen.load_image(value)

    # -------------------------------------------------------------------------
    # Behavior Loop (original functionality)
    # -------------------------------------------------------------------------

    def reset(self):
        """Reset puppy state for behavior loop."""
        if ON_EV3:
            self.left_leg_motor.reset_angle(0)
            self.right_leg_motor.reset_angle(0)
        
        cfg = self.config
        self.pet_target = urandom.randint(cfg.pet_target_min, cfg.pet_target_max)
        self.feed_target = urandom.randint(cfg.feed_target_min, cfg.feed_target_max)
        self.pet_count, self.feed_count = 1, 1
        
        self.pet_count_timer.reset()
        self.feed_count_timer.reset()
        self.count_changed_timer.reset()
        self.behavior = self._idle_behavior

    def _idle_behavior(self):
        """Idle behavior state."""
        if self.did_behavior_change:
            self._print("idle")
            self.stand_up()
        self._update_eyes()
        self._update_behavior()
        self._update_pet_count()
        self._update_feed_count()

    def _update_eyes(self):
        """Update eye animations."""
        if not ON_EV3:
            return
        if self.eyes_timer_1.time() > self.eyes_timer_1_end:
            self.eyes_timer_1.reset()
            if self.eyes == self.SLEEPING_EYES:
                self.eyes_timer_1_end = urandom.randint(1, 5) * 1000
                self.eyes = self.TIRED_RIGHT_EYES
            else:
                self.eyes_timer_1_end = 250
                self.eyes = self.SLEEPING_EYES

    def _update_behavior(self):
        """Update behavior based on pet/feed state."""
        if self.pet_count == self.pet_target and self.feed_count == self.feed_target:
            self.behavior = self._happy_behavior
        elif self.pet_count > self.pet_target and self.feed_count < self.feed_target:
            self.behavior = self._angry_behavior
        elif self.feed_count == 0:
            self.behavior = self._hungry_behavior

    def _update_pet_count(self) -> bool:
        """Update pet count from touch sensor."""
        if not ON_EV3:
            return False
        petted = self.touch_sensor.pressed()
        if petted and petted != self.prev_petted:
            self.pet_count += 1
            self._print(f"pet_count: {self.pet_count}/{self.pet_target}")
            self.count_changed_timer.reset()
            self.prev_petted = petted
            return True
        self.prev_petted = petted
        return False

    def _update_feed_count(self) -> bool:
        """Update feed count from color sensor."""
        if not ON_EV3:
            return False
        color = self.color_sensor.color()
        if color is not None and color != Color.BLACK and color != self.prev_color:
            self.feed_count += 1
            self._print(f"feed_count: {self.feed_count}/{self.feed_target}")
            self.count_changed_timer.reset()
            self.prev_color = color
            return True
        return False

    def _happy_behavior(self):
        """Happy behavior state."""
        if self.did_behavior_change:
            self._print("happy!")
        self.act_happy()
        self.reset()

    def _angry_behavior(self):
        """Angry behavior state."""
        if self.did_behavior_change:
            self._print("angry!")
        self.act_angry()
        self.pet_count -= 1
        self.behavior = self._idle_behavior

    def _hungry_behavior(self):
        """Hungry behavior state."""
        if self.did_behavior_change:
            self._print("hungry!")
            if ON_EV3:
                self.eyes = self.HURT_EYES
            self.sit_down()
        if self._update_feed_count():
            self.behavior = self._idle_behavior

    def _sleep_behavior(self):
        """Sleep behavior state."""
        if self.did_behavior_change:
            self.go_to_sleep()
        if ON_EV3:
            if self.touch_sensor.pressed() and Button.CENTER in self.ev3.buttons.pressed():
                self.count_changed_timer.reset()
                self.behavior = self._wakeup_behavior

    def _wakeup_behavior(self):
        """Wakeup behavior state."""
        if self.did_behavior_change:
            self._print("waking up")
        self.wake_up()
        self.behavior = self._idle_behavior

    def _monitor_counts(self):
        """Monitor and decay counts over time."""
        cfg = self.config
        if self.pet_count_timer.time() > cfg.pet_decay_ms:
            self.pet_count_timer.reset()
            self.pet_count = max(0, self.pet_count - 1)
        if self.feed_count_timer.time() > cfg.feed_decay_ms:
            self.feed_count_timer.reset()
            self.feed_count = max(0, self.feed_count - 1)
        if self.count_changed_timer.time() > cfg.idle_timeout_ms:
            self.count_changed_timer.reset()
            self.behavior = self._sleep_behavior

    def run(self):
        """Main behavior loop."""
        self._print("Starting main behavior loop...")
        self._running = True
        self.sit_down()
        self.adjust_head()
        self.eyes = self.SLEEPING_EYES
        self.reset()
        
        try:
            while self._running:
                self._monitor_counts()
                if self.behavior:
                    self.behavior()
                self._wait(100)
        except KeyboardInterrupt:
            self._print("Interrupted")
        
        self._running = False
        self._print("Stopped")

    def stop(self):
        """Stop the main loop."""
        self._running = False

    # -------------------------------------------------------------------------
    # Action Dispatcher
    # -------------------------------------------------------------------------

    def execute_action(self, action: str, **kwargs) -> dict:
        """Execute an action by name. Returns result dict."""
        action = action.lower()
        result = {"action": action, "success": False}
        
        action_map = {
            "run": self.run,
            "standup": self.stand_up,
            "stand_up": self.stand_up,
            "sitdown": self.sit_down,
            "sit_down": self.sit_down,
            "bark": lambda: self.bark(kwargs.get("count", 1)),
            "stretch": self.stretch,
            "hop": self.hop,
            "sleep": self.go_to_sleep,
            "wakeup": self.wake_up,
            "wake_up": self.wake_up,
            "adjust_head": self.adjust_head,
            "head_up": self.head_up,
            "head_down": self.head_down,
            "happy": self.act_happy,
            "angry": self.act_angry,
            "playful": self.act_playful,
            "stream": lambda: self.stream(duration_s=kwargs.get("duration", 0)),
            "status": lambda: None,  # Just return status
        }
        
        if action in action_map:
            try:
                action_map[action]()
                result["success"] = True
                result["status"] = self.get_status()
            except Exception as e:
                result["error"] = str(e)
        else:
            result["error"] = f"Unknown action: {action}"
            result["available_actions"] = list(action_map.keys())
        
        return result


# -----------------------------------------------------------------------------
# Action Adapter (loaded from platform level)
# -----------------------------------------------------------------------------
# Actions are now defined in configs/actions.yaml and loaded via ActionAdapter
# from platforms/ev3/action_adapter.py - keeping project code clean!

# Lazy-loaded action adapter with auto-reload on file change
_action_adapter = None
_action_yaml_mtime = 0

def get_action_adapter(force_reload=False):
    """Get or create the action adapter (auto-reloads if YAML file changed)."""
    global _action_adapter, _action_yaml_mtime
    
    try:
        from platforms.ev3.action_adapter import ActionAdapter
        import os
        yaml_path = os.path.join(os.path.dirname(__file__), "configs", "actions.yaml")
        
        if os.path.exists(yaml_path):
            current_mtime = os.path.getmtime(yaml_path)
            
            # Reload if: forced, first load, or file modified
            if force_reload or _action_adapter is None or current_mtime > _action_yaml_mtime:
                _action_adapter = ActionAdapter.from_yaml(yaml_path)
                _action_yaml_mtime = current_mtime
        elif _action_adapter is None:
            # Fallback to built-in
            from platforms.ev3.action_adapter import PUPPY_ACTIONS
            _action_adapter = ActionAdapter(PUPPY_ACTIONS)
    except ImportError:
        _action_adapter = None
    
    return _action_adapter


# -----------------------------------------------------------------------------
# Remote Puppy Controller (sends commands to EV3 via MicroPython)
# -----------------------------------------------------------------------------

class RemotePuppy:
    """
    Control EV3 Puppy remotely via MicroPython interface.
    
    Default: Uses EV3MicroPython (USB/WiFi TCP) with ~1-15ms latency.
    Fallback: Legacy SSH interface if MicroPython not available.
    
    The daemon (pybricks_daemon.py or puppy_daemon.py) must be running on EV3.
    """
    
    # Daemon file to upload (in same directory as this script)
    DAEMON_PUPPY_FILE = "puppy_daemon.py"
    
    COMMANDS_HELP = """
Commands: standup, sitdown, bark, stretch, hop
          head_up, head_down, happy, angry, status, stop
          eyes <style> - change display
            styles: neutral, happy, angry, sleepy,
                    surprised, love, wink, off
          quit/exit/q - disconnect"""

    def __init__(self, host: str = "ev3dev.local", user: str = "robot", 
                 password: str = "maker", sudo_password: str = "maker",
                 transport: str = "micropython"):
        """
        Initialize RemotePuppy controller.
        
        Args:
            host: EV3 hostname or IP
            user: SSH username (only for legacy mode)
            password: SSH password (only for legacy mode)
            sudo_password: sudo password (only for legacy mode)
            transport: "micropython" (default, fast) or "ssh" (legacy)
        """
        self.host = host
        self.user = user
        self.password = password
        self.sudo_password = sudo_password
        self.transport = transport
        self._ev3 = None
        self._connected = False
        self._loop = None
        self._script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Legacy SSH fields (only used if transport="ssh")
        self._channel = None
        self._stdin = None
        self._stdout = None
        self._daemon_running = False

    def _get_loop(self):
        """Get or create event loop for async operations."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run_async(self, coro):
        """Run async coroutine synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    def _connect(self):
        """Connect to EV3 using MicroPython or legacy SSH."""
        if self._connected:
            return
        
        if self.transport == "micropython":
            self._connect_micropython()
        else:
            self._connect_ssh()

    def _connect_micropython(self):
        """Connect using MicroPython interface (fast!)."""
        if not EV3_MICROPYTHON_AVAILABLE:
            raise RuntimeError("EV3MicroPython not available. Install pyserial.")
        
        config = EV3Config(wifi_host=self.host, wifi_port=9000)
        self._ev3 = EV3MicroPython(config=config)
        
        connected = self._run_async(self._ev3.connect())
        if not connected:
            raise RuntimeError(f"Failed to connect to EV3 at {self.host}")
        
        self._connected = True
        print(f"✓ EV3 MicroPython connected ({self._ev3.transport_name})")

    def _connect_ssh(self):
        """Connect using legacy SSH interface."""
        if not EV3_INTERFACE_AVAILABLE:
            raise RuntimeError("EV3Interface (SSH) not available. Install paramiko.")
        
        self._ev3 = EV3Interface(self.host, self.user, self.password)
        self._ev3.connect()
        self._connected = True

    def _upload_daemon(self):
        """Upload daemon script to EV3 (SSH only)."""
        if self.transport == "micropython":
            return  # MicroPython doesn't need daemon upload
        
        import tempfile
        
        # Load from puppy_daemon.py file
        puppy_file = os.path.join(self._script_dir, self.DAEMON_PUPPY_FILE)
        
        if not os.path.exists(puppy_file):
            raise FileNotFoundError(f"Daemon file not found: {puppy_file}")
        
        with open(puppy_file, 'r') as f:
            content = f.read()
        
        # Substitute sudo password
        content = content.replace(
            'SUDO_PASSWORD = "maker"',
            f'SUDO_PASSWORD = "{self.sudo_password}"'
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        self._ev3.upload_file(temp_path, "puppy_daemon.py")
        os.unlink(temp_path)
        print(f"✓ Uploaded {self.DAEMON_PUPPY_FILE}")

    def _start_daemon(self):
        """Start persistent daemon on EV3 (SSH only)."""
        if self.transport == "micropython":
            return  # MicroPython daemon should already be running
        
        if self._daemon_running:
            return
        
        self._upload_daemon()
        
        transport = self._ev3._ssh.get_transport()
        self._channel = transport.open_session()
        self._channel.exec_command("cd /home/robot/ev3 && python3 -u puppy_daemon.py")
        
        self._stdin = self._channel.makefile_stdin('wb', -1)
        self._stdout = self._channel.makefile('r', -1)
        
        response = self._stdout.readline().strip()
        if "READY" in response:
            self._daemon_running = True
            print("✓ Daemon ready (SSH)")
        else:
            raise RuntimeError("Daemon failed: " + response)

    def _send_command(self, cmd: str) -> str:
        """Send command to EV3 daemon and get response."""
        if self.transport == "micropython":
            # Async MicroPython interface
            response, latency = self._run_async(self._ev3.send(cmd))
            return response
        else:
            # Legacy SSH stdin/stdout
            try:
                self._stdin.write((cmd + "\n").encode())
                self._stdin.flush()
                response = self._stdout.readline().strip()
                if not response and cmd != "quit":
                    raise OSError("Socket is closed")
                return response
            except (OSError, IOError) as e:
                raise OSError("Socket is closed: " + str(e))

    def _do_squat(self, args: str) -> str:
        """Do squats (standup + sitdown) N times."""
        try:
            count = int(args) if args else 1
        except ValueError:
            return "ERR: usage: squat [count]"
        
        results = []
        for i in range(count):
            # Standup
            result1 = self._execute_sequence("standup")
            if result1.startswith("FAIL"):
                return f"FAIL at squat {i+1} standup: {result1}"
            
            # Sitdown
            result2 = self._execute_sequence("sitdown")
            if result2.startswith("FAIL"):
                return f"FAIL at squat {i+1} sitdown: {result2}"
            
            results.append(f"squat {i+1}: OK")
        
        return f"OK {count} squats done"

    def _execute_sequence(self, action: str) -> str:
        """Execute a puppy action sequence (MicroPython mode)."""
        # get_action_adapter() auto-reloads if YAML file changed
        adapter = get_action_adapter()
        
        if adapter is None or not adapter.has_action(action):
            # Not a translated action, send directly (might be generic command)
            return self._send_command(action)
        
        sequence = adapter.translate(action)
        responses = []
        
        # Group consecutive commands until we hit a delay
        # Commands before delay run together (batched), then we wait
        batch = []
        
        for cmd, delay_ms in sequence:
            batch.append(cmd)
            
            if delay_ms > 0:
                # Execute batch then wait
                if len(batch) == 1:
                    response = self._send_command(batch[0])
                else:
                    response = self._send_command("|" + "|".join(batch))
                responses.append(response)
                batch = []
                time.sleep(delay_ms / 1000.0)
        
        # Execute remaining batch (no trailing delay)
        if batch:
            if len(batch) == 1:
                response = self._send_command(batch[0])
            else:
                response = self._send_command("|" + "|".join(batch))
            responses.append(response)
        
        # Return combined result - check for FAIL (position verification failed)
        fails = [r for r in responses if r.startswith("FAIL")]
        if fails:
            return fails[0]  # Return first failure with details
        elif all("OK" in r or r.startswith("OK") for r in responses):
            # Return last response with details (e.g., "OK moved D:0->-55...")
            return responses[-1] if responses else "OK"
        else:
            return "; ".join(responses)

    def execute_action(self, action: str) -> dict:
        """Execute action on remote EV3."""
        result = {"action": action, "success": False, "remote": True}
        
        try:
            self._connect()
            
            if self.transport == "micropython":
                # MicroPython: translate puppy actions to sequences
                print(f"[RemotePuppy] Executing '{action}' via MicroPython...")
                response = self._execute_sequence(action)
                result["response"] = response
                result["success"] = "OK" in response or response.startswith("OK")
                print(f"[EV3] {response}")
            else:
                # Legacy SSH: upload daemon and run
                self._upload_daemon()
                print("[RemotePuppy] Executing '%s' via SSH..." % action)
                
                stdout, stderr, code = self._ev3.execute_command(
                    "cd /home/robot/ev3 && echo '%s' | python3 -u puppy_daemon.py" % action,
                    timeout=30
                )
                
                result["stdout"] = stdout.strip()
                result["exit_code"] = code
                result["success"] = "OK" in stdout or "READY" in stdout
                
                lines = stdout.strip().split('\n')
                for line in lines:
                    if line and line != "READY":
                        print("[EV3] %s" % line)
                if stderr.strip():
                    print("[EV3 Error] %s" % stderr.strip())
                
        except Exception as e:
            result["error"] = str(e)
            print("[RemotePuppy] Error: %s" % e)
        
        return result

    def flow(self):
        """Interactive flow mode using ProjectShell - ultra low latency."""
        from core.project_shell import ProjectShell, Colors, colored
        
        def reload_actions():
            """Force reload actions from YAML file."""
            adapter = get_action_adapter(force_reload=True)
            actions = adapter.list_actions() if adapter else []
            return f"OK reloaded {len(actions)} actions: {', '.join(actions)}"
        
        def make_handler(cmd_name):
            def handler(args):
                full_cmd = f"{cmd_name} {args}".strip() if args else cmd_name
                # For MicroPython, translate puppy actions to sequences
                # get_action_adapter() auto-reloads if file changed
                adapter = get_action_adapter()
                if self.transport == "micropython" and adapter and adapter.has_action(cmd_name):
                    return self._execute_sequence(cmd_name)
                return self._send_command(full_cmd)
            return handler
        
        # Define commands
        commands = {
            "standup": ("Stand up (legs to -55°)", make_handler("standup")),
            "sitdown": ("Sit down (legs to 0°)", make_handler("sitdown")),
            "calibrate": ("Set current as SITTING position (0°)", make_handler("calibrate")),
            "pos": ("Show motor positions", make_handler("pos")),
            "bark": ("Bark (woof woof)", make_handler("bark")),
            "stretch": ("Stretch", make_handler("stretch")),
            "hop": ("Hop", make_handler("hop")),
            "squat": ("Squat (standup+sitdown) N times", self._do_squat, "[count]"),
            "head_up": ("Move head up", make_handler("head_up")),
            "head_down": ("Move head down", make_handler("head_down")),
            "happy": ("Happy expression", make_handler("happy")),
            "angry": ("Angry expression", make_handler("angry")),
            "stop": ("Stop all motors", make_handler("stop")),
            "brake": ("Brake & clear stall state", make_handler("brake")),
            "eyes": ("Change eye display", make_handler("eyes"), "<style>"),
            "info": ("Show motors/sensors/battery", make_handler("status")),
            "reload": ("Reload actions.yaml (no restart needed)", lambda args: reload_actions()),
            "raw": ("Send raw command to daemon", lambda args: self._send_command(args) if args else "ERR: usage: raw <command>", "<cmd>"),
        }
        
        # Eye styles as aliases
        for style in ["neutral", "happy", "angry", "sleepy", "surprised", "love", "wink", "off"]:
            commands[style] = (f"Eyes: {style}", make_handler(f"eyes {style}"))
        
        # Custom banner
        banner = f"""
{colored("=" * 50, Colors.CYAN)}
{colored("  EV3 PUPPY - Interactive Shell", Colors.BOLD + Colors.CYAN)}
{colored("=" * 50, Colors.CYAN)}
"""
        
        # Connect function
        def connect():
            self._connect()
            self._start_daemon()
            # Force calibration at startup
            print("\n⚠️  CALIBRATION REQUIRED")
            print("   1. Put puppy in SITTING position (legs folded)")
            print("   2. Press ENTER to calibrate (sets current as 0°)")
            input("   Press ENTER when ready... ")
            self._send_command("reset")
            pos_response = self._send_command("pos")
            print(f"   ✓ Calibrated! {pos_response}")
            print("   Convention: 0° = sitting, -55° = standing\n")
            return True
        
        # Disconnect function  
        def disconnect():
            try:
                self._send_command("quit")
            except:
                pass
            self.disconnect()
        
        # Create and run shell
        shell = ProjectShell(
            name="Puppy",
            commands=commands,
            connect_func=connect,
            disconnect_func=disconnect,
            banner=banner,
        )
        
        shell.run()

    def disconnect(self):
        """Disconnect from EV3."""
        if self.transport == "micropython":
            # MicroPython async disconnect
            if self._ev3:
                try:
                    self._run_async(self._ev3.disconnect())
                except:
                    pass
                self._ev3 = None
        else:
            # Legacy SSH cleanup
            if hasattr(self, '_stdin') and self._stdin:
                try:
                    self._stdin.close()
                except:
                    pass
            if hasattr(self, '_stdout') and self._stdout:
                try:
                    self._stdout.close()
                except:
                    pass
            if self._channel:
                try:
                    self._channel.close()
                except:
                    pass
                self._channel = None
            self._daemon_running = False
            if self._ev3:
                self._ev3.disconnect()
                self._ev3 = None
        
        self._connected = False


# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

def run_with_config(cfg: DictConfig):
    """Run puppy with Hydra config."""
    config = PuppyConfig.from_hydra(cfg)
    action = cfg.get("action", "run")
    connection_mode = cfg.connection.get("mode", "remote") if hasattr(cfg, 'connection') else "remote"
    transport = cfg.connection.get("transport", "micropython") if hasattr(cfg, 'connection') else "micropython"
    
    # Determine mode: local (on EV3), remote (MicroPython/SSH), or mock
    if ON_EV3 or connection_mode == "local":
        # Running directly on EV3 or forced local mode
        mode = "EV3" if ON_EV3 else "Mock"
        print("[EV3 Puppy] Action: %s, Mode: %s" % (action, mode))
        puppy = Puppy(config)
        result = puppy.execute_action(action)
    else:
        # Remote mode - default MicroPython, fallback to SSH
        host = cfg.connection.get("host", "ev3dev.local")
        transport_str = "MicroPython" if transport == "micropython" else "SSH"
        print(f"[EV3 Puppy] Action: {action}, Mode: Remote ({host}, {transport_str})")
        
        # Check availability
        if transport == "micropython" and not EV3_MICROPYTHON_AVAILABLE:
            print("Warning: EV3MicroPython not available, falling back to SSH")
            transport = "ssh"
        
        if transport == "ssh" and not EV3_INTERFACE_AVAILABLE:
            print("Error: No EV3 interface available. Install pyserial or paramiko.")
            return {"success": False, "error": "No EV3 interface available"}
        
        remote = RemotePuppy(
            host=host,
            user=cfg.connection.get("user", "robot"),
            password=cfg.connection.get("password", "maker"),
            sudo_password=cfg.connection.get("sudo_password", "maker"),
            transport=transport,
        )
        
        # Flow mode - interactive session
        if action == "flow":
            remote.flow()
            return {"success": True, "action": "flow"}
        
        try:
            result = remote.execute_action(action)
        finally:
            remote.disconnect()
    
    if not result.get("success") and "error" in result:
        print("Error: %s" % result['error'])
    
    return result


if HYDRA_AVAILABLE:
    @hydra.main(version_base=None, config_path="configs", config_name="config")
    def main(cfg: DictConfig):
        return run_with_config(cfg)
else:
    def main():
        """Fallback main without Hydra."""
        import argparse
        parser = argparse.ArgumentParser(description="EV3 Puppy Controller")
        parser.add_argument("--action", "-a", default="status",
                          choices=[a.value for a in Action],
                          help="Action to perform")
        parser.add_argument("--host", default="ev3dev.local",
                          help="EV3 hostname")
        parser.add_argument("--local", action="store_true",
                          help="Run locally (mock mode)")
        parser.add_argument("--ssh", action="store_true",
                          help="Use legacy SSH transport (default: MicroPython)")
        parser.add_argument("--flow", action="store_const", const="flow",
                          dest="action", help="Interactive flow mode")
        parser.add_argument("--standup", action="store_const", const="standup",
                          dest="action", help="Stand up")
        parser.add_argument("--sitdown", action="store_const", const="sitdown",
                          dest="action", help="Sit down")
        parser.add_argument("--bark", action="store_const", const="bark",
                          dest="action", help="Bark")
        parser.add_argument("--stretch", action="store_const", const="stretch",
                          dest="action", help="Stretch")
        parser.add_argument("--hop", action="store_const", const="hop",
                          dest="action", help="Hop")
        parser.add_argument("--sleep", action="store_const", const="sleep",
                          dest="action", help="Go to sleep")
        parser.add_argument("--wakeup", action="store_const", const="wakeup",
                          dest="action", help="Wake up")
        parser.add_argument("--stream", action="store_const", const="stream",
                          dest="action", help="Stream status")
        parser.add_argument("--status", action="store_const", const="status",
                          dest="action", help="Print status")
        args = parser.parse_args()
        
        action = args.action or "status"
        transport = "ssh" if args.ssh else "micropython"
        
        if args.local or ON_EV3:
            puppy = Puppy()
            result = puppy.execute_action(action)
            if action == "status":
                print(json.dumps(result.get("status", {}), indent=2))
        else:
            # Check availability
            if transport == "micropython" and not EV3_MICROPYTHON_AVAILABLE:
                print("Warning: EV3MicroPython not available, trying SSH...")
                transport = "ssh"
            
            if transport == "ssh" and not EV3_INTERFACE_AVAILABLE:
                print("Error: No EV3 interface available. Use --local for mock mode.")
                return
            
            remote = RemotePuppy(host=args.host, transport=transport)
            
            # Flow mode - interactive session
            if action == "flow":
                remote.flow()
                return
            
            try:
                result = remote.execute_action(action)
            finally:
                remote.disconnect()


if __name__ == "__main__":
    main()
