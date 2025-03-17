# netfang/plugins/optional/plugin_waveshare_rgb_led_hat.py
import os
import subprocess
import sys
import platform
import importlib.util
from typing import Any, Dict

from netfang.plugins.base_plugin import BasePlugin
from netfang.scripts.waveshare_rgb_led_hat import ColorEnum


def is_raspberry_pi():
    try:
        return platform.machine().startswith('arm') and 'raspberry' in platform.platform().lower()
    except:
        return False

def has_rpi_ws281x():
    return importlib.util.find_spec("rpi_ws281x") is not None

USE_HARDWARE = is_raspberry_pi() and has_rpi_ws281x()


def subprocess_for_led_control(color: str, duration: int, brightness: int, sim_mode=None):
    if sim_mode or not USE_HARDWARE:
        print(f"[LED Simulation] Color: {color}, Duration: {duration}s, Brightness: {brightness}")
        return

    try:
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                 "../../scripts/waveshare_rgb_led_hat.py"))
        subprocess.run([
            "sudo",
            sys.executable,
            script_path,
            "--color", color,
            "--timeout", str(duration),
            "--brightness", str(brightness)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[LED Hardware Error] Failed to control LED HAT: {e}")
        print(f"[LED Simulation] Color: {color}, Duration: {duration}s, Brightness: {brightness}")
        global USE_HARDWARE
        USE_HARDWARE = False


class WaveShareRGBLEDHat(BasePlugin):
    name = "WaveShareRGBLEDHat"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        
        self.sim_mode = config.get("plugin_config", {}).get("simulation_mode", False)
        if self.sim_mode:
            global USE_HARDWARE
            USE_HARDWARE = False
            
        subprocess_for_led_control(ColorEnum.RED, 5, 1, self.sim_mode)
        print(f"[{self.name}] __init__ complete.")

    def on_setup(self) -> None:
        subprocess_for_led_control(ColorEnum.BLUE, 5, 1, self.sim_mode)
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        subprocess_for_led_control(ColorEnum.GREEN, 5, 1, self.sim_mode)
        print(f"[{self.name}] Enabled.")

    def on_disable(self) -> None:
        subprocess_for_led_control(ColorEnum.WHITE, 5, 1, self.sim_mode)
        print(f"[{self.name}] Disabled.")

    def on_known_network_connected(self, mac: str, name: str, is_blacklisted: bool) -> None:
        subprocess_for_led_control(ColorEnum.MAGENTA, 5, 1, self.sim_mode)
        print(
            f"[{self.name}] WaveShare RGB LED Hat received known network connection event: {mac=}, {name=}, {is_blacklisted=}")

    def on_new_network_connected(self, mac: str, name: str) -> None:
        subprocess_for_led_control(ColorEnum.YELLOW, 5, 1, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received new network connection event: {mac=}, {name=}")

    def on_home_network_connected(self) -> None:
        subprocess_for_led_control(ColorEnum.ORANGE, 5, 1, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received home network connection event")

    def on_disconnected(self) -> None:
        subprocess_for_led_control(ColorEnum.RED, 5, 1, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received disconnected event")

    def on_alerting(self, message: str) -> None:
        subprocess_for_led_control(ColorEnum.RED, 10, 10, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received alerting event: {message=}")

    def on_reconnecting(self) -> None:
        subprocess_for_led_control(ColorEnum.RED, 5, 1, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received reconnecting event")

    def on_connected_home(self) -> None:
        subprocess_for_led_control(ColorEnum.GREEN, 5, 1, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received connected home event")

    def on_connecting(self):
        subprocess_for_led_control(ColorEnum.BLUE, 5, 1, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received connecting event")

    def on_scanning_in_progress(self):
        subprocess_for_led_control(ColorEnum.CYAN, 5, 1, self.sim_mode)
        print(f"[{self.name}] WaveShare RGB LED Hat received scanning in progress event")

    def perform_action(self, args: list) -> None:
        print(f"[{self.name}] WaveShare RGB LED Hat received perform_action event: {args=}")
        print(f"[{self.name}] This means that the plugin {args[0]} is requested to perform an action.")
