# robot_control.py - Simple control server using Flask-SocketIO
from flask import Flask
from flask_socketio import SocketIO, emit
import time
import threading

# Use fully qualified import to avoid conflicts
try:
    import serial
    print("Successfully imported pyserial module")
except ImportError:
    print("Failed to import pyserial. Installing...")
    import subprocess
    subprocess.call(["pip3", "install", "--user", "pyserial"])
    try:
        import serial
        print("Successfully installed and imported pyserial")
    except ImportError:
        print("Error: Could not import pyserial even after installation")
        print("Try: pip3 install --user pyserial")
        exit(1)

# Flask app setup
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Arduino connection settings
ARDUINO_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600

# Global variables
movement = {"forward": 0, "turn": 0}
running = True
arduino = None
arduino_lock = threading.Lock()

# Try to connect to Arduino
def connect_to_arduino():
    global arduino
    try:
        print(f"Attempting to connect to Arduino on {ARDUINO_PORT}...")
        arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for Arduino to reset
        print(f"Connected to Arduino on {ARDUINO_PORT}")
        return True
    except Exception as e:
        print(f"Error connecting to Arduino: {e}")
        return False

# Send command to Arduino
def send_command(cmd):
    if arduino and arduino.is_open:
        with arduino_lock:
            try:
                arduino.write(cmd.encode())
                time.sleep(0.1)
                if arduino.in_waiting > 0:
                    return arduino.readline().decode().strip()
            except Exception as e:
                print(f"Error sending command: {e}")
    return None

# Movement logic
def get_motor_command():
    f = movement.get("forward", 0)
    t = movement.get("turn", 0)
    
    # Simple threshold-based logic
    if abs(f) < 0.2 and abs(t) < 0.2:
        return "S"  # Stop
    
    if abs(t) > abs(f):
        return "R" if t > 0 else "L"  # Turn right or left
    else:
        return "F" if f > 0 else "B"  # Forward or backward

# Motor control thread
def motor_control_loop():
    last_cmd = None
    while running:
        cmd = get_motor_command()
        if cmd != last_cmd:
            print(f"Sending command: {cmd}")
            response = send_command(cmd)
            if response:
                print(f"Arduino: {response}")
            last_cmd = cmd
        time.sleep(0.1)

# Socket.IO event handlers
@socketio.on("connect")
def handle_connect():
    print("Client connected")
    socketio.emit("log", "Connected to control server")

@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")

@socketio.on("control")
def handle_control(data):
    global movement
    movement = data
    print(f"Control: {data}")

@socketio.on("emergency_stop")
def handle_emergency_stop():
    global movement
    movement = {"forward": 0, "turn": 0}
    send_command("S")
    print("Emergency stop activated")
    socketio.emit("log", "Emergency stop activated")

# Main program
if __name__ == "__main__":
    try:
        if connect_to_arduino():
            # Start motor control thread
            control_thread = threading.Thread(target=motor_control_loop)
            control_thread.daemon = True
            control_thread.start()
            
            print("Starting server on port 9000...")
            socketio.run(app, host="0.0.0.0", port=9000)
        else:
            print("Failed to connect to Arduino. Check connections and try again.")
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        running = False
        if arduino and arduino.is_open:
            arduino.close()