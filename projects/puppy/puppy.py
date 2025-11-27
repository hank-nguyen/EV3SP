#!/usr/bin/env python3
"""
EV3 Puppy Robot Controller
--------------------------
Flexible controller with CLI actions and Hydra configuration.
Compatible with both local EV3 execution and remote control via ev3_interface.

Usage:
    python puppy.py action=standup                    # Stand up (remote by default)
    python puppy.py action=sitdown                    # Sit down
    python puppy.py action=bark                       # Bark
    python puppy.py action=stretch                    # Stretch
    python puppy.py action=hop                        # Hop
    python puppy.py action=sleep                      # Go to sleep
    python puppy.py action=wakeup                     # Wake up
    python puppy.py action=stream                     # Stream sensor data
    python puppy.py connection=local action=run       # Run on EV3 directly
"""

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
# Remote Puppy Controller (sends commands to EV3 via SSH)
# -----------------------------------------------------------------------------

class RemotePuppy:
    """Control EV3 Puppy remotely via SSH."""
    
    # Daemon file to upload (in same directory as this script)
    DAEMON_PUPPY_FILE = "puppy_daemon.py"
    
    # Legacy embedded script (fallback if files not found)
    EV3_DAEMON_SCRIPT = '''#!/usr/bin/env python3
import sys
import time
import json

# ev3dev2 imports - done ONCE at startup
from ev3dev2.motor import LargeMotor, MediumMotor, OUTPUT_A, OUTPUT_C, OUTPUT_D
from ev3dev2.sensor.lego import TouchSensor, ColorSensor
from ev3dev2.sensor import INPUT_1, INPUT_4
from ev3dev2.sound import Sound
from ev3dev2.display import Display

# Initialize ONCE
sound = Sound()
lcd = Display()
left_motor = None
right_motor = None
head_motor = None
touch_sensor = None
color_sensor = None

# Eye styles using PIL for drawing (compatible with older PIL)
from PIL import Image, ImageDraw

def draw_eyes(style="neutral"):
    # Create image buffer (178x128 is EV3 screen size)
    img = Image.new("1", (178, 128), color=0)  # 1-bit, black background
    draw = ImageDraw.Draw(img)
    
    cx1, cx2 = 45, 133  # eye centers
    cy = 64
    
    if style == "neutral":
        # Round open eyes - white circles with black pupils
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-10, cy-10, cx1+10, cy+10], fill=0)
        draw.ellipse([cx2-10, cy-10, cx2+10, cy+10], fill=0)
    
    elif style == "happy":
        # Happy curved eyes (^_^)
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        # Arc smiles using ellipse outline
        draw.arc([cx1-15, cy-15, cx1+15, cy+15], 0, 180, fill=0)
        draw.arc([cx2-15, cy-15, cx2+15, cy+15], 0, 180, fill=0)
        draw.arc([cx1-14, cy-14, cx1+14, cy+14], 0, 180, fill=0)
        draw.arc([cx2-14, cy-14, cx2+14, cy+14], 0, 180, fill=0)
    
    elif style == "angry":
        # Angry slanted eyes
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-8, cy-3, cx1+12, cy+17], fill=0)
        draw.ellipse([cx2-12, cy-3, cx2+8, cy+17], fill=0)
        # Angry eyebrows using polygons
        draw.polygon([(cx1-20, cy-30), (cx1+15, cy-20), (cx1+15, cy-16), (cx1-20, cy-26)], fill=0)
        draw.polygon([(cx2+20, cy-30), (cx2-15, cy-20), (cx2-15, cy-16), (cx2+20, cy-26)], fill=0)
    
    elif style == "sleepy":
        # Half-closed eyes
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        # Eyelids
        draw.rectangle([cx1-26, cy-26, cx1+26, cy-5], fill=0)
        draw.rectangle([cx2-26, cy-26, cx2+26, cy-5], fill=0)
        draw.ellipse([cx1-6, cy, cx1+6, cy+12], fill=0)
        draw.ellipse([cx2-6, cy, cx2+6, cy+12], fill=0)
    
    elif style == "surprised":
        # Big wide eyes
        draw.ellipse([cx1-30, cy-30, cx1+30, cy+30], fill=1)
        draw.ellipse([cx2-30, cy-30, cx2+30, cy+30], fill=1)
        draw.ellipse([cx1-15, cy-15, cx1+15, cy+15], fill=0)
        draw.ellipse([cx2-15, cy-15, cx2+15, cy+15], fill=0)
        # Highlights
        draw.ellipse([cx1-12, cy-12, cx1-4, cy-4], fill=1)
        draw.ellipse([cx2-12, cy-12, cx2-4, cy-4], fill=1)
    
    elif style == "love":
        # Heart eyes
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        # Hearts made of overlapping circles + triangle
        draw.ellipse([cx1-12, cy-10, cx1, cy+2], fill=0)
        draw.ellipse([cx1, cy-10, cx1+12, cy+2], fill=0)
        draw.polygon([(cx1-10, cy-2), (cx1, cy+12), (cx1+10, cy-2)], fill=0)
        draw.ellipse([cx2-12, cy-10, cx2, cy+2], fill=0)
        draw.ellipse([cx2, cy-10, cx2+12, cy+2], fill=0)
        draw.polygon([(cx2-10, cy-2), (cx2, cy+12), (cx2+10, cy-2)], fill=0)
    
    elif style == "wink":
        # One eye open, one closed
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-10, cy-10, cx1+10, cy+10], fill=0)
        # Wink - horizontal line using rectangle
        draw.rectangle([cx2-18, cy-2, cx2+18, cy+2], fill=0)
    
    elif style == "off":
        pass  # already black
    
    else:  # default neutral
        draw.ellipse([cx1-25, cy-25, cx1+25, cy+25], fill=1)
        draw.ellipse([cx2-25, cy-25, cx2+25, cy+25], fill=1)
        draw.ellipse([cx1-10, cy-10, cx1+10, cy+10], fill=0)
        draw.ellipse([cx2-10, cy-10, cx2+10, cy+10], fill=0)
    
    lcd.image.paste(img, (0, 0))
    lcd.update()

def init_hardware():
    global left_motor, right_motor, head_motor, touch_sensor, color_sensor
    try:
        left_motor = LargeMotor(OUTPUT_D)
    except:
        pass
    try:
        right_motor = LargeMotor(OUTPUT_A)
    except:
        pass
    try:
        head_motor = MediumMotor(OUTPUT_C)
    except:
        pass
    try:
        touch_sensor = TouchSensor(INPUT_1)
    except:
        pass
    try:
        color_sensor = ColorSensor(INPUT_4)
    except:
        pass

def standup():
    if not left_motor or not right_motor:
        return "ERROR: motors"
    draw_eyes("neutral")
    left_motor.on_for_degrees(speed=30, degrees=25, block=False)
    right_motor.on_for_degrees(speed=30, degrees=25, block=True)
    time.sleep(0.3)
    left_motor.on_for_degrees(speed=25, degrees=40, block=False)
    right_motor.on_for_degrees(speed=25, degrees=40, block=True)
    return "OK"

def sitdown():
    if not left_motor or not right_motor:
        return "ERROR: motors"
    draw_eyes("sleepy")
    left_motor.on(speed=-25)
    right_motor.on(speed=-25)
    time.sleep(0.8)
    left_motor.off()
    right_motor.off()
    return "OK"

def bark():
    draw_eyes("surprised")
    sound.speak("woof woof")
    # Keep surprised eyes - don't reset
    return "OK"

def stretch():
    if not left_motor or not right_motor:
        return "ERROR: motors"
    draw_eyes("sleepy")
    left_motor.on_for_degrees(speed=30, degrees=25, block=False)
    right_motor.on_for_degrees(speed=30, degrees=25, block=True)
    time.sleep(0.3)
    left_motor.on_for_degrees(speed=25, degrees=40, block=False)
    right_motor.on_for_degrees(speed=25, degrees=40, block=True)
    left_motor.on_for_degrees(speed=30, degrees=60, block=False)
    right_motor.on_for_degrees(speed=30, degrees=60, block=True)
    left_motor.on_for_degrees(speed=30, degrees=-60, block=False)
    right_motor.on_for_degrees(speed=30, degrees=-60, block=True)
    draw_eyes("neutral")
    return "OK"

def hop():
    if not left_motor or not right_motor:
        return "ERROR: motors"
    draw_eyes("surprised")
    left_motor.on(speed=50)
    right_motor.on(speed=50)
    time.sleep(0.2)
    left_motor.off(brake=True)
    right_motor.off(brake=True)
    time.sleep(0.2)
    left_motor.on(speed=-25)
    right_motor.on(speed=-25)
    time.sleep(0.2)
    left_motor.off()
    right_motor.off()
    # Keep surprised eyes - don't reset
    return "OK"

def head_up():
    draw_eyes("neutral")
    if head_motor:
        head_motor.on_for_degrees(speed=15, degrees=40)
        return "OK"
    return "ERROR: head"

def head_down():
    draw_eyes("sleepy")
    if head_motor:
        head_motor.on_for_degrees(speed=15, degrees=-40)
        return "OK"
    return "ERROR: head"

def happy():
    draw_eyes("love")
    sound.speak("woof")
    if left_motor and right_motor:
        left_motor.on(speed=50)
        right_motor.on(speed=50)
        time.sleep(0.2)
        left_motor.off(brake=True)
        right_motor.off(brake=True)
        time.sleep(0.2)
        left_motor.on(speed=-25)
        right_motor.on(speed=-25)
        time.sleep(0.2)
        left_motor.off()
        right_motor.off()
    draw_eyes("happy")
    sound.speak("woof")
    # Keep happy eyes
    return "OK"

def angry():
    draw_eyes("angry")
    sound.speak("grrr")
    if left_motor and right_motor:
        left_motor.on_for_degrees(speed=30, degrees=25, block=False)
        right_motor.on_for_degrees(speed=30, degrees=25, block=True)
        time.sleep(0.3)
        left_motor.on_for_degrees(speed=25, degrees=40, block=False)
        right_motor.on_for_degrees(speed=25, degrees=40, block=True)
    sound.speak("woof woof")
    # Keep angry eyes
    return "OK"

def status():
    r = {"m": {}, "s": {}}
    if left_motor:
        r["m"]["l"] = left_motor.position
    if right_motor:
        r["m"]["r"] = right_motor.position
    if head_motor:
        r["m"]["h"] = head_motor.position
    if touch_sensor:
        r["s"]["t"] = touch_sensor.is_pressed
    if color_sensor:
        r["s"]["c"] = color_sensor.color_name
    return json.dumps(r)

def stop():
    if left_motor:
        left_motor.off()
    if right_motor:
        right_motor.off()
    if head_motor:
        head_motor.off()
    return "OK"

ACTIONS = {
    "standup": standup, "sitdown": sitdown, "bark": bark,
    "stretch": stretch, "hop": hop, "head_up": head_up,
    "head_down": head_down, "happy": happy, "angry": angry,
    "status": status, "stop": stop,
}

# Eye styles that can be called directly
EYE_STYLES = ["neutral", "happy", "angry", "sleepy", "surprised", "love", "wink", "off"]

def stop_brickman():
    import subprocess
    try:
        subprocess.call("echo maker | sudo -S systemctl stop brickman 2>/dev/null", shell=True)
        time.sleep(0.5)
    except:
        pass

def start_brickman():
    import subprocess
    try:
        subprocess.call("echo maker | sudo -S systemctl start brickman 2>/dev/null", shell=True)
    except:
        pass

if __name__ == "__main__":
    # Stop brickman to take full control of screen
    stop_brickman()
    
    init_hardware()
    draw_eyes("neutral")
    sys.stdout.write("READY\\n")
    sys.stdout.flush()
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().lower()
            if cmd == "quit" or cmd == "exit":
                draw_eyes("sleepy")
                break
            
            # Handle eyes command with style parameter
            if cmd.startswith("eyes"):
                parts = cmd.split()
                style = parts[1] if len(parts) > 1 else "neutral"
                if style in EYE_STYLES:
                    draw_eyes(style)
                    sys.stdout.write("OK: eyes " + style + "\\n")
                else:
                    sys.stdout.write("OK: styles=" + ",".join(EYE_STYLES) + "\\n")
                sys.stdout.flush()
                continue
            
            if cmd in ACTIONS:
                result = ACTIONS[cmd]()
                sys.stdout.write(str(result) + "\\n")
            else:
                sys.stdout.write("ERR: " + cmd + "\\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write("ERR: " + str(e) + "\\n")
            sys.stdout.flush()
    
    stop()
    # Restart brickman when done
    start_brickman()
'''

    COMMANDS_HELP = """
Commands: standup, sitdown, bark, stretch, hop
          head_up, head_down, happy, angry, status, stop
          eyes <style> - change display
            styles: neutral, happy, angry, sleepy,
                    surprised, love, wink, off
          quit/exit/q - disconnect"""

    def __init__(self, host: str = "ev3dev.local", user: str = "robot", 
                 password: str = "maker", sudo_password: str = "maker"):
        self.host = host
        self.user = user
        self.password = password
        self.sudo_password = sudo_password
        self._ev3: Optional[EV3Interface] = None
        self._channel = None
        self._stdin = None
        self._stdout = None
        self._daemon_running = False
        self._script_dir = os.path.dirname(os.path.abspath(__file__))

    def _connect(self):
        """Connect to EV3 if not already connected."""
        if self._ev3 is None:
            if not EV3_INTERFACE_AVAILABLE:
                raise RuntimeError("ev3_interface not available")
            self._ev3 = EV3Interface(self.host, self.user, self.password)
            self._ev3.connect()

    def _upload_daemon(self):
        """Upload daemon script to EV3."""
        self._connect()
        import tempfile
        
        # Try external puppy_daemon.py file first
        puppy_file = os.path.join(self._script_dir, self.DAEMON_PUPPY_FILE)
        
        if os.path.exists(puppy_file):
            # Read and inject sudo password
            with open(puppy_file, 'r') as f:
                content = f.read()
            content = content.replace(
                'SUDO_PASSWORD = "maker"',
                'SUDO_PASSWORD = "' + self.sudo_password + '"'
            )
            
            # Upload with injected password
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(content)
                temp_path = f.name
            self._ev3.upload_file(temp_path, "puppy_daemon.py")
            os.unlink(temp_path)
        else:
            # Fallback to embedded script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(self.EV3_DAEMON_SCRIPT)
                temp_path = f.name
            self._ev3.upload_file(temp_path, "puppy_daemon.py")
            os.unlink(temp_path)

    def _start_daemon(self):
        """Start persistent daemon on EV3."""
        if self._daemon_running:
            return
        
        self._upload_daemon()
        
        # Open channel and exec daemon
        transport = self._ev3._ssh.get_transport()
        self._channel = transport.open_session()
        self._channel.exec_command("cd /home/robot/ev3 && python3 -u puppy_daemon.py")
        
        # Set up stdin for writing
        self._stdin = self._channel.makefile_stdin('wb', -1)
        self._stdout = self._channel.makefile('r', -1)
        
        # Wait for READY signal
        response = self._stdout.readline().strip()
        if "READY" in response:
            self._daemon_running = True
            print("✓ Daemon ready")
        else:
            raise RuntimeError("Daemon failed: " + response)

    def _send_command(self, cmd: str) -> str:
        """Send command to daemon and get response."""
        try:
            self._stdin.write((cmd + "\n").encode())
            self._stdin.flush()
            response = self._stdout.readline().strip()
            if not response and cmd != "quit":
                raise OSError("Socket is closed")
            return response
        except (OSError, IOError) as e:
            raise OSError("Socket is closed: " + str(e))

    def execute_action(self, action: str) -> dict:
        """Execute action on remote EV3 (single command mode)."""
        result = {"action": action, "success": False, "remote": True}
        
        try:
            self._connect()
            self._upload_daemon()
            print("[RemotePuppy] Executing '%s'..." % action)
            
            # For single commands, just run directly
            stdout, stderr, code = self._ev3.execute_command(
                "cd /home/robot/ev3 && echo '%s' | python3 -u puppy_daemon.py" % action,
                timeout=30
            )
            
            result["stdout"] = stdout.strip()
            result["exit_code"] = code
            result["success"] = "OK" in stdout or "READY" in stdout
            
            # Parse output (skip READY line)
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
        """Interactive flow mode with persistent daemon - ultra low latency."""
        print("=" * 50)
        print("EV3 Puppy Flow Mode (Low Latency)")
        print("=" * 50)
        
        try:
            self._connect()
            self._start_daemon()
            
            print("\nCommands: standup, sitdown, bark, stretch, hop")
            print("          head_up, head_down, happy, angry, status, stop")
            print("          eyes <style> - change display")
            print("            styles: neutral, happy, angry, sleepy,")
            print("                    surprised, love, wink, off")
            print("          quit/exit/q - disconnect")
            print("-" * 50)
            
            while True:
                try:
                    cmd = input("\n> ").strip().lower()
                    
                    if not cmd:
                        continue
                    
                    if cmd in ("quit", "exit", "q"):
                        self._send_command("quit")
                        print("Goodbye!")
                        break
                    
                    if cmd == "help":
                        print("standup sitdown bark stretch hop")
                        print("head_up head_down happy angry status stop")
                        print("eyes <style>: neutral happy angry sleepy surprised love wink off")
                        continue
                    
                    # Send to daemon - instant response!
                    t0 = time.time()
                    response = self._send_command(cmd)
                    latency = (time.time() - t0) * 1000
                    
                    print("[EV3] %s (%.0fms)" % (response, latency))
                        
                except KeyboardInterrupt:
                    print("\n\nInterrupted.")
                    try:
                        self._send_command("quit")
                    except:
                        pass
                    break
                except EOFError:
                    print("\nGoodbye!")
                    break
                except OSError as e:
                    if "Socket is closed" in str(e) or "closed" in str(e).lower():
                        print("\n[Disconnected] EV3 connection closed (back button?)")
                        break
                    print("[Error] %s" % e)
                except Exception as e:
                    err_str = str(e).lower()
                    if "socket" in err_str or "closed" in err_str or "eof" in err_str:
                        print("\n[Disconnected] Connection lost")
                        break
                    print("[Error] %s" % e)
                    
        except Exception as e:
            print("Connection error: %s" % e)
        finally:
            self.disconnect()

    def disconnect(self):
        """Disconnect from EV3."""
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


# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

def run_with_config(cfg: DictConfig):
    """Run puppy with Hydra config."""
    config = PuppyConfig.from_hydra(cfg)
    action = cfg.get("action", "run")
    connection_mode = cfg.connection.get("mode", "remote") if hasattr(cfg, 'connection') else "remote"
    
    # Determine mode: local (on EV3), remote (SSH), or mock
    if ON_EV3 or connection_mode == "local":
        # Running directly on EV3 or forced local mode
        mode = "EV3" if ON_EV3 else "Mock"
        print("[EV3 Puppy] Action: %s, Mode: %s" % (action, mode))
        puppy = Puppy(config)
        result = puppy.execute_action(action)
    else:
        # Remote mode - send commands via SSH
        host = cfg.connection.get("host", "ev3dev.local")
        print("[EV3 Puppy] Action: %s, Mode: Remote (%s)" % (action, host))
        
        if not EV3_INTERFACE_AVAILABLE:
            print("Error: ev3_interface not available. Install paramiko.")
            return {"success": False, "error": "ev3_interface not available"}
        
        remote = RemotePuppy(
            host=host,
            user=cfg.connection.get("user", "robot"),
            password=cfg.connection.get("password", "maker"),
            sudo_password=cfg.connection.get("sudo_password", "maker"),
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
        
        if args.local or ON_EV3:
            puppy = Puppy()
            result = puppy.execute_action(action)
            if action == "status":
                print(json.dumps(result.get("status", {}), indent=2))
        else:
            if not EV3_INTERFACE_AVAILABLE:
                print("Error: ev3_interface not available. Use --local for mock mode.")
                return
            remote = RemotePuppy(host=args.host)
            
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
