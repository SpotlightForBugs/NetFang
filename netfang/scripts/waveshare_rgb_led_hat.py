#!/usr/bin/env python3
import argparse
import time
import random
import sys
import signal
import math
from typing import Optional, List, Tuple, Dict, Type, Union, Any, cast

try:
    from rpi_ws281x import PixelStrip, Color
    LED_AVAILABLE = True
except ImportError:
    print("Warning: rpi_ws281x library not available - running in simulation mode")
    LED_AVAILABLE = False

# LED matrix configuration:
LED_ROWS: int = 4           # Number of rows in the LED matrix
LED_COLS: int = 8           # Number of columns in the LED matrix
LED_COUNT: int = LED_ROWS * LED_COLS  # Total number of LEDs
LED_PIN: int = 18           # GPIO pin connected to the pixels (18 uses PWM!)
LED_FREQ_HZ: int = 800000   # LED signal frequency in hertz (usually 800khz)
LED_DMA: int = 10           # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS: int = 255   # Set to 0 for darkest and 255 for brightest
LED_INVERT: bool = False    # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL: int = 0        # set to '1' for GPIOs 13, 19, 41, 45 or 53

# Type alias for Color
ColorType = int

# Color values
COLORS: Dict[str, ColorType] = {
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

class MatrixInterface:
    """Interface for LED matrix operations to standardize between real and simulated matrix"""
    def numPixels(self) -> int:
        """Return the number of pixels in the matrix"""
        raise NotImplementedError
    
    def numRows(self) -> int:
        """Return the number of rows in the matrix"""
        raise NotImplementedError
    
    def numCols(self) -> int:
        """Return the number of columns in the matrix"""
        raise NotImplementedError
        
    def setPixelColor(self, pos: int, color: ColorType) -> None:
        """Set the color of a pixel at a linear position"""
        raise NotImplementedError
        
    def setPixelColorRC(self, row: int, col: int, color: ColorType) -> None:
        """Set the color of a pixel at a specific row and column"""
        raise NotImplementedError
        
    def show(self) -> None:
        """Update the display with all pixel changes"""
        raise NotImplementedError
        
    def begin(self) -> None:
        """Initialize the matrix"""
        raise NotImplementedError
        
    def setBrightness(self, brightness: int) -> None:
        """Set the brightness of the matrix"""
        raise NotImplementedError
        
    @property
    def brightness(self) -> int:
        """Get the current brightness level"""
        raise NotImplementedError

# Animation definitions
class Animation:
    """Base class for all animations"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        """
        Base animation class
        
        Args:
            matrix: The LED matrix instance
            color: Primary color for the animation
            alt_color: Secondary color for animations that use two colors
            speed: Animation speed (1-10, where 10 is fastest)
        """
        self.matrix = matrix
        self.color: ColorType = COLORS.get(color, COLORS["white"])
        self.alt_color: ColorType = COLORS.get(alt_color or "", COLORS["blue"]) if alt_color else COLORS["off"]
        self.speed: int = min(max(speed, 1), 10)  # Constrain between 1-10
        self.frame_delay: float = 0.1 * (11 - self.speed)  # Convert speed to delay (faster = lower delay)
        
    def setup(self) -> None:
        """Initialize the animation (called once before running)"""
        pass
        
    def update(self) -> None:
        """Update animation frame (called repeatedly while running)"""
        pass
        
    def cleanup(self) -> None:
        """Clean up after animation (called once when animation is done)"""
        pass
        
    def clear(self) -> None:
        """Clear all LEDs"""
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColor(i, COLORS["off"])
        self.matrix.show()
        
    def xy_to_index(self, row: int, col: int) -> int:
        """Convert row/column coordinates to linear index"""
        rows = self.matrix.numRows()
        cols = self.matrix.numCols()
        
        # Ensure coordinates are in bounds
        row = max(0, min(row, rows - 1))
        col = max(0, min(col, cols - 1))
        
        # Map coordinates to index based on serpentine layout
        # (each row alternates direction to match common matrix wiring)
        if row % 2 == 0:  # Even rows go left to right
            return (row * cols) + col
        else:  # Odd rows go right to left
            return (row * cols) + (cols - 1 - col)
        
class SolidAnimation(Animation):
    """Display a static solid color on all LEDs"""
    def update(self) -> None:
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColor(i, self.color)
        self.matrix.show()
        time.sleep(0.1)  # Small delay to avoid CPU hogging

class PulseAnimation(Animation):
    """Pulse the LEDs by varying the brightness"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed)
        self.brightness_multiplier: float = 0.0
        self.increasing: bool = True
        self.step: float = 0.05 * self.speed  # Speed affects step size
        
    def update(self) -> None:
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
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColor(i, dimmed_color)
        
        self.matrix.show()
        time.sleep(self.frame_delay)

class BlinkAnimation(Animation):
    """Blink between the color and off"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed)
        self.state: bool = True
        
    def update(self) -> None:
        # Toggle state
        self.state = not self.state
        
        # Set all LEDs to either the color or off
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColor(i, self.color if self.state else COLORS["off"])
            
        self.matrix.show()
        time.sleep(self.frame_delay * 2)  # Longer delay for blink

class RainbowAnimation(Animation):
    """Cycle through all colors of the rainbow"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed)
        self.position: int = 0
        
    def wheel(self, pos: int) -> ColorType:
        """Generate rainbow colors across 0-255 positions"""
        pos = pos % 256
        if pos < 85:
            return Color(pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return Color(255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return Color(0, pos * 3, 255 - pos * 3)
    
    def update(self) -> None:
        # Set all LEDs to current rainbow position
        for row in range(self.matrix.numRows()):
            for col in range(self.matrix.numCols()):
                idx = self.xy_to_index(row, col)
                self.matrix.setPixelColor(idx, self.wheel((idx + self.position) & 255))
            
        self.matrix.show()
        
        # Advance position for next frame
        self.position = (self.position + 1) % 256
        
        time.sleep(self.frame_delay)

class ChaseAnimation(Animation):
    """Running light animation across the matrix"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed)
        self.row: int = 0
        self.col: int = 0
        self.direction: int = 0  # 0:right, 1:down, 2:left, 3:up
        
    def update(self) -> None:
        # Clear all and then set just the current position
        self.clear()
        
        # Set the current pixel
        idx = self.xy_to_index(self.row, self.col)
        self.matrix.setPixelColor(idx, self.color)
        self.matrix.show()
        
        # Move to next position in spiral pattern
        if self.direction == 0:  # Moving right
            self.col += 1
            if self.col >= self.matrix.numCols() - 1 or self.matrix.setPixelColor(self.xy_to_index(self.row, self.col + 1), COLORS["off"]):
                self.direction = 1
        elif self.direction == 1:  # Moving down
            self.row += 1
            if self.row >= self.matrix.numRows() - 1 or self.matrix.setPixelColor(self.xy_to_index(self.row + 1, self.col), COLORS["off"]):
                self.direction = 2
        elif self.direction == 2:  # Moving left
            self.col -= 1
            if self.col <= 0 or self.matrix.setPixelColor(self.xy_to_index(self.row, self.col - 1), COLORS["off"]):
                self.direction = 3
        else:  # Moving up
            self.row -= 1
            if self.row <= 0 or self.matrix.setPixelColor(self.xy_to_index(self.row - 1, self.col), COLORS["off"]):
                self.direction = 0
        
        # If we've gone out of bounds, reset
        if (self.row < 0 or self.row >= self.matrix.numRows() or 
            self.col < 0 or self.col >= self.matrix.numCols()):
            self.row = 0
            self.col = 0
            self.direction = 0
        
        time.sleep(self.frame_delay)

class AlternatingAnimation(Animation):
    """Alternating between two colors"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed)
        if alt_color is None:
            self.alt_color = COLORS["blue"]  # Default to blue if not specified
        self.state: bool = True
        
    def update(self) -> None:
        # Toggle state
        self.state = not self.state
        
        # Set all LEDs to current color
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColor(i, self.color if self.state else self.alt_color)
            
        self.matrix.show()
        time.sleep(self.frame_delay * 2)  # Longer delay for alternating

class AlertAnimation(Animation):
    """Alert pattern (rapid blinks)"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed)
        self.state: bool = True
        self.blinks: int = 0
        self.max_blinks: int = 3  # Number of blinks per cycle
        
    def update(self) -> None:
        # Toggle state
        self.state = not self.state
        
        # Set all LEDs to color or off
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColor(i, self.color if self.state else COLORS["off"])
            
        self.matrix.show()
        
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
    """Scanning animation - sweeping line across the matrix"""
    def __init__(self, 
                 matrix: MatrixInterface, 
                 color: str, 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed)
        self.position: int = 0
        self.horizontal: bool = True  # True for horizontal scanning, False for vertical
        self.direction: int = 1  # 1 for forward, -1 for reverse
        self.scan_count: int = 0
        
    def update(self) -> None:
        # Clear all
        self.clear()
        
        # Calculate brightness falloff for trail effect
        r = (self.color >> 16) & 0xFF
        g = (self.color >> 8) & 0xFF
        b = self.color & 0xFF
        
        # Create dimmer colors for trail effect
        dim_color = Color(r // 3, g // 3, b // 3)
        super_dim_color = Color(r // 8, g // 8, b // 8)
        
        if self.horizontal:
            # Horizontal scanning (a line moving up and down)
            for col in range(self.matrix.numCols()):
                # Main scanning line
                idx = self.xy_to_index(self.position, col)
                self.matrix.setPixelColor(idx, self.color)
                
                # Add trail effect (dimmer pixels)
                if 0 <= (self.position - self.direction) < self.matrix.numRows():
                    trail_idx = self.xy_to_index(self.position - self.direction, col)
                    self.matrix.setPixelColor(trail_idx, dim_color)
                
                if 0 <= (self.position - (2 * self.direction)) < self.matrix.numRows():
                    far_trail_idx = self.xy_to_index(self.position - (2 * self.direction), col)
                    self.matrix.setPixelColor(far_trail_idx, super_dim_color)
        else:
            # Vertical scanning (a line moving left and right)
            for row in range(self.matrix.numRows()):
                # Main scanning line
                idx = self.xy_to_index(row, self.position)
                self.matrix.setPixelColor(idx, self.color)
                
                # Add trail effect (dimmer pixels)
                if 0 <= (self.position - self.direction) < self.matrix.numCols():
                    trail_idx = self.xy_to_index(row, self.position - self.direction)
                    self.matrix.setPixelColor(trail_idx, dim_color)
                
                if 0 <= (self.position - (2 * self.direction)) < self.matrix.numCols():
                    far_trail_idx = self.xy_to_index(row, self.position - (2 * self.direction))
                    self.matrix.setPixelColor(far_trail_idx, super_dim_color)
        
        self.matrix.show()
        
        # Update position
        self.position += self.direction
        
        # Change direction when reaching edge
        if self.horizontal:
            if self.position >= self.matrix.numRows():
                self.position = self.matrix.numRows() - 1
                self.direction = -1
                self.scan_count += 1
            elif self.position < 0:
                self.position = 0
                self.direction = 1
                self.scan_count += 1
                # After completing a full scan cycle, switch to vertical
                if self.scan_count >= 2:
                    self.horizontal = False
                    self.scan_count = 0
        else:
            if self.position >= self.matrix.numCols():
                self.position = self.matrix.numCols() - 1
                self.direction = -1
                self.scan_count += 1
            elif self.position < 0:
                self.position = 0
                self.direction = 1
                self.scan_count += 1
                # After completing a full scan cycle, switch to horizontal
                if self.scan_count >= 2:
                    self.horizontal = True
                    self.scan_count = 0
        
        time.sleep(self.frame_delay)

# Animation factory
def create_animation(name: str, 
                    matrix: MatrixInterface, 
                    color: str, 
                    alt_color: Optional[str] = None, 
                    speed: int = 5) -> Animation:
    """Create an animation instance by name"""
    animations: Dict[str, Type[Animation]] = {
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
    return animation_class(matrix, color, alt_color, speed)

class MatrixAdapter(MatrixInterface):
    """Adapter class to provide matrix functionality using PixelStrip"""
    def __init__(self, strip: Union[PixelStrip, Any], rows: int, cols: int) -> None:
        self.strip = strip
        self._rows = rows
        self._cols = cols
        self._brightness = LED_BRIGHTNESS
        
    def numPixels(self) -> int:
        return self.strip.numPixels()
    
    def numRows(self) -> int:
        return self._rows
    
    def numCols(self) -> int:
        return self._cols
        
    def setPixelColor(self, pos: int, color: ColorType) -> None:
        if 0 <= pos < self.numPixels():
            self.strip.setPixelColor(pos, color)
    
    def setPixelColorRC(self, row: int, col: int, color: ColorType) -> None:
        """Set pixel color by row and column coordinates"""
        if 0 <= row < self._rows and 0 <= col < self._cols:
            # Determine the pixel's position in the serpentine layout
            if row % 2 == 0:  # Even rows go left to right
                pos = (row * self._cols) + col
            else:  # Odd rows go right to left
                pos = (row * self._cols) + (self._cols - 1 - col)
            
            self.strip.setPixelColor(pos, color)
    
    def show(self) -> None:
        self.strip.show()
        
    def begin(self) -> None:
        self.strip.begin()
        
    def setBrightness(self, brightness: int) -> None:
        if hasattr(self.strip, 'setBrightness'):
            self.strip.setBrightness(brightness)
        self._brightness = brightness
            
    @property
    def brightness(self) -> int:
        return self._brightness

class MatrixSimulation(MatrixInterface):
    """Simulation of an LED matrix for development without hardware"""
    def __init__(self, rows: int, cols: int) -> None:
        self._rows = rows
        self._cols = cols
        self._pixels = [0] * (rows * cols)
        self._brightness = LED_BRIGHTNESS
        
    def numPixels(self) -> int:
        return len(self._pixels)
    
    def numRows(self) -> int:
        return self._rows
    
    def numCols(self) -> int:
        return self._cols
        
    def setPixelColor(self, pos: int, color: ColorType) -> None:
        if 0 <= pos < len(self._pixels):
            self._pixels[pos] = color
    
    def setPixelColorRC(self, row: int, col: int, color: ColorType) -> None:
        """Set pixel color by row and column coordinates"""
        if 0 <= row < self._rows and 0 <= col < self._cols:
            # Determine the pixel's position in the serpentine layout
            if row % 2 == 0:  # Even rows go left to right
                pos = (row * self._cols) + col
            else:  # Odd rows go right to left
                pos = (row * self._cols) + (self._cols - 1 - col)
            
            self._pixels[pos] = color
    
    def show(self) -> None:
        """Display the matrix in a text-based grid layout"""
        display = [['◯' for _ in range(self._cols)] for _ in range(self._rows)]
        
        # Convert linear array to 2D grid for display
        for i, pixel in enumerate(self._pixels):
            # Determine row and column from linear index
            row = i // self._cols
            if row % 2 == 0:  # Even rows go left to right
                col = i % self._cols
            else:  # Odd rows go right to left
                col = self._cols - 1 - (i % self._cols)
                
            if pixel == 0:
                display[row][col] = '◯'  # Empty circle for off
            else:
                r = (pixel >> 16) & 0xFF
                g = (pixel >> 8) & 0xFF
                b = pixel & 0xFF
                
                if r > g and r > b:
                    display[row][col] = '🔴'  # Red
                elif g > r and g > b:
                    display[row][col] = '🟢'  # Green
                elif b > r and b > g:
                    display[row][col] = '🔵'  # Blue
                elif r > 0 and g > 0 and b == 0:
                    display[row][col] = '🟡'  # Yellow
                elif r > 0 and b > 0 and g == 0:
                    display[row][col] = '🟣'  # Purple/Magenta
                elif g > 0 and b > 0 and r == 0:
                    display[row][col] = '🔷'  # Cyan
                elif r > 0 and g > 0 and b > 0:
                    display[row][col] = '⚪'  # White
                else:
                    display[row][col] = '◯'  # Off
        
        # Print the matrix
        print("\033[H\033[J", end="")  # Clear screen
        print("LED Matrix Simulation (4x8):")
        print("┌" + "─" * (self._cols * 2) + "┐")
        for row in display:
            print("│" + "".join(row) + "│")
        print("└" + "─" * (self._cols * 2) + "┘")
        
    def begin(self) -> None:
        print("LED Matrix Simulation mode active - LEDs will be printed as a grid")
        
    def setBrightness(self, brightness: int) -> None:
        self._brightness = brightness
            
    @property
    def brightness(self) -> int:
        return self._brightness

def init_matrix() -> MatrixInterface:
    """Initialize the LED matrix or a simulation"""
    global LED_AVAILABLE
    
    if LED_AVAILABLE:
        try:
            # Create and initialize NeoPixel object
            strip = PixelStrip(
                LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
            )
            strip.begin()
            return MatrixAdapter(strip, LED_ROWS, LED_COLS)
        except Exception as e:
            print(f"Error initializing LED matrix: {e}")
            LED_AVAILABLE = False
    
    # If not available, create a matrix simulation
    return MatrixSimulation(LED_ROWS, LED_COLS)

def run_animation(matrix: MatrixInterface, 
                 color: str, 
                 timeout: int, 
                 brightness: int, 
                 animation: str = "solid", 
                 alt_color: Optional[str] = None, 
                 speed: int = 5) -> None:
    """Run the specified animation for the given timeout"""
    # Set brightness
    # Store current brightness safely - use getBrightness method if available
    if hasattr(matrix.strip, 'getBrightness'):
        orig_brightness = matrix.strip.getBrightness()
    else:
        orig_brightness = matrix.brightness
    
    new_brightness = int((brightness / 10.0) * 255)
    
    matrix.setBrightness(new_brightness)
    
    # Create the animation
    anim = create_animation(animation, matrix, color, alt_color, speed)
    
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
        matrix.setBrightness(orig_brightness)
        clear_matrix(matrix)

def clear_matrix(matrix: MatrixInterface) -> None:
    """Clear all LEDs in the matrix"""
    for i in range(matrix.numPixels()):
        matrix.setPixelColor(i, Color(0, 0, 0))
    matrix.show()

def signal_handler(sig, frame) -> None:
    """Handle Ctrl+C"""
    print("\nExiting gracefully")
    sys.exit(0)

def main() -> None:
    parser = argparse.ArgumentParser(description='Control Waveshare RGB LED HAT 4x8 Matrix')
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
    
    # Initialize the LED matrix
    matrix = init_matrix()
    
    # Validate brightness
    brightness = max(1, min(10, args.brightness))
    
    # Validate speed
    speed = max(1, min(10, args.speed))
    
    try:
        # Run the animation
        run_animation(
            matrix, 
            args.color, 
            args.timeout, 
            brightness, 
            args.animation,
            args.alt_color,
            speed
        )
    finally:
        # Always make sure LEDs are off when script exits
        clear_matrix(matrix)
        print("\nLEDs turned off")

if __name__ == "__main__":
    main()
