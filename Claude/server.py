from flask import Flask, Response, render_template, send_from_directory, request
from flask_socketio import SocketIO, emit
import cv2
import time
import logging
import os
import json
import threading
from threading import Thread, Lock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('server')

class RCTankServer:
    """
    Unified server for RC tank handling both HTTP and WebSocket connections.
    Provides video streaming, control interface, and telemetry.
    """
    
    def __init__(self, motor_controller, object_detection=None,
                 http_port=8000, ws_port=None, static_folder='static'):
        """
        Initialize the server
        
        Args:
            motor_controller: MotorController instance
            object_detection: ObjectDetection instance (optional)
            http_port: Port for HTTP server
            ws_port: Port for WebSocket (if None, uses the same as HTTP)
            static_folder: Folder for static files
        """
        self.motor_controller = motor_controller
        self.object_detector = object_detection
        self.http_port = http_port
        self.ws_port = ws_port if ws_port is not None else http_port
        self.static_folder = static_folder
        
        # Ensure static folder exists
        os.makedirs(static_folder, exist_ok=True)
        
        # Create Flask app
        self.app = Flask(__name__, 
                         static_folder=static_folder, 
                         static_url_path='')
        
        # Initialize Socket.IO
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        # Shared frame buffer and lock for video streaming
        self.frame_lock = Lock()
        self.latest_frame = None
        self.latest_boxes = []
        self.object_overlay = True  # Show detected objects on video feed
        self.detect_objects = True  # Run object detection on frames
        
        # Set up camera
        self.camera = None
        self.camera_width = 640
        self.camera_height = 480
        
        # Flag to indicate if capture thread is running
        self.capture_running = False
        self.capture_thread = None
        
        # Register routes and event handlers
        self._register_routes()
        self._register_socketio_handlers()
        
        # Telemetry state
        self.telemetry = {
            "battery": 100,
            "current_motion": "S",
            "auto_navigation": False,
            "object_detection": True
        }
        
        logger.info(f"Server initialized on HTTP port {http_port}")
    
    def _register_routes(self):
        """Register Flask routes"""
        # Main page
        @self.app.route('/')
        def index():
            return send_from_directory(self.static_folder, 'index.html')
        
        # Video stream
        @self.app.route('/video')
        def video_feed():
            return Response(self._generate_frames(), 
                           mimetype='multipart/x-mixed-replace; boundary=frame')
        
        # Toggle object overlay
        @self.app.route('/toggle_overlay')
        def toggle_overlay():
            self.object_overlay = not self.object_overlay
            logger.info(f"Object overlay {'enabled' if self.object_overlay else 'disabled'}")
            return f"Overlay {'enabled' if self.object_overlay else 'disabled'}"
        
        # Toggle object detection
        @self.app.route('/toggle_detection')
        def toggle_detection():
            self.detect_objects = not self.detect_objects
            logger.info(f"Object detection {'enabled' if self.detect_objects else 'disabled'}")
            self.telemetry["object_detection"] = self.detect_objects
            return f"Object detection {'enabled' if self.detect_objects else 'disabled'}"
        
        # Toggle autonomous navigation (person following)
        @self.app.route('/toggle_navigation')
        def toggle_navigation():
            if self.object_detector:
                auto_nav = self.object_detector.set_auto_navigation(
                    not self.object_detector.auto_navigation
                )
                self.telemetry["auto_navigation"] = auto_nav
                status = 'enabled' if auto_nav else 'disabled'
                logger.info(f"Person following {status}")
                return f"Person following {status}"
            return "Object detection not available"
        
        # Emergency stop
        @self.app.route('/emergency_stop')
        def emergency_stop():
            if self.motor_controller:
                self.motor_controller.emergency_stop()
            logger.warning("Emergency stop activated via HTTP")
            self.socketio.emit('log', 'Emergency stop activated via HTTP')
            return "Emergency stop activated"
            
        # Additional routes for compatibility with original interface
        
        # Toggle Arduino connection (compatibility with original)
        @self.app.route('/toggle_arduino')
        def toggle_arduino():
            if self.motor_controller and self.motor_controller.control_mode == "arduino":
                if self.motor_controller.arduino_connected:
                    self.motor_controller.arduino_connected = False
                    if self.motor_controller.arduino:
                        with self.motor_controller.arduino_lock:
                            self.motor_controller.arduino.close()
                    status = "disabled"
                else:
                    self.motor_controller.connect_to_arduino()
                    status = "enabled" if self.motor_controller.arduino_connected else "failed to connect"
                
                logger.info(f"Arduino control {status}")
                return f"Arduino control {status}"
            return "Arduino control not available in current mode"
            
        # Reconnect Arduino (compatibility with original)
        @self.app.route('/reconnect_arduino')
        def reconnect_arduino():
            if self.motor_controller and self.motor_controller.control_mode == "arduino":
                success = self.motor_controller.connect_to_arduino()
                if success:
                    return "Arduino reconnected successfully"
                else:
                    return "Failed to reconnect Arduino"
            return "Arduino control not available in current mode"
    
    def _register_socketio_handlers(self):
        """Register Socket.IO event handlers"""
        @self.socketio.on('connect')
        def handle_connect():
            logger.info("Client connected via WebSocket")
            emit('log', 'Connection established with control server.')
            
            # Start a background task for telemetry
            self.socketio.start_background_task(self._telemetry_thread)
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            logger.info("Client disconnected")
        
        @self.socketio.on('control')
        def handle_control(data):
            # Update motion based on joystick input
            if self.motor_controller:
                forward = data.get('forward', 0) / 100.0  # Convert to -1.0 to 1.0
                turn = data.get('turn', 0) / 100.0
                
                # Only process control if auto-navigation is disabled
                if not (self.object_detector and self.object_detector.auto_navigation):
                    self.motor_controller.process_joystick_input(forward, turn)
                
                # Update telemetry
                self.telemetry["current_motion"] = self._get_motion_state(forward, turn)
                
                # Log movement for debugging
                logger.debug(f"Control input: forward={forward}, turn={turn}")
        
        @self.socketio.on('emergency_stop')
        def handle_emergency_stop(data):
            if self.motor_controller:
                self.motor_controller.emergency_stop()
                
            logger.warning("Emergency stop activated via WebSocket")
            emit('log', 'Emergency stop activated. Motors stopped.')
            emit('emergency_stop_activated', {})
    
    def _get_motion_state(self, forward, turn):
        """Convert motion values to a readable state"""
        if abs(forward) < 0.1 and abs(turn) < 0.1:
            return "S"  # Stopped
        
        if abs(turn) > abs(forward):
            if turn > 0.1:
                return "R"  # Right
            elif turn < -0.1:
                return "L"  # Left
        else:
            if forward > 0.1:
                return "F"  # Forward
            elif forward < -0.1:
                return "B"  # Backward
        
        return "S"  # Default stop
    
    def _telemetry_thread(self):
        """Send periodic telemetry updates to clients"""
        count = 0
        while True:
            self.socketio.sleep(1)  # Send updates every second
            
            # Simulate battery drain
            count += 1
            if count % 60 == 0 and self.telemetry["battery"] > 0:
                self.telemetry["battery"] -= 1
            
            # Send telemetry to connected clients
            self.socketio.emit('telemetry', self.telemetry)
            
            # Periodic log message
            if count % 30 == 0:
                self.socketio.emit('log', 'System status: Normal operation')
    
    def _camera_thread(self):
        """Background thread for camera capture"""
        logger.info("Starting camera capture thread")
        
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
        
        while self.capture_running:
            success, frame = self.camera.read()
            if not success:
                logger.error("Failed to read frame from camera")
                time.sleep(0.1)
                continue
            
            # Store raw frame
            with self.frame_lock:
                self.latest_frame = frame.copy()
            
            # Run object detection if enabled
            if self.detect_objects and self.object_detector:
                # Run detection but only navigate if auto-navigation is enabled
                self.latest_boxes = self.object_detector.inference(frame)
            else:
                self.latest_boxes = []
            
            # Short delay to limit CPU usage
            time.sleep(0.03)
        
        # Clean up camera when thread exits
        if self.camera:
            self.camera.release()
            self.camera = None
    
    def _draw_boxes(self, frame, boxes):
        """Draw detection boxes on the frame"""
        for box in boxes:
            x1, y1, x2, y2 = box['x1'], box['y1'], box['x2'], box['y2']
            label = f"{box['label']} {box['conf']:.2f}"

            # Draw rectangle
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Draw label text
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    def _generate_frames(self):
        """Generator function for video streaming"""
        while True:
            with self.frame_lock:
                if self.latest_frame is None:
                    time.sleep(0.1)
                    continue

                frame_to_send = self.latest_frame.copy()

                # Draw object detection boxes if overlay is enabled
                if self.object_overlay and self.latest_boxes:
                    self._draw_boxes(frame_to_send, self.latest_boxes)

                # Add status text
                status_text = []
                if self.object_detector and self.object_detector.auto_navigation:
                    status_text.append("AUTO")
                
                if status_text:
                    status_str = " | ".join(status_text)
                    cv2.putText(frame_to_send, status_str, (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                # Convert frame to JPEG
                _, buffer = cv2.imencode('.jpg', frame_to_send)

            # Yield the frame in MJPEG format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            
            # Short delay to control frame rate
            time.sleep(0.03)
    
    def start(self):
        """Start the server and camera thread"""
        # Start camera capture thread
        self.capture_running = True
        self.capture_thread = Thread(target=self._camera_thread)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
        # Start the Flask-SocketIO server
        try:
            if self.http_port == self.ws_port:
                logger.info(f"Starting server on port {self.http_port}")
                self.socketio.run(self.app, host='0.0.0.0', port=self.http_port)
            else:
                # If using different ports, more complex setup is needed
                logger.error("Different HTTP and WS ports not supported")
                self.socketio.run(self.app, host='0.0.0.0', port=self.http_port)
        except KeyboardInterrupt:
            logger.info("Server shutting down...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server and release resources"""
        logger.info("Stopping server")
        
        # Stop camera thread
        self.capture_running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        
        # Release camera if still open
        if self.camera:
            self.camera.release()
            self.camera = None