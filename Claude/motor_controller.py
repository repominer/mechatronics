import time
import threading
import logging

# Try to import GPIO libraries, with fallbacks for testing environments
try:
    import Jetson.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    try:
        import RPi.GPIO as GPIO
        GPIO_AVAILABLE = True
    except ImportError:
        GPIO_AVAILABLE = False
        print("WARNING: GPIO libraries not available. Running in simulation mode.")

# Try to import serial for Arduino communication
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("WARNING: PySerial not available. Arduino control disabled.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('motor_controller')

class MotorController:
    """
    Unified motor controller class that can work with either:
    1. Direct GPIO control on Jetson/Raspberry Pi
    2. Serial communication with Arduino
    """
    
    # Motor commands
    CMD_FORWARD = "F"
    CMD_BACKWARD = "B"
    CMD_LEFT = "L"
    CMD_RIGHT = "R"
    CMD_STOP = "S"
    
    def __init__(self, enable_motors=True, command_cooldown=0.2):
        """
        Initialize the motor controller.
        
        Args:
            enable_motors: Whether to enable physical motor control.
            command_cooldown: Minimum time between successive commands.
        """
        self.motors_enabled = enable_motors and GPIO_AVAILABLE
        self.command_cooldown = command_cooldown  # Increased to 200ms for stability
        self.control_mode = "gpio"
        
        # Command tracking
        self.last_command = None
        self.last_command_time = 0
        self.command_lock = threading.Lock()
        
        # Motor state tracking
        self.current_speed = 0  # 0-100%
        self.current_turn = 0   # -100 to 100 (negative = left)
        
        # Arduino connection (if applicable)
        self.arduino = None
        self.arduino_connected = False
        self.arduino_lock = threading.Lock()
        
        # GPIO setup for direct control
        if self.control_mode == "gpio" and GPIO_AVAILABLE and enable_motors:
            # Define L298N control pins
            # Motor A
            self.in1_pin = 23
            self.in2_pin = 21
            # Motor B
            self.in3_pin = 19
            self.in4_pin = 26
            
            self.motor_pins = [self.in1_pin, self.in2_pin, self.in3_pin, self.in4_pin]
            
            # Set up GPIO
            GPIO.setmode(GPIO.BOARD)
            for pin in self.motor_pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)  # Initialize all pins to LOW
            
            logger.info("GPIO initialized for motor control")
        
        # For filtering rapid joystick changes
        self.last_motion_state = None

    def send_command(self, command, source="manual"):
        """
        Send a motor command.
        
        Args:
            command: One of the CMD_* constants.
            source: Source of the command (for logging).
        
        Returns:
            success: Whether the command was sent.
        """
        current_time = time.time()
        with self.command_lock:
            # Rate limit repeated commands to avoid noisy signals
            if (self.last_command == command and 
                current_time - self.last_command_time < self.command_cooldown):
                return False  # Skip sending the same command too frequently
            
            self.last_command = command
            self.last_command_time = current_time
        
        logger.info(f"Motor command: {command} (from {source})")
        
        if not self.motors_enabled:
            logger.info("Motors disabled - command simulated")
            return True
        
        # Send the command based on control mode
        if self.control_mode == "gpio" and GPIO_AVAILABLE:
            return self._send_gpio_command(command)
        else:
            logger.warning("Unable to send command - invalid control mode or not connected")
            return False

    def _send_gpio_command(self, command):
        """
        Send command directly to GPIO pins.
        """
        if not GPIO_AVAILABLE or not self.motors_enabled:
            return False
        
        # Stop all motors first
        for pin in self.motor_pins:
            GPIO.output(pin, GPIO.LOW)
        
        # Execute the appropriate command
        if command == self.CMD_FORWARD:  # Forward - both motors forward
            GPIO.output(self.in1_pin, GPIO.HIGH)
            GPIO.output(self.in2_pin, GPIO.LOW)
            GPIO.output(self.in3_pin, GPIO.HIGH)
            GPIO.output(self.in4_pin, GPIO.LOW)
            logger.debug("Motors: Moving Forward")
            
        elif command == self.CMD_BACKWARD:  # Backward - both motors backward
            GPIO.output(self.in1_pin, GPIO.LOW)
            GPIO.output(self.in2_pin, GPIO.HIGH)
            GPIO.output(self.in3_pin, GPIO.LOW)
            GPIO.output(self.in4_pin, GPIO.HIGH)
            logger.debug("Motors: Moving Backward")
            
        elif command == self.CMD_RIGHT:  # Right - left motor forward, right motor backward
            GPIO.output(self.in1_pin, GPIO.HIGH)
            GPIO.output(self.in2_pin, GPIO.LOW)
            GPIO.output(self.in3_pin, GPIO.LOW)
            GPIO.output(self.in4_pin, GPIO.HIGH)
            logger.debug("Motors: Turning Right")
            
        elif command == self.CMD_LEFT:  # Left - right motor forward, left motor backward
            GPIO.output(self.in1_pin, GPIO.LOW)
            GPIO.output(self.in2_pin, GPIO.HIGH)
            GPIO.output(self.in3_pin, GPIO.HIGH)
            GPIO.output(self.in4_pin, GPIO.LOW)
            logger.debug("Motors: Turning Left")
            
        elif command == self.CMD_STOP:  # Stop - all motors stopped
            # All pins already set to LOW
            logger.debug("Motors: Stopped")
        
        return True

    def process_joystick_input(self, forward, turn):
        """
        Process joystick input and convert to motor commands.
        
        Args:
            forward: Forward/backward value (-1.0 to 1.0).
            turn: Left/right value (-1.0 to 1.0).
            
        Returns:
            command: The motor command sent (if any).
        """
        # Determine the current motion state based on joystick input
        motion = self._determine_motion(forward, turn)
        
        # Only send the command if the state has changed
        if motion != self.last_motion_state:
            self.last_motion_state = motion
            return self.send_command(motion, "joystick")
        
        return False

    def _determine_motion(self, forward, turn):
        """
        Determine the motor command based on joystick values.
        
        Args:
            forward: Forward/backward value (-1.0 to 1.0).
            turn: Left/right value (-1.0 to 1.0).
        
        Returns:
            One of the CMD_* constants.
        """
        # If both forward and turn are near zero, stop
        if abs(forward) < 0.1 and abs(turn) < 0.1:
            return self.CMD_STOP
        
        # Prioritize turning if the turn value dominates
        if abs(turn) > abs(forward):
            return self.CMD_RIGHT if turn > 0.1 else self.CMD_LEFT
        else:
            return self.CMD_FORWARD if forward > 0.1 else self.CMD_BACKWARD

    def emergency_stop(self):
        """Emergency stop - immediately halt all motors."""
        logger.warning("EMERGENCY STOP activated")
        return self.send_command(self.CMD_STOP, "emergency")
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up motor controller resources")
        self.send_command(self.CMD_STOP, "cleanup")
        
        # Clean up GPIO if using direct control
        if self.control_mode == "gpio" and GPIO_AVAILABLE and self.motors_enabled:
            time.sleep(0.1)  # Small delay to ensure motors stop
            GPIO.cleanup()
            logger.info("GPIO cleaned up")
