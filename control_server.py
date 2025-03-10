from flask import Flask
from flask_socketio import SocketIO, emit
import time
import threading
from threading import Thread

# Import pyserial with a different name to avoid conflicts
import serial as pyserial

# Flask app setup
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Arduino connection settings
ARDUINO_PORT = "/dev/ttyACM0"  # Updated port from your system
BAUD_RATE = 9600

# Movement state
movement = {"forward": 0, "turn": 0}
running = True  # To allow stopping the telemetry loop if needed
arduino = None  # Will hold our serial connection
arduino_lock = threading.Lock()  # Thread lock for serial access

# Connect to Arduino
def connect_to_arduino():
    global arduino
    try:
        arduino = pyserial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for Arduino to reset
        print(f'Connected to Arduino on {ARDUINO_PORT}')
        socketio.emit('log', f'Connected to Arduino on {ARDUINO_PORT}')
        return True
    except pyserial.SerialException as e:
        print(f'Error connecting to Arduino: {e}')
        socketio.emit('log', f'Error connecting to Arduino: {e}')
        return False

# Send command to Arduino
def send_arduino_command(command):
    global arduino
    if arduino and arduino.is_open:
        with arduino_lock:
            try:
                arduino.write(command.encode())
                time.sleep(0.1)  # Short delay
                
                # Read response from Arduino if available
                if arduino.in_waiting > 0:
                    response = arduino.readline().decode().strip()
                    return response
            except Exception as e:
                print(f'Error sending command to Arduino: {e}')
                socketio.emit('log', f'Error sending command to Arduino: {e}')
    return None

# Convert movement values to Arduino commands
def movement_to_command(movement):
    forward = movement.get('forward', 0)  # -1 to 1
    turn = movement.get('turn', 0)  # -1 to 1
    
    # Determine command based on movement values
    if abs(forward) < 0.2 and abs(turn) < 0.2:
        return 'S'  # Stop if joystick near center
    
    if abs(turn) > abs(forward):
        # Turning dominates
        if turn > 0.2:
            return 'R'  # Right
        elif turn < -0.2:
            return 'L'  # Left
    else:
        # Forward/backward dominates
        if forward > 0.2:
            return 'F'  # Forward
        elif forward < -0.2:
            return 'B'  # Backward
    
    return 'S'  # Default stop

# Motor control thread
def motor_control_thread():
    """Process movement commands and send to Arduino."""
    global running, movement
    last_command = None
    
    while running:
        command = movement_to_command(movement)
        
        # Only send command if it changed (to reduce serial traffic)
        if command != last_command:
            response = send_arduino_command(command)
            if response:
                print(f'Arduino: {response}')
                socketio.emit('log', f'Arduino: {response}')
            last_command = command
        
        time.sleep(0.1)  # 10 updates per second should be sufficient

# Telemetry thread
def telemetry_thread():
    """Send server-generated events to clients."""
    count = 0
    while running:
        socketio.sleep(1)  # Send updates every second
        count += 1
        # Example of sending telemetry data periodically
        socketio.emit('telemetry', {
            'battery': 85 - (count % 10),
            'current_motion': movement_to_command(movement)
        })
        
        # Example of sending log messages periodically
        if count % 10 == 0:  # Every 10 seconds
            socketio.emit('log', f'System check: Motors functioning normally')

@socketio.on('connect')
def handle_connect():
    socketio.emit('log', 'Connection established with control server.')
    print('Client connected')
    
    # Start the telemetry thread
    socketio.start_background_task(telemetry_thread)
    
    # Attempt to connect to Arduino if not already connected
    global arduino
    if not arduino or not arduino.is_open:
        if connect_to_arduino():
            # Start the motor control thread
            socketio.start_background_task(motor_control_thread)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')
    # We don't stop motor control on disconnect - client might reconnect

@socketio.on('control')
def handle_control(data):
    global movement
    # Update the movement dict with received control data
    movement = data
    # Optionally log for debugging
    print(f"Received control: {data}")

@socketio.on('emergency_stop')
def handle_emergency_stop(data):
    global movement
    movement = {"forward": 0, "turn": 0}
    send_arduino_command('S')  # Stop command
    socketio.emit('log', 'Emergency stop activated. Motors stopped.')
    socketio.emit('emergency_stop_activated', {})

# Cleanup function for closing serial connection
def cleanup():
    global running, arduino
    running = False
    if arduino and arduino.is_open:
        arduino.close()
        print("Arduino connection closed")

if __name__ == '__main__':
    try:
        # Initial connection to Arduino
        if connect_to_arduino():
            # Start motor control thread
            motor_thread = threading.Thread(target=motor_control_thread)
            motor_thread.daemon = True
            motor_thread.start()
            
            # Start the Flask-SocketIO server
            socketio.run(app, host='0.0.0.0', port=9000)
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        cleanup()