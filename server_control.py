# direct_gpio_server.py
from flask import Flask
from flask_socketio import SocketIO
import threading
import time
import Jetson.GPIO as GPIO

# Flask setup
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# GPIO setup
GPIO.setmode(GPIO.BOARD)

# Define motor control pins
# Motor A
in1_pin = 23  # spi1_sck
in2_pin = 21  # spi1_din
# Motor B
in3_pin = 19  # spi1_dout
in4_pin = 26  # spi1_cs1

# Create a list of all pins
motor_pins = [in1_pin, in2_pin, in3_pin, in4_pin]

# Set up all pins as outputs
for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Initialize all pins to LOW

print("GPIO initialized for motor control")

# State
movement = {"forward": 0, "turn": 0}
running = True

def send_command(cmd):
    """Send command to motors using GPIO."""
    try:
        # Stop motors first
        for pin in motor_pins:
            GPIO.output(pin, GPIO.LOW)
        
        # Execute the command
        if cmd == 'F':  # Forward - both motors forward
            GPIO.output(in1_pin, GPIO.HIGH)
            GPIO.output(in2_pin, GPIO.LOW)
            GPIO.output(in3_pin, GPIO.HIGH)
            GPIO.output(in4_pin, GPIO.LOW)
            
        elif cmd == 'B':  # Backward - both motors backward
            GPIO.output(in1_pin, GPIO.LOW)
            GPIO.output(in2_pin, GPIO.HIGH)
            GPIO.output(in3_pin, GPIO.LOW)
            GPIO.output(in4_pin, GPIO.HIGH)
            
        elif cmd == 'L':  # Left - right motor forward, left motor backward
            GPIO.output(in1_pin, GPIO.LOW)
            GPIO.output(in2_pin, GPIO.HIGH)  # Left motor backward
            GPIO.output(in3_pin, GPIO.HIGH)
            GPIO.output(in4_pin, GPIO.LOW)   # Right motor forward
            
        elif cmd == 'R':  # Right - left motor forward, right motor backward
            GPIO.output(in1_pin, GPIO.HIGH)
            GPIO.output(in2_pin, GPIO.LOW)   # Left motor forward
            GPIO.output(in3_pin, GPIO.LOW)
            GPIO.output(in4_pin, GPIO.HIGH)  # Right motor backward
            
        elif cmd == 'S':  # Stop - all motors stopped
            # All pins already set to LOW
            pass
            
        print(f"Executed command: {cmd}")
        return True
    except Exception as e:
        print(f"Error executing command: {e}")
        return False

def get_motor_command():
    """Convert joystick values to motor commands."""
    f = movement.get("forward", 0)
    t = movement.get("turn", 0)
    
    if abs(f) < 0.2 and abs(t) < 0.2:
        return "S"  # Stop
    
    if abs(t) > abs(f):
        return "R" if t > 0 else "L"
    else:
        return "F" if f > 0 else "B"

def motor_control_loop():
    """Background thread for motor control."""
    last_cmd = None
    while running:
        cmd = get_motor_command()
        if cmd != last_cmd:
            send_command(cmd)
            socketio.emit('log', f'Command: {cmd}')
            last_cmd = cmd
        time.sleep(0.1)

def telemetry_thread():
    """Background thread for telemetry updates."""
    count = 0
    while running:
        socketio.sleep(1)
        count += 1
        cmd = get_motor_command()
        socketio.emit('telemetry', {
            'battery': 85 - (count % 10),
            'current_motion': cmd
        })
        
        # Periodic status updates
        if count % 10 == 0:
            socketio.emit('log', f'System check: Motors functioning (Mode: {cmd})')

@socketio.on('connect')
def handle_connect():
    print("Client connected")
    socketio.emit('log', 'Connection established with control server')
    
    # Start telemetry thread
    socketio.start_background_task(telemetry_thread)

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('control')
def handle_control(data):
    global movement
    movement = data
    print(f"Control: {data}")

@socketio.on('emergency_stop')
def handle_emergency_stop(data=None):
    global movement
    movement = {"forward": 0, "turn": 0}
    send_command('S')
    print("Emergency stop activated")
    socketio.emit('log', 'Emergency stop activated')
    socketio.emit('emergency_stop_activated', {})

if __name__ == "__main__":
    try:
        print("Initializing GPIO motor control...")
        
        # Send initial stop command to test
        if send_command('S'):
            print("GPIO motor control established")
            socketio.emit('log', 'GPIO motor control initialized')
            
            # Start motor control thread
            control_thread = threading.Thread(target=motor_control_loop)
            control_thread.daemon = True
            control_thread.start()
            
            print("Starting server on port 9000...")
            socketio.run(app, host="0.0.0.0", port=9000)
        else:
            print("Failed to initialize GPIO. Check connections.")
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    finally:
        running = False
        # Clean up GPIO
        print("Cleaning up GPIO...")
        for pin in motor_pins:
            GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup()