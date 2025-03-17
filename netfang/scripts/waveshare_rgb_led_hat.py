#!/usr/bin/env python
# encoding: utf-8
"""
WS2812 LED Strip Async Color Setter

CONTAINS CODE FROM: WAVESHARE LED HAT EXAMPLES by Waveshare Inc. (https://www.waveshare.com/wiki/LED_HAT)

This script allows you to set the LED strip to a specified color
(with extended options: red, green, blue, magenta, yellow, cyan, white, orange)
with a chosen brightness level, turn it on or off,
optionally updating only one LED, and optionally setting a timeout after which the LED(s) turn off.
It uses asynchronous sleep for non-blocking timeout handling.
"""

import argparse
import asyncio

from rpi_ws281x import Adafruit_NeoPixel, Color

# LED strip configuration:
LED_COUNT = 32  # Number of LED pixels.
LED_PIN = 18  # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800kHz)
LED_DMA = 10  # DMA channel to use for generating signal (try 5)
LED_INVERT = False  # True to invert the signal (when using NPN transistor level shift)

# Define color mapping: names to their (R, G, B) values.
COLOR_MAP = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "magenta": (255, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "white": (255, 255, 255),
    "orange": (255, 165, 0)
}


# also provide a color enum so that we can use it in the plugin more easily by importing it
class ColorEnum:
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    MAGENTA = "magenta"
    YELLOW = "yellow"
    CYAN = "cyan"
    WHITE = "white"
    ORANGE = "orange"


def turn_off(strip, index=None):
    """Turn off either a single LED if an index is provided or all LEDs."""
    if index is not None:
        strip.setPixelColor(index, Color(0, 0, 0))
    else:
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


async def main():
    parser = argparse.ArgumentParser(
        description="Async WS2812 LED Strip Color and Brightness Setter with Single LED and Timeout Options"
    )
    parser.add_argument(
        "--color",
        choices=list(COLOR_MAP.keys()),
        default="red",
        help="Set the color of the LED strip. Available choices: " + ", ".join(COLOR_MAP.keys())
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=1,
        help="Set brightness (0-255); default is 1"
    )
    parser.add_argument(
        "--state",
        choices=["on", "off"],
        default="on",
        help="Turn the LED strip on or off"
    )
    parser.add_argument(
        "--led",
        type=int,
        help="If specified, only update the LED at this 0-indexed position"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0,
        help="Time in seconds to keep the LED(s) on before turning off. 0 means no timeout."
    )
    args = parser.parse_args()

    # Create NeoPixel object with the specified configuration.
    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, args.brightness)
    strip.begin()

    if args.state == "off":
        # Turn off all LEDs.
        turn_off(strip)
    else:
        # Get the RGB values for the chosen color.
        r, g, b = COLOR_MAP[args.color]

        # Set the LED(s)
        if args.led is not None:
            # Validate the LED index.
            if args.led < 0 or args.led >= LED_COUNT:
                print("Error: LED index out of range (0 to {})".format(LED_COUNT - 1))
                return
            # Turn off all LEDs first.
            for i in range(strip.numPixels()):
                strip.setPixelColor(i, Color(0, 0, 0))
            # Set only the specified LED.
            strip.setPixelColor(args.led, Color(r, g, b))
        else:
            # Set all pixels to the chosen color.
            for i in range(strip.numPixels()):
                strip.setPixelColor(i, Color(r, g, b))
        strip.show()

        # If a timeout is specified, wait asynchronously and then turn off the LED(s).
        if args.timeout > 0:
            await asyncio.sleep(args.timeout)
            turn_off(strip, index=args.led if args.led is not None else None)


if __name__ == "__main__":
    asyncio.run(main())
