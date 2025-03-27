#!/usr/bin/env python3
import argparse
import time
import random
import sys
import signal
import math
from typing import Optional, List, Tuple
try:
    from rpi_ws281x import PixelStrip, Color
    LED_AVAILABLE = True
except ImportError:
    print("Warning: rpi_ws281x library not available - running in simulation mode")
    LED_AVAILABLE = False

# LED strip configuration:
LED_COUNT = 8         # Number of LED pixels on the Waveshare RGB LED HAT
LED_PIN = 18          # GPIO pin connected to the pixels (18 uses PWM!)
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10          # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255  # Set to 0 for darkest and 255 for brightest
LED_INVERT = False    # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53

# Color values
COLORS = {
    "red": Color(255, 0, 0),
    "green": Color(0, 255, 0),
    "blue": Color(0, 0, 255),
    "white": Color(255, 255, 255),
    "yellow": Color(255, 255, 0),
    "purple": Color(128, 0, 128),
    "magenta": Color(255, 0, 255),
    "cyan": Color(0, 255, 255),
    "orange": Color(255, 165, 0),
    "off": Color(0, 0, 0)
}

# Animation definitions
class Animation:
    def __init__(self, strip, color, alt_color=None, speed=5):
        """
        Base animation class
        
        Args:
            strip: The LED strip instance
            color: Primary color for the animation
            alt_color: Secondary color for animations that use two colors
            speed: Animation speed (1-10, where 10 is fastest)
        """
        self.strip = strip
        self.color = COLORS.get(color, COLORS["white"])
        self.alt_color = COLORS.get(alt_color, COLORS["blue"]) if alt_color else COLORS["off"]
        self.speed = min(max(speed, 1), 10)  # Constrain between 1-10
        self.frame_delay = 0.1 * (11 - self.speed)  # Convert speed to delay (faster = lower delay)
        
    def setup(self):
        """Initialize the animation (called once before running)"""
        pass
        
    def update(self):
        """Update animation frame (called repeatedly while running)"""
        pass
        
    def cleanup(self):
        """Clean up after animation (called once when animation is done)"""
        pass
        
    def clear(self):
        """Clear all LEDs"""
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, COLORS["off"])
        self.strip.show()
        
class SolidAnimation(Animation):
    """Display a static solid color on all LEDs"""
    def update(self):
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.color)
        self.strip.show()
        time.sleep(0.1)  # Small delay to avoid CPU hogging

class PulseAnimation(Animation):
    """Pulse the LEDs by varying the brightness"""
    def __init__(self, strip, color, alt_color=None, speed=5):
        super().__init__(strip, color, alt_color, speed)
        self.brightness_multiplier = 0
        self.increasing = True
        self.step = 0.05 * self.speed  # Speed affects step size
        
    def update(self):
        # Calculate brightness multiplier (0.0 to 1.0)
        if self.increasing:
            self.brightness_multiplier += self.step
            if self.brightness_multiplier >= 1.0:
                self.brightness_multiplier = 1.0
                self.increasing = False
        else:
            self.brightness_multiplier -= self.step
            if self.brightness_multiplier <= 0.1:  # Don't go completely dark
                self.brightness_multiplier = 0.1
                self.increasing = True
                
        # Create a dimmed version of the color
        r = int(((self.color >> 16) & 0xFF) * self.brightness_multiplier)
        g = int(((self.color >> 8) & 0xFF) * self.brightness_multiplier)
        b = int((self.color & 0xFF) * self.brightness_multiplier)
        dimmed_color = Color(r, g, b)
        
        # Apply to all LEDs
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, dimmed_color)
        
        self.strip.show()
        time.sleep(self.frame_delay)

class BlinkAnimation(Animation):
    """Blink between the color and off"""
    def __init__(self, strip, color, alt_color=None, speed=5):
        super().__init__(strip, color, alt_color, speed)
        self.state = True
        
    def update(self):
        # Toggle state
        self.state = not self.state
        
        # Set all LEDs to either the color or off
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.color if self.state else COLORS["off"])
            
        self.strip.show()
        time.sleep(self.frame_delay * 2)  # Longer delay for blink

class RainbowAnimation(Animation):
    """Cycle through all colors of the rainbow"""
    def __init__(self, strip, color, alt_color=None, speed=5):
        super().__init__(strip, color, alt_color, speed)
        self.position = 0
        
    def wheel(self, pos):
        """Generate rainbow colors across 0-255 positions"""
        if pos < 85:
            return Color(pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return Color(255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return Color(0, pos * 3, 255 - pos * 3)
    
    def update(self):
        # Set all LEDs to current rainbow position
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.wheel((i + self.position) & 255))
            
        self.strip.show()
        
        # Advance position for next frame
        self.position = (self.position + 1) % 256
        
        time.sleep(self.frame_delay)

class ChaseAnimation(Animation):
    """Running light animation"""
    def __init__(self, strip, color, alt_color=None, speed=5):
        super().__init__(strip, color, alt_color, speed)
        self.position = 0
        
    def update(self):
        # Clear all and then set just the current position
        self.clear()
        self.strip.setPixelColor(self.position, self.color)
        self.strip.show()
        
        # Advance position for next frame
        self.position = (self.position + 1) % self.strip.numPixels()
        
        time.sleep(self.frame_delay)

class AlternatingAnimation(Animation):
    """Alternating between two colors"""
    def __init__(self, strip, color, alt_color=None, speed=5):
        super().__init__(strip, color, alt_color, speed)
        if alt_color is None:
            self.alt_color = COLORS["blue"]  # Default to blue if not specified
        self.state = True
        
    def update(self):
        # Toggle state
        self.state = not self.state
        
        # Set all LEDs to current color
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.color if self.state else self.alt_color)
            
        self.strip.show()
        time.sleep(self.frame_delay * 2)  # Longer delay for alternating

class AlertAnimation(Animation):
    """Alert pattern (rapid blinks)"""
    def __init__(self, strip, color, alt_color=None, speed=5):
        super().__init__(strip, color, alt_color, speed)
        self.state = True
        self.blinks = 0
        self.max_blinks = 3  # Number of blinks per cycle
        
    def update(self):
        # Toggle state
        self.state = not self.state
        
        # Set all LEDs to color or off
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.color if self.state else COLORS["off"])
            
        self.strip.show()
        
        # Count blinks and pause between cycles
        if not self.state:
            self.blinks += 1
            if self.blinks >= self.max_blinks:
                self.blinks = 0
                time.sleep(self.frame_delay * 5)  # Longer pause between blink sequences
                self.state = not self.state  # Ensure we start the next cycle with lights on
            else:
                time.sleep(self.frame_delay * 0.5)  # Quick blink
        else:
            time.sleep(self.frame_delay * 0.5)  # Quick blink

class ScanningAnimation(Animation):
    """Scanning animation (rotating pattern)"""
    def __init__(self, strip, color, alt_color=None, speed=5):
        super().__init__(strip, color, alt_color, speed)
        self.position = 0
        
    def update(self):
        # Clear all
        self.clear()
        
        # Set primary position and fading neighboring LEDs
        num_pixels = self.strip.numPixels()
        self.strip.setPixelColor(self.position, self.color)
        
        # Set dimmer version of color for adjacent pixels
        r = (self.color >> 16) & 0xFF
        g = (self.color >> 8) & 0xFF
        b = self.color & 0xFF
        
        # Calculate positions (wrapping around)
        prev_pos = (self.position - 1) % num_pixels
        next_pos = (self.position + 1) % num_pixels
        
        # Create dimmer color for adjacent LEDs
        dim_color = Color(r // 3, g // 3, b // 3)
        super_dim_color = Color(r // 10, g // 10, b // 10)
        
        # Set adjacent LEDs
        self.strip.setPixelColor(prev_pos, dim_color)
        self.strip.setPixelColor(next_pos, dim_color)
        
        # Set even dimmer color for LEDs 2 steps away
        self.strip.setPixelColor((self.position - 2) % num_pixels, super_dim_color)
        self.strip.setPixelColor((self.position + 2) % num_pixels, super_dim_color)
        
        self.strip.show()
        
        # Advance position for next frame
        self.position = (self.position + 1) % num_pixels
        
        time.sleep(self.frame_delay)

# Animation factory
def create_animation(name, strip, color, alt_color=None, speed=5):
    animations = {
        "solid": SolidAnimation,
        "pulse": PulseAnimation,
        "blink": BlinkAnimation,
        "rainbow": RainbowAnimation,
        "chase": ChaseAnimation,
        "alternate": AlternatingAnimation,
        "alert": AlertAnimation,
        "scanning": ScanningAnimation
    }
    
    animation_class = animations.get(name, SolidAnimation)
    return animation_class(strip, color, alt_color, speed)

def init_strip():
    """Initialize the LED strip or a simulation"""
    global LED_AVAILABLE
    
    if LED_AVAILABLE:
        try:
            # Create and initialize NeoPixel object
            strip = PixelStrip(
                LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
            )
            strip.begin()
            return strip
        except Exception as e:
            print(f"Error initializing LED strip: {e}")
            LED_AVAILABLE = False
    
    # If not available, create a strip simulation
    class StripSimulation:
        def __init__(self, num_pixels):
            self.num_pixels = num_pixels
            self.pixels = [0] * num_pixels
        
        def numPixels(self):
            return self.num_pixels
        
        def setPixelColor(self, pos, color):
            if 0 <= pos < self.num_pixels:
                self.pixels[pos] = color
        
        def show(self):
            # Print simple ASCII representation
            display = []
            for pixel in self.pixels:
                if pixel == 0:
                    display.append("◯")  # Empty circle for off
                else:
                    r = (pixel >> 16) & 0xFF
                    g = (pixel >> 8) & 0xFF
                    b = pixel & 0xFF
                    
                    if r > g and r > b:
                        display.append("🔴")  # Red
                    elif g > r and g > b:
                        display.append("🟢")  # Green
                    elif b > r and b > g:
                        display.append("🔵")  # Blue
                    elif r > 0 and g > 0 and b == 0:
                        display.append("🟡")  # Yellow
                    elif r > 0 and b > 0 and g == 0:
                        display.append("🟣")  # Purple/Magenta
                    elif g > 0 and b > 0 and r == 0:
                        display.append("🔷")  # Cyan
                    elif r > 0 and g > 0 and b > 0:
                        display.append("⚪")  # White
                    else:
                        display.append("◯")  # Off
            
            print(f"\r{''.join(display)}", end="", flush=True)
        
        def begin(self):
            print("LED Simulation mode active - LEDs will be printed as text")
    
    return StripSimulation(LED_COUNT)

def run_animation(strip, color, timeout, brightness, animation="solid", alt_color=None, speed=5):
    """Run the specified animation for the given timeout"""
    # Set brightness
    orig_brightness = strip.brightness
    new_brightness = int((brightness / 10.0) * 255)
    
    if hasattr(strip, 'setBrightness'):
        strip.setBrightness(new_brightness)
    
    # Create the animation
    anim = create_animation(animation, strip, color, alt_color, speed)
    
    # Run the animation loop
    start_time = time.time()
    anim.setup()
    
    try:
        while True:
            anim.update()
            
            # Check if timeout has been reached
            if timeout > 0 and time.time() - start_time >= timeout:
                break
    
    except KeyboardInterrupt:
        print("Animation interrupted")
    finally:
        # Clean up
        anim.cleanup()
        if hasattr(strip, 'setBrightness'):
            strip.setBrightness(orig_brightness)
        clear_strip(strip)

def clear_strip(strip):
    """Clear all LEDs"""
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()

def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    print("\nExiting gracefully")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='Control Waveshare RGB LED HAT')
    parser.add_argument('--color', default='green', 
                        choices=list(COLORS.keys()),
                        help='Color to display (default: green)')
    parser.add_argument('--timeout', type=int, default=5,
                        help='Time in seconds to display the color (default: 5, 0 for indefinite)')
    parser.add_argument('--brightness', type=int, default=5,
                        help='Brightness level 1-10 (default: 5)')
    parser.add_argument('--animation', default='solid',
                        choices=['solid', 'pulse', 'blink', 'rainbow', 'chase', 'alternate', 'alert', 'scanning'],
                        help='Animation pattern (default: solid)')
    parser.add_argument('--alt-color', default=None,
                        choices=list(COLORS.keys()),
                        help='Secondary color for animations that use two colors')
    parser.add_argument('--speed', type=int, default=5,
                        help='Animation speed 1-10 (default: 5)')
    
    args = parser.parse_args()
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize the LED strip
    strip = init_strip()
    
    # Validate brightness
    brightness = max(1, min(10, args.brightness))
    
    # Validate speed
    speed = max(1, min(10, args.speed))
    
    try:
        # Run the animation
        run_animation(
            strip, 
            args.color, 
            args.timeout, 
            brightness, 
            args.animation,
            args.alt_color,
            speed
        )
    finally:
        # Always make sure LEDs are off when script exits
        clear_strip(strip)
        print("\nLEDs turned off")

if __name__ == "__main__":
    main()
