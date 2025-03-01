from flask import Flask, Response
import cv2
import time
from threading import Thread, Lock
from object_dection import ObjectDetection

app = Flask(__name__)

obj = ObjectDetection()

# Shared frame buffer and lock
object_overlay = True  # Start with overlay enabled
detect_objects = False  # Start with object detection enabled
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
            break

        # Always keep the raw frame (no boxes)
        with frame_lock:
            latest_frame = frame.copy()

        # Run inference to get boxes (but not draw them)
        latest_boxes = obj.inference(frame) if detect_objects else []

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, threaded=True)
