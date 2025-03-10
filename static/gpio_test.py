import Jetson.GPIO as GPIO
import time

# Set pin numbering mode
GPIO.setmode(GPIO.BOARD)

# Define L298N control pins
# Motor A
in1_pin = 23  # spi1_sck
in2_pin = 21  # spi1_din
# Motor B
in3_pin = 19  # spi1_dout
in4_pin = 26  # spi1_cs1

# Create a dictionary for better debugging
pins = {
    "in1": in1_pin,
    "in2": in2_pin,
    "in3": in3_pin, 
    "in4": in4_pin
}

# Setup all pins
motor_pins = [in1_pin, in2_pin, in3_pin, in4_pin]
for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Initialize all pins to LOW

def print_pin_states():
    """Print the current state of all pins"""
    states = {name: GPIO.input(pin) for name, pin in pins.items()}
    print(f"Pin states: {states}")

def stop_motors():
    """Stop both motors with verification"""
    print("Stopping motors...")
    for pin in motor_pins:
        GPIO.output(pin, GPIO.LOW)
    time.sleep(0.1)  # Brief delay
    print_pin_states()  # Verify pins are LOW

def test_motors():
    try:
        print("\nL298N Motor Control Test")
        print("------------------------")
        
        # Test each motor individually with verification between tests
        print("\nRunning Motor A forward")
        GPIO.output(in1_pin, GPIO.HIGH)
        GPIO.output(in2_pin, GPIO.LOW)
        print_pin_states()
        time.sleep(2)
        
        print("\nStopping Motor A")
        stop_motors()
        time.sleep(1)  # Longer pause between tests
        
        print("\nRunning Motor A backward")
        GPIO.output(in1_pin, GPIO.LOW)
        GPIO.output(in2_pin, GPIO.HIGH)
        print_pin_states()
        time.sleep(2)
        
        print("\nStopping Motor A")
        stop_motors()
        time.sleep(1)
        
        print("\nRunning Motor B forward")
        GPIO.output(in3_pin, GPIO.HIGH)
        GPIO.output(in4_pin, GPIO.LOW)
        print_pin_states()
        time.sleep(2)
        
        print("\nStopping Motor B")
        stop_motors()
        time.sleep(1)
        
        print("\nRunning Motor B backward")
        GPIO.output(in3_pin, GPIO.LOW)
        GPIO.output(in4_pin, GPIO.HIGH)
        print_pin_states()
        time.sleep(2)
        
        print("\nStopping all motors")
        stop_motors()
        
        print("\nTest complete")
        
    except KeyboardInterrupt:
        print("Program interrupted by user")
    finally:
        print("\nFinal cleanup...")
        print_pin_states()
     

# Run the test
test_motors()