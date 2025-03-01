from flask import Flask
from flask_socketio import SocketIO, emit
import time
from threading import Thread

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Movement state
movement = {"forward": 0, "turn": 0}
running = True  # To allow stopping the telemetry loop if needed

# Thread tracking
thread_running = False

# Add a background thread for sending periodic updates
def background_thread():
    """Send server-generated events to clients."""
    global thread_running
    thread_running = True
    
    count = 0
    while running:
        socketio.sleep(1)  # Send updates every second
        count += 1
        # Example of sending telemetry data periodically
        socketio.emit('telemetry', {'battery': 85 - (count % 10)})
        # Example of sending log messages periodically
        if count % 5 == 0:  # Every 5 seconds
            socketio.emit('log', f'System status check: {count}')
    
    thread_running = False

@socketio.on('connect')
def handle_connect():
    socketio.emit('log', 'Connection established with control server.')
    print('Client connected')
    # Start the background thread only if it's not already running
    global thread_running
    if not thread_running:
        socketio.start_background_task(background_thread)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('control')
def handle_control(data):
    global movement
    movement = data
    # Send immediate feedback about received control data

@socketio.on('emergency_stop')
def handle_emergency_stop(data):
    global movement
    movement = {"forward": 0, "turn": 0}
    socketio.emit('log', 'Emergency stop received. Stopping all motors.')
    socketio.emit('emergency_stop_activated', {})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=9000)