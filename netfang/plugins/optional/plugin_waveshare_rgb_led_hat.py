import os
import subprocess
import sys
from typing import Any, Dict

from netfang import api
from netfang.api import pi_utils
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

def subprocess_for_led_control(color: str, duration: int, brightness: int):
    if not pi_utils.is_pi_zero_2():
        print("This plugin is only compatible with Raspberry Pi Zero 2 W.")
        return
    # This function will be used to control the LED Hat
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts/waveshare_rgb_led_hat.py"))
    subprocess.run([
        "sudo",
        sys.executable,
        script_path,
        "--color", color,
        "--timeout", str(duration),
        "--brightness", str(brightness)
    ], check=True)

class WaveshareRGBLEDHat(BasePlugin):
    name = "WaveshareRGBLEDHat"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        print(f"[{self.name}] __init__ complete.")

    def on_setup(self) -> None:
        # Blue indicates initialization.
        subprocess_for_led_control(ColorEnum.BLUE, 5, 1)
        print(f"[{self.name}] Setup complete.")

    def on_enable(self) -> None:
        # Green indicates successful enablement.
        subprocess_for_led_control(ColorEnum.GREEN, 5, 1)
        print(f"[{self.name}] Enabled.")

    def on_disable(self) -> None:
        # White indicates deactivation.
        subprocess_for_led_control(ColorEnum.WHITE, 5, 1)
        print(f"[{self.name}] Disabled.")

    def on_known_network_connected(self, mac: str) -> None:
        # Green indicates a trusted (known) network.
        subprocess_for_led_control(ColorEnum.GREEN, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received known network connection event: {mac=}")

    def on_new_network_connected(self, mac: str) -> None:
        # Yellow indicates an unrecognized network.
        subprocess_for_led_control(ColorEnum.YELLOW, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received new network connection event: {mac=}")

    def on_home_network_connected(self) -> None:
        # Orange indicates the home network.
        subprocess_for_led_control(ColorEnum.ORANGE, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received home network connection event")

    def on_disconnected(self) -> None:
        # Red indicates loss of connection.
        subprocess_for_led_control(ColorEnum.RED, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received disconnected event")

    def on_alerting(self, message: str) -> None:
        # Critical alert: Red with increased brightness and duration.
        subprocess_for_led_control(ColorEnum.RED, 10, 10)
        print(f"[{self.name}] WaveShare RGB LED Hat received alerting event: {message=}")

    def on_reconnecting(self) -> None:
        # Cyan indicates that reconnection is in progress.
        subprocess_for_led_control(ColorEnum.CYAN, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received reconnecting event")

    def on_connected_home(self) -> None:
        # Green indicates a confirmed home network connection.
        subprocess_for_led_control(ColorEnum.GREEN, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received connected home event")

    def on_connecting(self):
        # Blue indicates an ongoing connection attempt.
        subprocess_for_led_control(ColorEnum.BLUE, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received connecting event")

    def on_scanning_in_progress(self):
        # Magenta indicates that scanning is in progress.
        subprocess_for_led_control(ColorEnum.MAGENTA, 5, 1)
        print(f"[{self.name}] WaveShare RGB LED Hat received scanning in progress event")

    def perform_action(self, args: list) -> None:
        print(f"[{self.name}] WaveShare RGB LED Hat received perform_action event: {args=}")
        print(f"[{self.name}] This means that the plugin {args[0]} is requested to perform an action.")
