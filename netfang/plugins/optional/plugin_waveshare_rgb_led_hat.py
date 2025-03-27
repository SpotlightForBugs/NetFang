import os
import subprocess
import sys
import time
import threading
import logging
from typing import Any, Dict, List, Optional, Tuple

from netfang import api
from netfang.api import pi_utils
from netfang.db.database import add_plugin_log
from netfang.plugins.base_plugin import BasePlugin

class ColorEnum:
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    MAGENTA = "magenta"
    YELLOW = "yellow"
    CYAN = "cyan"
    WHITE = "white"
    ORANGE = "orange"
    PURPLE = "purple"
    OFF = "off"

class AnimationEnum:
    SOLID = "solid"          # Static color
    PULSE = "pulse"          # Pulsing color (brightness varies)
    BLINK = "blink"          # Blinking between color and off
    RAINBOW = "rainbow"      # Cycle through colors
    CHASE = "chase"          # Running light effect
    ALTERNATING = "alternate" # Alternating between two colors
    ALERT = "alert"          # Alert pattern (rapid blinks)
    SCANNING = "scanning"    # Scanning pattern (rotating)

# Flag to track if this plugin is enabled
_plugin_enabled = False

def subprocess_for_led_control(color: str, duration: int, brightness: int, animation: str = "solid", 
                               alt_color: str = None, speed: int = 5):
    """
    Control the Waveshare RGB LED Hat with enhanced animation capabilities.
    
    Args:
        color: Primary color for the LED
        duration: How long to display in seconds
        brightness: LED brightness (1-10)
        animation: Animation pattern to display
        alt_color: Secondary color for animations that use two colors
        speed: Animation speed (1-10, 10 being fastest)
    """
    # Skip everything if the plugin is not enabled
    if not _plugin_enabled:
        return
        
    # Only check Raspberry Pi compatibility if the plugin is enabled
    if not pi_utils.is_pi_zero_2():
        logging.warning("This plugin is only compatible with Raspberry Pi Zero 2 W.")
        return
    
    # Get the script path
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts/waveshare_rgb_led_hat.py"))
    
    # Build command with animation parameters
    cmd = [
        "sudo",
        sys.executable,
        script_path,
        "--color", color,
        "--timeout", str(duration),
        "--brightness", str(brightness),
        "--animation", animation,
        "--speed", str(speed)
    ]
    
    # Add alt_color if provided
    if alt_color:
        cmd.extend(["--alt-color", alt_color])
    
    # Execute the command using streaming subprocess for real-time output
    try:
        # Import the streaming subprocess function
        from netfang.streaming_subprocess import run_subprocess_sync
        
        # Use the streaming subprocess runner
        result = run_subprocess_sync(
            "WaveshareRGBLEDHat",  # Plugin name
            cmd,                    # Command to run
            db_path=None,           # We'll handle logging elsewhere
            timeout=(duration + 5) if duration > 0 else None  # Add a buffer for the timeout (5 seconds) if needed
        )
        
        if result["status"] != "completed" or result["return_code"] != 0:
            error = result["stderr"] if result["stderr"] else f"LED control failed with code {result['return_code']}"
            logging.error(f"Error controlling LED: {error}")
            
    except Exception as e:
        logging.error(f"Unexpected error controlling LED: {str(e)}")

class AnimationController:
    """
    Manages animations for the LED hat, handling background animation threads.
    """
    
    def __init__(self):
        self.current_thread = None
        self.stop_event = threading.Event()
        self.logger = logging.getLogger(__name__)
        
    def start_animation(self, animation_name: str, color: str, duration: int = 0, 
                        brightness: int = 5, alt_color: str = None, speed: int = 5):
        """
        Start an LED animation in a background thread with the ability to stop it.
        
        Args:
            animation_name: Name of the animation to run
            color: Primary color for the animation
            duration: How long to run in seconds (0 for indefinite)
            brightness: LED brightness (1-10)
            alt_color: Secondary color for animations that use two colors
            speed: Animation speed (1-10, 10 being fastest)
        """
        # Skip everything if the plugin is not enabled
        if not _plugin_enabled:
            return
            
        # Stop any running animation
        self.stop_animation()
        
        # Reset stop event
        self.stop_event = threading.Event()
        
        # Create and start the animation thread
        self.current_thread = threading.Thread(
            target=self._run_animation,
            args=(animation_name, color, duration, brightness, alt_color, speed)
        )
        self.current_thread.daemon = True
        self.current_thread.start()
        
        self.logger.debug(f"Started animation: {animation_name}, color: {color}, duration: {duration}")
        
    def stop_animation(self):
        """Stop any currently running animation"""
        if self.current_thread and self.current_thread.is_alive():
            self.stop_event.set()
            self.current_thread.join(timeout=1.0)
            self.logger.debug("Stopped current animation")
            
    def _run_animation(self, animation_name: str, color: str, duration: int,
                      brightness: int, alt_color: str, speed: int):
        """
        Run the animation in a background thread.
        
        For indefinite animations (duration=0), will run until stop_event is set.
        For timed animations, will run for specified duration or until stop_event.
        """
        start_time = time.time()
        try:
            if duration > 0:
                # Run with a fixed duration
                subprocess_for_led_control(
                    color, duration, brightness, animation_name, alt_color, speed
                )
            else:
                # Run indefinitely until stop_event or in chunks
                chunk_duration = 30  # Run in 30-second chunks
                while not self.stop_event.is_set():
                    subprocess_for_led_control(
                        color, chunk_duration, brightness, animation_name, alt_color, speed
                    )
                    
                    # Check if we should stop
                    if self.stop_event.is_set():
                        break
                        
            # Turn off the LED when done
            if not self.stop_event.is_set():
                subprocess_for_led_control(ColorEnum.OFF, 1, 1, AnimationEnum.SOLID)
                
        except Exception as e:
            self.logger.error(f"Error in animation thread: {str(e)}")
        finally:
            # Ensure LED is off when thread exits
            try:
                subprocess_for_led_control(ColorEnum.OFF, 1, 1, AnimationEnum.SOLID)
            except:
                pass
            
            self.logger.debug(f"Animation completed after {time.time() - start_time:.1f} seconds")

class WaveshareRGBLEDHat(BasePlugin):
    name = "WaveshareRGBLEDHat"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        self.animation_controller = AnimationController()
        self.db_path = config.get("database_path", "netfang.db")
        
        # Configure default animation settings from config
        plugin_cfg = config.get("plugin_config", {}).get("waveshare_rgb_led_hat", {})
        self.default_brightness = plugin_cfg.get("brightness", 5)
        self.default_duration = plugin_cfg.get("duration", 5)
        self.default_speed = plugin_cfg.get("speed", 5)
        self.animations_enabled = plugin_cfg.get("animations_enabled", True)
        
        # Check if the plugin is enabled in the config
        is_enabled = config.get("enabled", False)
        if is_enabled:
            self.logger.info(f"[{self.name}] Initialized with brightness={self.default_brightness}, "
                          f"speed={self.default_speed}, animations_enabled={self.animations_enabled}")
        
        # Only log to database if the plugin is enabled
        if is_enabled:
            add_plugin_log(self.db_path, self.name, "Plugin initialized")

    def on_setup(self) -> None:
        # Blue pulse animation indicates initialization
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.PULSE, ColorEnum.BLUE, 
                self.default_duration, self.default_brightness, 
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Setup complete")

    def on_enable(self) -> None:
        # Set the global enabled flag for LED control functions
        global _plugin_enabled
        _plugin_enabled = True
        
        # Green pulse animation indicates successful enablement
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.PULSE, ColorEnum.GREEN, 
                self.default_duration, self.default_brightness, 
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Plugin enabled")
        
        # Register dashboard actions
        self.register_dashboard_actions()

    def on_disable(self) -> None:
        # Clear the global enabled flag to prevent LED control when disabled
        global _plugin_enabled
        _plugin_enabled = False
        
        # Turn off any animations and clean up
        self.animation_controller.stop_animation()
        add_plugin_log(self.db_path, self.name, "Plugin disabled")

    def on_known_network_connected(self, mac: str) -> None:
        # Green solid indicates a trusted (known) network
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.SOLID, ColorEnum.GREEN, 
                self.default_duration, self.default_brightness
            )
        add_plugin_log(self.db_path, self.name, f"Known network connected: {mac}")

    def on_new_network_connected(self, mac: str) -> None:
        # Yellow pulsing indicates an unrecognized network
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.PULSE, ColorEnum.YELLOW, 
                self.default_duration, self.default_brightness,
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, f"New network connected: {mac}")

    def on_home_network_connected(self) -> None:
        # Green with blue alternating indicates the home network
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.ALTERNATING, ColorEnum.GREEN, 
                self.default_duration, self.default_brightness,
                alt_color=ColorEnum.BLUE, speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Home network connected")

    def on_disconnected(self) -> None:
        # Red pulsing indicates loss of connection
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.PULSE, ColorEnum.RED, 
                self.default_duration, self.default_brightness,
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Network disconnected")

    def on_alerting(self, alert) -> None:
        # Critical alert: Red alert pattern with increased brightness
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.ALERT, ColorEnum.RED, 
                10, 10,  # Higher brightness and longer duration for alerts
                speed=8  # Faster speed for alerts
            )
        add_plugin_log(self.db_path, self.name, f"Alert triggered: {alert.message}")

    def on_alert_resolved(self, alert) -> None:
        # Green blink pattern indicates alert resolution
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.BLINK, ColorEnum.GREEN, 
                5, self.default_brightness,
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, f"Alert resolved: {alert.message}")

    def on_reconnecting(self) -> None:
        # Cyan chase animation indicates that reconnection is in progress
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.CHASE, ColorEnum.CYAN, 
                0, self.default_brightness,  # Indefinite duration until state changes
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Reconnecting to network")

    def on_connected_home(self) -> None:
        # Green with blue alternating indicates a confirmed home network connection
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.ALTERNATING, ColorEnum.GREEN, 
                self.default_duration, self.default_brightness,
                alt_color=ColorEnum.BLUE, speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Connected to home network")

    def on_connecting(self):
        # Blue chase animation indicates an ongoing connection attempt
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.CHASE, ColorEnum.BLUE, 
                0, self.default_brightness,  # Indefinite duration until state changes
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Connecting to network")

    def on_scanning_in_progress(self):
        # Magenta scanning animation indicates that scanning is in progress
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.SCANNING, ColorEnum.MAGENTA, 
                0, self.default_brightness,  # Indefinite duration until state changes
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Network scanning in progress")
        
    def on_scan_completed(self):
        # Green blink pattern indicates scan completion
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.BLINK, ColorEnum.GREEN, 
                5, self.default_brightness,
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Network scan completed")
        
    def on_connected_blacklisted(self, mac_address):
        # Red alert pattern indicates connection to a blacklisted network
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.ALERT, ColorEnum.RED, 
                0, 8,  # Indefinite duration with high brightness
                speed=8
            )
        add_plugin_log(self.db_path, self.name, f"Connected to blacklisted network: {mac_address}")

    def perform_action(self, args: list) -> None:
        """
        Handle plugin actions for LED control.
        
        Format:
        [plugin_name, "led", animation, color, duration, brightness, alt_color, speed]
        
        Example:
        ["WaveshareRGBLEDHat", "led", "pulse", "blue", "10", "5", "green", "5"]
        """
        if args[0] != self.name:
            return
            
        if len(args) > 1 and args[1] == "led":
            try:
                # Extract parameters with defaults
                animation = args[2] if len(args) > 2 else AnimationEnum.SOLID
                color = args[3] if len(args) > 3 else ColorEnum.GREEN
                duration = int(args[4]) if len(args) > 4 else self.default_duration
                brightness = int(args[5]) if len(args) > 5 else self.default_brightness
                alt_color = args[6] if len(args) > 6 else None
                speed = int(args[7]) if len(args) > 7 else self.default_speed
                
                # Start the animation
                if self.animations_enabled:
                    self.animation_controller.start_animation(
                        animation, color, duration, brightness, alt_color, speed
                    )
                    
                add_plugin_log(self.db_path, self.name, 
                             f"Executed LED action: animation={animation}, color={color}, duration={duration}")
                
            except Exception as e:
                self.logger.error(f"Error executing LED action: {str(e)}")
                add_plugin_log(self.db_path, self.name, f"Error executing LED action: {str(e)}")
        else:
            self.logger.debug(f"Received unhandled action: {args}")
            
    def register_dashboard_actions(self):
        """Register LED control actions in the dashboard"""
        try:
            from netfang.socketio_handler import handler
            import asyncio
            
            # Define available animations for quick access
            animations = [
                {"name": "Solid Color", "id": AnimationEnum.SOLID, "description": "Display a solid color"},
                {"name": "Pulse", "id": AnimationEnum.PULSE, "description": "Pulsing effect"},
                {"name": "Blink", "id": AnimationEnum.BLINK, "description": "Blinking on/off"},
                {"name": "Rainbow", "id": AnimationEnum.RAINBOW, "description": "Cycle through colors"},
                {"name": "Chase", "id": AnimationEnum.CHASE, "description": "Running light effect"},
                {"name": "Alternating", "id": AnimationEnum.ALTERNATING, "description": "Alternate between colors"}
            ]
            
            # Define available colors
            colors = [
                {"name": "Red", "id": ColorEnum.RED},
                {"name": "Green", "id": ColorEnum.GREEN},
                {"name": "Blue", "id": ColorEnum.BLUE},
                {"name": "Yellow", "id": ColorEnum.YELLOW},
                {"name": "Magenta", "id": ColorEnum.MAGENTA},
                {"name": "Cyan", "id": ColorEnum.CYAN},
                {"name": "White", "id": ColorEnum.WHITE},
                {"name": "Orange", "id": ColorEnum.ORANGE},
                {"name": "Purple", "id": ColorEnum.PURPLE}
            ]
            
            # Register each animation as an action
            async def register_actions():
                for anim in animations:
                    for color in colors:
                        action_id = f"led_{anim['id']}_{color['id']}"
                        action_name = f"{anim['name']} - {color['name']}"
                        
                        await handler.register_dashboard_action(
                            self.name,
                            action_id,
                            action_name,
                            f"{anim['description']} in {color['name']}",
                            "system"
                        )
            
            # Run the async registration
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(register_actions())
            else:
                loop.run_until_complete(register_actions())
                
            add_plugin_log(self.db_path, self.name, "Registered dashboard LED control actions")
            
        except Exception as e:
            self.logger.error(f"Error registering dashboard actions: {str(e)}")
            add_plugin_log(self.db_path, self.name, f"Error registering dashboard actions: {str(e)}")
            
    # Register dashboard actions when the plugin is enabled
    def on_enable(self) -> None:
        # Green pulse animation indicates successful enablement
        if self.animations_enabled:
            self.animation_controller.start_animation(
                AnimationEnum.PULSE, ColorEnum.GREEN, 
                self.default_duration, self.default_brightness, 
                speed=self.default_speed
            )
        add_plugin_log(self.db_path, self.name, "Plugin enabled")
        
        # Register dashboard actions
        self.register_dashboard_actions()
