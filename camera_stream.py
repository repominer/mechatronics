from flask import Flask, Response
import cv2
import time
from threading import Thread, Lock
from object_dection import ObjectDetection

app = Flask(__name__)

# Initialize the object detection with Arduino control
# Make sure to use the correct Arduino port
# Will still work if Arduino is not connected
obj = ObjectDetection()

# Shared frame buffer and lock
object_overlay = True  # Start with overlay enabled
detect_objects = True  # Start with object detection enabled
auto_navigation = False  # Toggle for autonomous navigation
latest_frame = None
latest_boxes = []
frame_lock = Lock()

def camera_inference_loop():
    global latest_frame, latest_boxes

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:
        success, frame = cap.read()
        if not success:
            print('Error reading frame')
            break

        # Always keep the raw frame (no boxes)
        with frame_lock:
            latest_frame = frame.copy()

        # Run inference to get boxes (but not draw them)
        # If auto_navigation is enabled, this will also send commands to Arduino
        if detect_objects:
            latest_boxes = obj.inference(frame)
        else:
            latest_boxes = []
            # Send stop command if detection is disabled
            if auto_navigation:
                obj.send_arduino_command("S")


    cap.release()

# Start the background thread on app start
inference_thread = Thread(target=camera_inference_loop, daemon=True)
inference_thread.start()

def draw_boxes(frame, boxes):
    """Draw boxes on the frame (when object_overlay is enabled)."""
    for box in boxes:
        x1, y1, x2, y2 = box['x1'], box['y1'], box['x2'], box['y2']
        label = f"{box['label']} {box['conf']:.2f}"

        # Draw rectangle
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Draw label text
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

def generate_frames():
    global latest_frame, latest_boxes

    while True:
        with frame_lock:
            if latest_frame is None:
                continue

            frame_to_send = latest_frame.copy()

            if object_overlay:
                draw_boxes(frame_to_send, latest_boxes)

            _, buffer = cv2.imencode('.jpg', frame_to_send)

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.03)  # slight delay to control frame rate

@app.route('/video')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/toggle_overlay')
def toggle_overlay():
    global object_overlay
    object_overlay = not object_overlay
    return f"Overlay {'enabled' if object_overlay else 'disabled'}"

@app.route('/toggle_detection')
def toggle_detection():
    global detect_objects
    detect_objects = not detect_objects
    return f"Object detection {'enabled' if detect_objects else 'disabled'}"

@app.route('/toggle_navigation')
def toggle_navigation():
    global auto_navigation
    auto_navigation = not auto_navigation
    status = 'enabled' if auto_navigation else 'disabled'
    print(f"Autonomous navigation {status}")
    return f"Autonomous navigation {status}"

@app.route('/toggle_arduino')
def toggle_arduino():
    obj.arduino_enabled = not obj.arduino_enabled
    status = 'enabled' if obj.arduino_enabled else 'disabled'
    if obj.arduino_enabled and not obj.arduino_connected:
        obj.arduino_connected = obj.connect_to_arduino()
    print(f"Arduino control {status}")
    return f"Arduino control {status}"

@app.route('/reconnect_arduino')
def reconnect_arduino():
    if obj.arduino_enabled:
        success = obj.connect_to_arduino()
        if success:
            return "Arduino reconnected successfully"
        else:
            return "Failed to reconnect Arduino"
    else:
        return "Arduino control is disabled"

@app.route('/emergency_stop')
def emergency_stop():
    obj.send_arduino_command("S")  # Emergency stop
    return "Emergency stop activated"

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=8000, threaded=True)
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        obj.cleanup()  # Close Arduino connection on shutdown