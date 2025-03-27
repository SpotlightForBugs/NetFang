#!/usr/bin/env python3
import argparse
import time
import random
import sys
import signal
import math
from typing import Optional, List, Tuple, Dict, Type, Union, Any, cast

try:
    # Use Adafruit_NeoPixel as it works for the target HAT
    from rpi_ws281x import Adafruit_NeoPixel, Color

    LED_AVAILABLE = True
except ImportError:
    print(
        "Warning: rpi_ws281x library not available - running in simulation mode"
    )
    LED_AVAILABLE = False
except RuntimeError as e:
    # Catch RuntimeError during import, often related to GPIO permissions
    print(f"Error importing rpi_ws281x: {e}", file=sys.stderr)
    print("This might be a permissions issue. Try running with 'sudo'.", file=sys.stderr)
    LED_AVAILABLE = False


# --- Configuration ---
LED_ROWS: int = 4
LED_COLS: int = 8
LED_COUNT: int = LED_ROWS * LED_COLS
LED_PIN: int = 18
LED_FREQ_HZ: int = 800000
LED_DMA: int = 10
LED_BRIGHTNESS: int = 50 # Default initial brightness (0-255)
LED_INVERT: bool = False
LED_CHANNEL: int = 0
MAX_BRIGHTNESS_VALUE: int = 20 # Cap the final brightness value (0-255)





# Color definitions
if LED_AVAILABLE:
    # Use the actual Color object from the library
    COLORS: Dict[str, Union[Color,int]] = {
        "red": Color(255, 0, 0),
        "green": Color(0, 255, 0),
        "blue": Color(0, 0, 255),
        "white": Color(255, 255, 255),
        "yellow": Color(255, 255, 0),
        "purple": Color(128, 0, 128),
        "magenta": Color(255, 0, 255),
        "cyan": Color(0, 255, 255),
        "orange": Color(255, 165, 0),
        "off": Color(0, 0, 0),
    }
else:
    # Simulation mode: Use integers
    Union[Color,int] = int
    COLORS: Dict[str, Union[Color,int]] = {
        "red": 0xFF0000,
        "green": 0x00FF00,
        "blue": 0x0000FF,
        "white": 0xFFFFFF,
        "yellow": 0xFFFF00,
        "purple": 0x800080,
        "magenta": 0xFF00FF,
        "cyan": 0x00FFFF,
        "orange": 0xFFA500,
        "off": 0x000000,
    }

    # Dummy Color function for simulation
    def Color(r, g, b):
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return (r << 16) | (g << 8) | b


# --- Matrix Interface and Implementations ---
class MatrixInterface:
    """Interface for LED matrix operations"""

    def numPixels(self) -> int:
        raise NotImplementedError("numPixels must be implemented")

    def numRows(self) -> int:
        raise NotImplementedError("numRows must be implemented")

    def numCols(self) -> int:
        raise NotImplementedError("numCols must be implemented")

    def setPixelColor(self, pos: int, color: Union[Color,int]) -> None:
        raise NotImplementedError("setPixelColor must be implemented")

    def setPixelColorRC(self, row: int, col: int, color: Union[Color,int]) -> None:
        # Default implementation using xy_to_index, relies on subclass setPixelColor
        idx = self.xy_to_index(row, col)
        self.setPixelColor(idx, color)

    def show(self) -> None:
        raise NotImplementedError("show must be implemented")

    def begin(self) -> None:
        # Optional initialization step
        pass

    def setBrightness(self, brightness: int) -> None:
        raise NotImplementedError("setBrightness must be implemented")

    def getBrightness(self) -> int:
        raise NotImplementedError("getBrightness must be implemented")

    def xy_to_index(self, row: int, col: int) -> int:
        """Convert row/column coordinates to linear index (serpentine layout)"""
        rows = self.numRows()
        cols = self.numCols()
        row = max(0, min(row, rows - 1))
        col = max(0, min(col, cols - 1))
        if row % 2 == 0: # Even rows (0, 2, ...) go left to right
            return (row * cols) + col
        else: # Odd rows (1, 3, ...) go right to left
            return (row * cols) + (cols - 1 - col)


class MatrixAdapter(MatrixInterface):
    """Adapter class using Adafruit_NeoPixel"""

    def __init__(
        self, strip: Union[Adafruit_NeoPixel, Any], rows: int, cols: int
    ) -> None:
        if not LED_AVAILABLE or not isinstance(strip, Adafruit_NeoPixel):
             raise TypeError("MatrixAdapter requires a valid Adafruit_NeoPixel strip instance.")
        self.strip = strip
        self._rows = rows
        self._cols = cols
        self._brightness = self.strip.getBrightness() # Get initial value

    def numPixels(self) -> int:
        return self.strip.numPixels()

    def numRows(self) -> int:
        return self._rows

    def numCols(self) -> int:
        return self._cols

    def setPixelColor(self, pos: int, color: Union[Color,int]) -> None:
        if 0 <= pos < self.numPixels():
            # Adafruit_NeoPixel.setPixelColor expects an integer color value
            self.strip.setPixelColor(pos, cast(int, color))

    def setPixelColorRC(self, row: int, col: int, color: Union[Color,int]) -> None:
        # Explicitly override to use the base class logic
        super().setPixelColorRC(row, col, color)

    def show(self) -> None:
        self.strip.show()

    def begin(self) -> None:
        # Adafruit_NeoPixel is begun during init_matrix, so nothing needed here
        pass

    def setBrightness(self, brightness: int) -> None:
        # Clamp brightness to the allowed range (0-255 for the library)
        brightness = max(0, min(255, brightness))
        self.strip.setBrightness(brightness)
        self._brightness = brightness # Update local store

    def getBrightness(self) -> int:
        # Return locally stored brightness (more reliable than querying strip again)
        return self._brightness


class MatrixSimulation(MatrixInterface):
    """Simulation of an LED matrix for development without hardware"""

    def __init__(self, rows: int, cols: int) -> None:
        self._rows = rows
        self._cols = cols
        self._pixels: List[Union[Color,int]] = [COLORS["off"]] * (rows * cols)
        self._brightness = LED_BRIGHTNESS # Use the default initial

    def numPixels(self) -> int:
        return len(self._pixels)

    def numRows(self) -> int:
        return self._rows

    def numCols(self) -> int:
        return self._cols

    def setPixelColor(self, pos: int, color: Union[Color,int]) -> None:
        if 0 <= pos < len(self._pixels):
            self._pixels[pos] = color

    def setPixelColorRC(self, row: int, col: int, color: Union[Color,int]) -> None:
        # Explicitly override to use the base class logic
        super().setPixelColorRC(row, col, color)

    def show(self) -> None:
        """Display the matrix in a text-based grid layout"""
        display = [["⚫" for _ in range(self._cols)] for _ in range(self._rows)]
        # Apply brightness factor for simulation display
        # Use the capped max brightness for scaling the display effect
        brightness_factor = self._brightness / 255.0

        for i, pixel_color in enumerate(self._pixels):
            row = i // self._cols
            if row % 2 == 0: # Even rows
                col = i % self._cols
            else: # Odd rows
                col = self._cols - 1 - (i % self._cols)

            pixel_int = cast(int, pixel_color)
            r = int(((pixel_int >> 16) & 0xFF) * brightness_factor)
            g = int(((pixel_int >> 8) & 0xFF) * brightness_factor)
            b = int((pixel_int & 0xFF) * brightness_factor)

            threshold = 30 * brightness_factor # Threshold for visibility
            if r < threshold and g < threshold and b < threshold:
                 display[row][col] = "⚫"
            elif r > g and r > b: display[row][col] = "🔴"
            elif g > r and g > b: display[row][col] = "🟢"
            elif b > r and b > g: display[row][col] = "🔵"
            elif r > threshold and g > threshold and b < threshold: display[row][col] = "🟡"
            elif r > threshold and b > threshold and g < threshold: display[row][col] = "🟣"
            elif g > threshold and b > threshold and r < threshold: display[row][col] = "🔷"
            elif r > threshold and g > threshold and b > threshold: display[row][col] = "⚪"
            else: display[row][col] = "⚫"

        print("\033[H\033[J", end="") # Clear screen
        print(f"LED Matrix Simulation ({self._rows}x{self._cols}): Brightness {self._brightness}/{MAX_BRIGHTNESS_VALUE}")
        print("┌" + "──" * self._cols + "┐")
        for row_display in display:
            print("│" + "".join(row_display) + "│")
        print("└" + "──" * self._cols + "┘")

    def begin(self) -> None:
        # Simulation specific initialization message
        print("LED Matrix Simulation mode active.")

    def setBrightness(self, brightness: int) -> None:
        # Clamp brightness to the allowed range (0-255 internally)
        self._brightness = max(0, min(255, brightness))

    def getBrightness(self) -> int:
        return self._brightness


# --- Animation Definitions (Unchanged from previous version) ---
# Base Animation class and all specific animation classes (Solid, Pulse, etc.)
# remain the same as in the previous corrected version.
# Ensure all specific animation classes correctly override update().
class Animation:
    """Base class for all animations"""
    def __init__(
        self, matrix: MatrixInterface, color: str,
        alt_color: Optional[str] = None, speed: int = 5
    ) -> None:
        self.matrix = matrix
        self.color: Union[Color,int] = COLORS.get(color, COLORS["white"])
        self.alt_color: Union[Color,int] = (
            COLORS.get(alt_color, COLORS["blue"])
            if alt_color else COLORS["off"]
        )
        self.speed: int = min(max(speed, 1), 10)
        self.frame_delay: float = 0.1 * (11 - self.speed)
    def setup(self) -> None: pass
    def update(self) -> None: raise NotImplementedError("Animation subclass must implement update()")
    def cleanup(self) -> None: pass
    def clear(self) -> None:
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColor(i, COLORS["off"])
    def _get_rgb(self, color: Union[Color,int]) -> Tuple[int, int, int]:
        color_int = cast(int, color)
        return ((color_int >> 16) & 0xFF, (color_int >> 8) & 0xFF, color_int & 0xFF)
    def _make_color(self, r: int, g: int, b: int) -> Union[Color,int]:
         r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
         return Color(r, g, b)

class SolidAnimation(Animation):
    def update(self) -> None:
        for i in range(self.matrix.numPixels()): self.matrix.setPixelColor(i, self.color)
        self.matrix.show(); time.sleep(0.1)
class PulseAnimation(Animation):
    def __init__(self, matrix: MatrixInterface, color: str, alt_color: Optional[str] = None, speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed); self.brightness_multiplier, self.increasing, self.step = 0.0, True, 0.02 * self.speed
    def update(self) -> None:
        if self.increasing: self.brightness_multiplier += self.step; self.increasing = self.brightness_multiplier < 1.0
        else: self.brightness_multiplier -= self.step; self.increasing = self.brightness_multiplier <= 0.05
        if self.brightness_multiplier > 1.0: self.brightness_multiplier = 1.0
        if self.brightness_multiplier < 0.05: self.brightness_multiplier = 0.05
        r, g, b = self._get_rgb(self.color); dimmed_color = self._make_color(int(r * self.brightness_multiplier), int(g * self.brightness_multiplier), int(b * self.brightness_multiplier))
        for i in range(self.matrix.numPixels()): self.matrix.setPixelColor(i, dimmed_color)
        self.matrix.show(); time.sleep(self.frame_delay * 0.5)
class BlinkAnimation(Animation):
    def __init__(self, matrix: MatrixInterface, color: str, alt_color: Optional[str] = None, speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed); self.state = True
    def update(self) -> None:
        self.state = not self.state; current_color = self.color if self.state else COLORS["off"]
        for i in range(self.matrix.numPixels()): self.matrix.setPixelColor(i, current_color)
        self.matrix.show(); time.sleep(self.frame_delay * 1.5)
class RainbowAnimation(Animation):
    def __init__(self, matrix: MatrixInterface, color: str, alt_color: Optional[str] = None, speed: int = 5) -> None:
        super().__init__(matrix, "white", alt_color, speed); self.position = 0
    def wheel(self, pos: int) -> Union[Color,int]:
        pos %= 256; r, g, b = (0,0,0)
        if pos < 85: r, g, b = pos * 3, 255 - pos * 3, 0
        elif pos < 170: pos -= 85; r, g, b = 255 - pos * 3, 0, pos * 3
        else: pos -= 170; r, g, b = 0, pos * 3, 255 - pos * 3
        return self._make_color(r, g, b)
    def update(self) -> None:
        num_pixels = self.matrix.numPixels()
        for i in range(num_pixels): self.matrix.setPixelColor(i, self.wheel((i * (256 // num_pixels) + self.position) & 255))
        self.matrix.show(); self.position = (self.position + self.speed // 2 + 1) % 256; time.sleep(self.frame_delay * 0.2)
class ChaseAnimation(Animation):
    def __init__(self, matrix: MatrixInterface, color: str, alt_color: Optional[str] = None, speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed); self.current_pixel, self.pixel_count = 0, matrix.numPixels()
    def update(self) -> None:
        self.clear(); pixel_index = self.current_pixel % self.pixel_count
        self.matrix.setPixelColor(pixel_index, self.color); self.matrix.show()
        self.current_pixel += 1; time.sleep(self.frame_delay)
class AlternatingAnimation(Animation):
    def __init__(self, matrix: MatrixInterface, color: str, alt_color: Optional[str] = None, speed: int = 5) -> None:
        alt_color = alt_color or "blue"; super().__init__(matrix, color, alt_color, speed)
        if isinstance(self.alt_color, str): self.alt_color = COLORS.get(self.alt_color, COLORS["blue"])
        self.state = True
    def update(self) -> None:
        self.state = not self.state; current_color = self.color if self.state else self.alt_color
        for i in range(self.matrix.numPixels()): self.matrix.setPixelColor(i, current_color)
        self.matrix.show(); time.sleep(self.frame_delay * 2)
class AlertAnimation(Animation):
    def __init__(self, matrix: MatrixInterface, color: str, alt_color: Optional[str] = None, speed: int = 5) -> None:
        base_speed = max(7, speed); super().__init__(matrix, color, alt_color, base_speed)
        self.state, self.blinks, self.max_blinks, self.pause_state = True, 0, 3, False
        self.blink_delay, self.pause_delay = self.frame_delay * 0.5, self.frame_delay * 4
    def update(self) -> None:
        current_color = COLORS["off"] # Default
        if self.pause_state:
            if self.state: self.clear(); self.matrix.show(); self.state = False
            time.sleep(self.pause_delay); self.pause_state, self.blinks, self.state = False, 0, True
            current_color = self.color # Set color for next frame after pause
        else:
            self.state = not self.state; current_color = self.color if self.state else COLORS["off"]
            if not self.state: self.blinks += 1
            if self.blinks >= self.max_blinks and not self.state: self.pause_state = True
        if not (self.pause_state and not self.state): # Don't show if pausing and already off
            for i in range(self.matrix.numPixels()): self.matrix.setPixelColor(i, current_color)
            self.matrix.show()
        time.sleep(self.blink_delay if not self.pause_state else 0) # Only sleep during blinking
class ScanningAnimation(Animation):
    def __init__(self, matrix: MatrixInterface, color: str, alt_color: Optional[str] = None, speed: int = 5) -> None:
        super().__init__(matrix, color, alt_color, speed); self.position, self.horizontal, self.direction, self.scan_count = 0, True, 1, 0
    def update(self) -> None:
        self.clear(); r, g, b = self._get_rgb(self.color)
        dim_color, super_dim_color = self._make_color(r // 4, g // 4, b // 4), self._make_color(r // 10, g // 10, b // 10)
        rows, cols = self.matrix.numRows(), self.matrix.numCols()
        limit = rows if self.horizontal else cols
        if self.horizontal:
            for c in range(cols):
                idx = self.matrix.xy_to_index(self.position, c); self.matrix.setPixelColor(idx, self.color)
                if 0 <= self.position - self.direction < limit: self.matrix.setPixelColor(self.matrix.xy_to_index(self.position - self.direction, c), dim_color)
                if 0 <= self.position - 2 * self.direction < limit: self.matrix.setPixelColor(self.matrix.xy_to_index(self.position - 2 * self.direction, c), super_dim_color)
        else:
            for r in range(rows):
                idx = self.matrix.xy_to_index(r, self.position); self.matrix.setPixelColor(idx, self.color)
                if 0 <= self.position - self.direction < limit: self.matrix.setPixelColor(self.matrix.xy_to_index(r, self.position - self.direction), dim_color)
                if 0 <= self.position - 2 * self.direction < limit: self.matrix.setPixelColor(self.matrix.xy_to_index(r, self.position - 2 * self.direction), super_dim_color)
        self.matrix.show(); self.position += self.direction
        if self.position >= limit: self.position, self.direction, self.scan_count = limit - 1, -1, self.scan_count + 1
        elif self.position < 0: self.position, self.direction, self.scan_count = 0, 1, self.scan_count + 1
        if self.scan_count >= 2: self.horizontal, self.scan_count, self.position, self.direction = not self.horizontal, 0, 0, 1
        time.sleep(self.frame_delay)
# --- End of Animation Definitions ---


# --- Animation Factory ---
def create_animation(
    name: str, matrix: MatrixInterface, color: str,
    alt_color: Optional[str] = None, speed: int = 5
) -> Animation:
    """Create an animation instance by name"""
    animations: Dict[str, Type[Animation]] = {
        "solid": SolidAnimation, "pulse": PulseAnimation, "blink": BlinkAnimation,
        "rainbow": RainbowAnimation, "chase": ChaseAnimation, "alternate": AlternatingAnimation,
        "alert": AlertAnimation, "scanning": ScanningAnimation,
    }
    animation_class = animations.get(name.lower(), SolidAnimation)
    # print(f"Creating animation: {animation_class.__name__} for '{name}'") # Debug
    try:
        instance = animation_class(matrix, color, alt_color, speed)
        # Verify the instance has an update method (should always be true if class structure is correct)
        if not hasattr(instance, 'update') or not callable(instance.update):
             raise TypeError(f"Animation class {animation_class.__name__} does not have a callable update method.")
        return instance
    except Exception as e:
        print(f"Error creating animation '{name}': {e}", file=sys.stderr)
        # Fallback safely to SolidAnimation if creation fails
        return SolidAnimation(matrix, color, alt_color, speed)


# --- Initialization and Control ---
def init_matrix() -> Optional[MatrixInterface]:
    """Initialize the LED matrix or a simulation. Returns None on failure."""
    global LED_AVAILABLE
    if LED_AVAILABLE:
        try:
            strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
            strip.begin()
            # print(f"Real LED Matrix ({LED_ROWS}x{LED_COLS}) Initialized.")
            return MatrixAdapter(strip, LED_ROWS, LED_COLS)
        except RuntimeError as e:
            print(f"Error initializing LED matrix: {e}", file=sys.stderr)
            print("Try running with 'sudo'. Falling back to simulation.", file=sys.stderr)
            LED_AVAILABLE = False
        except Exception as e:
            print(f"Unexpected error initializing LED matrix: {e}", file=sys.stderr)
            LED_AVAILABLE = False
    # Fallback to simulation
    if not LED_AVAILABLE:
        # print("Initializing LED Matrix Simulation.")
        return MatrixSimulation(LED_ROWS, LED_COLS)
    return None # Should not be reached


def run_animation_loop(
    matrix: MatrixInterface, color: str, timeout: int,
    brightness_level: int, animation_name: str = "solid",
    alt_color: Optional[str] = None, speed: int = 5
) -> None:
    """Run the specified animation, respecting timeout and brightness cap."""

    # --- Brightness Setup ---
    # Convert 1-10 level from plugin to 0-MAX_BRIGHTNESS_VALUE scale
    brightness_val = int((brightness_level / 10.0) * MAX_BRIGHTNESS_VALUE)
    # Clamp to 0-MAX_BRIGHTNESS_VALUE and ensure it's an int
    brightness_val = max(0, min(MAX_BRIGHTNESS_VALUE, brightness_val))

    matrix.setBrightness(brightness_val)
    # print(f"Setting brightness to {brightness_val}/{MAX_BRIGHTNESS_VALUE} (Level {brightness_level})")

    # --- Animation Setup ---
    anim = create_animation(animation_name, matrix, color, alt_color, speed)
    anim.setup()

    # --- Main Loop ---
    start_time = time.time()
    try:
        if timeout > 0:
            while time.time() - start_time < timeout:
                anim.update()
        else: # timeout == 0
            while True:
                anim.update()
    except KeyboardInterrupt:
        print("\nAnimation interrupted by user (Ctrl+C)")
    finally:
        # --- Cleanup ---
        anim.cleanup()
        clear_matrix(matrix) # Ensure matrix is cleared on exit


def clear_matrix(matrix: MatrixInterface) -> None:
    """Clear all LEDs in the matrix."""
    # print("Clearing matrix...")
    try:
        # Set brightness to 0 before clearing for a potentially smoother off effect
        matrix.setBrightness(0)
        for i in range(matrix.numPixels()):
            matrix.setPixelColor(i, COLORS["off"])
        matrix.show()
        time.sleep(0.05) # Allow time for show command
    except Exception as e:
        print(f"Error during matrix clear: {e}", file=sys.stderr)


# Global reference for cleanup in signal handler
_matrix_instance: Optional[MatrixInterface] = None

def signal_handler(sig, frame) -> None:
    """Handle termination signals gracefully (SIGINT, SIGTERM)."""
    print(f"\nSignal {sig} received, exiting gracefully...", file=sys.stderr)
    if _matrix_instance:
        # Attempt to clear the matrix on signal
        clear_matrix(_matrix_instance)
    sys.exit(0)


def main() -> None:
    global _matrix_instance
    parser = argparse.ArgumentParser(description="Control Waveshare RGB LED HAT (4x8) via CLI.")
    parser.add_argument("--color", default="green", choices=list(COLORS.keys()), help="Primary color (or 'off'). Default: green")
    parser.add_argument("--timeout", type=int, default=0, help="Time in seconds to run (0 for indefinite). Default: 0")
    parser.add_argument("--brightness", type=int, default=5, help="Brightness level 1-10. Default: 5")
    parser.add_argument("--animation", default="solid", choices=["solid", "pulse", "blink", "rainbow", "chase", "alternate", "alert", "scanning"], help="Animation pattern. Default: solid")
    parser.add_argument("--alt-color", default=None, choices=list(COLORS.keys()), help="Secondary color for animations")
    parser.add_argument("--speed", type=int, default=5, help="Animation speed 1-10 (1=slowest, 10=fastest). Default: 5")
    args = parser.parse_args()

    _matrix_instance = init_matrix()
    if _matrix_instance is None:
        print("Failed to initialize LED matrix or simulation. Exiting.", file=sys.stderr)
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.color.lower() == "off":
        clear_matrix(_matrix_instance)
        sys.exit(0)

    brightness = max(1, min(10, args.brightness))
    speed = max(1, min(10, args.speed))

    try:
        run_animation_loop(
            _matrix_instance, args.color, args.timeout, brightness,
            args.animation, args.alt_color, speed
        )
    except Exception as e:
         print(f"An error occurred during animation loop: {e}", file=sys.stderr)
         if _matrix_instance: clear_matrix(_matrix_instance) # Attempt cleanup
         sys.exit(1)

    # Normal exit (likely after timeout)
    sys.exit(0)


if __name__ == "__main__":
    main()
