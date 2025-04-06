import cv2
import signal
import json # Not currently used, but kept from previous versions
import logging
import os
import threading
import time
from flask import Flask, Response, render_template, send_from_directory, request
from flask_socketio import SocketIO, emit
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
    Provides video streaming, control interface, map interaction, and telemetry.
    """

    def __init__(self, motor_controller, object_detection=None, robot_map=None,
                 navigation_controller=None, # Added for Phase 3 prep
                 http_port=8000, ws_port=None, static_folder='static'):
        """
        Initialize the server

        Args:
            motor_controller: MotorController instance
            object_detection: ObjectDetection instance (optional)
            robot_map: RobotMap instance (optional, needed for pose updates/navigation)
            navigation_controller: NavigationController instance (optional, needed for Phase 3)
            http_port: Port for HTTP server
            ws_port: Port for WebSocket (if None, uses the same as HTTP)
            static_folder: Folder for static files (e.g., map.html, map_script.js)
        """
        self.motor_controller = motor_controller
        self.object_detector = object_detection
        self.robot_map = robot_map # Stored for pose updates (Phase 1)
        self.navigation_controller = navigation_controller # Stored for Phase 3
        self.http_port = http_port
        self.ws_port = ws_port if ws_port is not None else http_port
        self.static_folder = static_folder

        # Ensure static folder exists
        os.makedirs(static_folder, exist_ok=True)

        # Create Flask app
        self.app = Flask(__name__,
                         static_folder=static_folder,
                         template_folder=static_folder, # Added to easily serve map.html
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
        self.navigation_controller = navigation_controller

        # Register routes and event handlers
        self._register_routes()
        self._register_socketio_handlers()

        # Telemetry state
        self.telemetry = {
            "battery": 100,
            "current_motion": "S", # Updated by 'control' handler
            "auto_navigation": False, # Updated by HTTP route /toggle_navigation
            "object_detection": self.detect_objects # Updated by HTTP route /toggle_detection
        }

        logger.info(f"Server initialized. Static folder: {static_folder}. Map enabled: {self.robot_map is not None}")

    def _register_routes(self):
        """Register Flask routes"""
        # Main map page (assuming map.html exists in static folder)
        @self.app.route('/')
        def map_page():
            # Use render_template if map.html uses Jinja, otherwise send_from_directory
            try:
                # Check if map.html exists
                map_file_path = os.path.join(self.static_folder, 'map.html')
                if os.path.exists(map_file_path):
                     logger.info("Serving map.html")
                     return send_from_directory(self.static_folder, 'map.html')
                else:
                     logger.warning("map.html not found in static folder, serving fallback.")
                     # Fallback or error page
                     return "Error: map.html not found.", 404
            except Exception as e:
                 logger.error(f"Error serving map page: {e}")
                 return "Server error", 500


        # Fallback for index.html if needed
        @self.app.route('/index.html')
        def index():
             # Check if index.html exists
            index_file_path = os.path.join(self.static_folder, 'index.html')
            if os.path.exists(index_file_path):
                 logger.info("Serving index.html as fallback/alternative.")
                 return send_from_directory(self.static_folder, 'index.html')
            else:
                 return "Error: index.html not found.", 404

        # Video stream
        @self.app.route('/calibrate')
        def calibrate_page():
            calib_file_path = os.path.join(self.static_folder, 'calibration.html')
            if os.path.exists(calib_file_path):
                 logger.info("Serving calibration.html")
                 return send_from_directory(self.static_folder, 'calibration.html')
            else:
                 logger.error("calibration.html not found!")
                 return "Error: calibration.html not found.", 404

        @self.app.route('/video')
        def video_feed():
            return Response(self._generate_frames(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        # --- Control Endpoints ---
        @self.app.route('/toggle_overlay')
        def toggle_overlay():
            self.object_overlay = not self.object_overlay
            logger.info(f"Object overlay {'enabled' if self.object_overlay else 'disabled'}")
            return f"Overlay {'enabled' if self.object_overlay else 'disabled'}"

        @self.app.route('/toggle_detection')
        def toggle_detection():
            self.detect_objects = not self.detect_objects
            logger.info(f"Object detection {'enabled' if self.detect_objects else 'disabled'}")
            self.telemetry["object_detection"] = self.detect_objects
            self.socketio.emit('telemetry', self.telemetry) # Update clients
            return f"Object detection {'enabled' if self.detect_objects else 'disabled'}"

        # Toggle autonomous navigation (object following)
        @self.app.route('/toggle_navigation')
        def toggle_navigation():
            if self.object_detector:
                auto_nav = self.object_detector.set_auto_navigation(
                    not self.object_detector.auto_navigation
                )
                self.telemetry["auto_navigation"] = auto_nav
                self.socketio.emit('telemetry', self.telemetry) # Update clients
                status = 'enabled' if auto_nav else 'disabled'
                logger.info(f"Object following auto-navigation {status}")
                return f"Object following auto-navigation {status}"
            return "Object detection not available"

        # Emergency stop
        @self.app.route('/emergency_stop')
        def emergency_stop():
            if self.motor_controller:
                self.motor_controller.emergency_stop()
            logger.warning("Emergency stop activated via HTTP")
            self.socketio.emit('log', {'msg': 'Emergency stop activated via HTTP'})
            return "Emergency stop activated"

        # --- Compatibility Routes ---
        # (Arduino routes kept for potential future use, but non-functional with current motor_controller.py)
        @self.app.route('/toggle_arduino')
        def toggle_arduino():
             # ... (implementation remains non-functional unless motor_controller updated) ...
             return "Arduino control not available in current mode"

        @self.app.route('/reconnect_arduino')
        def reconnect_arduino():
             # ... (implementation remains non-functional unless motor_controller updated) ...
             return "Arduino control not available in current mode"

    def _register_socketio_handlers(self):
        """Register Socket.IO event handlers"""

        @self.socketio.on('connect')
        def handle_connect():
            client_id = request.sid # Get client session ID
            logger.info(f"Client connected via WebSocket: {client_id}")
            emit('log', {'msg': 'Connection established with control server.'})

            # Start a background task for telemetry/pose updates if not already running for this client?
            # Or maybe just one global task is enough. Let's stick to one global task for simplicity.
            # If the task isn't running yet, start it.
            if not hasattr(self.socketio, '_telemetry_task_started') or not self.socketio._telemetry_task_started:
                logger.info("Starting background telemetry/pose update task.")
                self.socketio.start_background_task(self._telemetry_and_pose_thread)
                self.socketio._telemetry_task_started = True
            else:
                logger.debug("Telemetry/pose update task already running.")
            # Send current state immediately on connect
            emit('telemetry', self.telemetry)
            if self.robot_map:
                 try:
                     pose_data = {
                         'col': self.robot_map.pos_x,
                         'row': self.robot_map.pos_y,
                         'angle': self.robot_map.angle
                     }
                     emit('robot_update', pose_data)
                 except Exception as e:
                     logger.error(f"Error sending initial pose: {e}")


        @self.socketio.on('disconnect')
        def handle_disconnect():
            client_id = request.sid
            logger.info(f"Client disconnected: {client_id}")
            # Note: Background task continues running

        @self.socketio.on('calibrate_command')
        def handle_calibrate_command(self, data):
            command = data.get('command')
            log_msg = "Calibration command ignored."
            success = False
            PULSE_DURATION = 0.15 # <<<--- Time (in seconds) for the motor pulse. Tune as needed!

            if command in ['F', 'B', 'L', 'R'] and self.motor_controller:
                logger.info(f"Sending calibration pulse: {command} for {PULSE_DURATION}s")
                # Send the movement command
                success = self.motor_controller.send_command(command, 'calibration_start')

                if success:
                    # Wait for the pulse duration
                    # Using time.sleep here blocks this specific worker thread briefly,
                    # which is generally okay for a short calibration action.
                    time.sleep(PULSE_DURATION)
                    # Send the stop command
                    stop_success = self.motor_controller.send_command(self.motor_controller.CMD_STOP, 'calibration_stop')
                    log_msg = f"Single '{command}' pulse sent (Stop success: {stop_success})."
                    # Note: The final 'success' reflects the initial command sending
                else:
                    log_msg = f"Single '{command}' command failed to send (Rate limited or motors disabled?)"

            elif not self.motor_controller:
                 log_msg = "Motor controller not available."
                 logger.warning(log_msg)
            else:
                 log_msg = f"Invalid calibration command: {command}"
                 logger.warning(log_msg)

            # Send feedback to client
            emit('calibration_log', {'msg': log_msg})

        @self.socketio.on('apply_calibration')
        def handle_apply_calibration(data):
            log_msg = "Apply calibration ignored."
            applied = False
            if self.robot_map and isinstance(data, dict):
                distance = data.get('distance') # Gets None if key doesn't exist
                angle = data.get('angle')
                logger.info(f"Received calibration data to apply: distance={distance}, angle={angle}")
                applied = self.robot_map.apply_calibration(distance=distance, angle=angle)
                if applied:
                     log_msg = "Calibration values applied to simulation."
                else:
                     log_msg = "No valid calibration values applied (check logs)."
            elif not self.robot_map:
                log_msg = "Cannot apply calibration: Robot map not available."
                logger.warning(log_msg)
            else:
                 log_msg = f"Invalid data format for apply_calibration: {data}"
                 logger.warning(log_msg)
            # Send feedback
            emit('calibration_log', {'msg': log_msg})


        @self.socketio.on('request_calibration_values')
        def handle_request_calibration_values():
            log_msg = "Cannot get calibration values: Robot map not available."
            if self.robot_map:
                try:
                    # Read current values (add locks in RobotMap if needed)
                    values = {
                        'move_distance': self.robot_map.move_distance,
                        'turn_angle': self.robot_map.turn_angle
                    }
                    logger.info(f"Sending current calibration values: {values}")
                    emit('calibration_values', values)
                    return # Success
                except Exception as e:
                    log_msg = f"Error reading calibration values: {e}"
                    logger.error(log_msg)
            else:
                 logger.warning(log_msg)
            # Send error feedback if values couldn't be sent
            emit('calibration_log', {'msg': log_msg})

        @self.socketio.on('control')
        def handle_control(data):
            # Update motion based on joystick input
            if self.motor_controller:
                try:
                    forward = data.get('forward', 0) / 100.0  # Convert to -1.0 to 1.0
                    turn = data.get('turn', 0) / 100.0

                    # Only process manual control if autonomous modes are disabled
                    auto_nav_active = (self.object_detector and self.object_detector.auto_navigation)
                    map_nav_active = (self.navigation_controller and self.navigation_controller.is_navigating)

                    if not auto_nav_active and not map_nav_active:
                        self.motor_controller.process_joystick_input(forward, turn)
                    elif auto_nav_active:
                         logger.debug("Manual control ignored: Object following active.")
                    elif map_nav_active:
                         logger.debug("Manual control ignored: Map navigation active.")


                    # Update telemetry motion state regardless
                    new_motion_state = self._get_motion_state(forward, turn)
                    if self.telemetry["current_motion"] != new_motion_state:
                         self.telemetry["current_motion"] = new_motion_state
                         # Only emit telemetry if it changed or periodically
                         # Periodic emission is handled by _telemetry_and_pose_thread
                         # emit('telemetry', self.telemetry) # Optional: immediate feedback on change

                    logger.debug(f"Control input: forward={forward:.2f}, turn={turn:.2f}")

                except Exception as e:
                     logger.error(f"Error processing control input {data}: {e}")


        @self.socketio.on('emergency_stop')
        def handle_emergency_stop(data=None): # Data not expected but handle if sent
            if self.motor_controller:
                self.motor_controller.emergency_stop()
            # Also stop map navigation if active
            if self.navigation_controller:
                self.navigation_controller.clear_target() # This should also stop motors

            logger.warning("Emergency stop activated via WebSocket")
            emit('log', {'msg': 'Emergency stop activated. Motors stopped. Navigation cancelled.'}, broadcast=True) # Inform all clients
            # Optionally send specific event if needed by UI
            # emit('emergency_stop_activated', {})

        # --- Phase 2 Handlers ---
        @self.socketio.on('navigate_to')
        def handle_navigate_to(data):
            navigation_controller = getattr(self, 'navigation_controller', None)

            if not self.robot_map:
                logger.warning("Cannot navigate: Robot map not available.")
                emit('log', {'msg': 'Navigation error: Map not available.'})
                return

            try:
                if not isinstance(data, dict) or 'row' not in data or 'col' not in data:
                     raise ValueError("Invalid data format: expecting {'row': r, 'col': c}")
                target_row = int(data['row'])
                target_col = int(data['col'])

                grid_size = self.robot_map.grid_size
                if not (0 <= target_row < grid_size and 0 <= target_col < grid_size):
                    raise ValueError(f"Target coordinates ({target_row},{target_col}) out of bounds (Grid Size: {grid_size})")

                logger.info(f"Received navigation target via WebSocket: Row={target_row}, Col={target_col}")
                emit('log', {'msg': f"Navigation target set to ({target_row}, {target_col})."})

                # Trigger Phase 3 Navigation Logic
                if navigation_controller:
                    # Check if object following is active, potentially disable it? Or prioritize?
                    if self.object_detector and self.object_detector.auto_navigation:
                         logger.warning("Disabling object following to start map navigation.")
                         self.object_detector.set_auto_navigation(False)
                         self.telemetry["auto_navigation"] = False
                         emit('telemetry', self.telemetry) # Update UI

                    navigation_controller.set_target(target_row, target_col) # Assumes this method exists
                    logger.info("Navigation controller instructed to set target.")
                    emit('log', {'msg': 'Map navigation started.'})
                else:
                    logger.error("Navigation controller not available to handle 'navigate_to'.")
                    emit('log', {'msg': 'Error: Map navigation logic not available on server.'})

            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Invalid navigation target data received: {data}, Error: {e}")
                emit('log', {'msg': f'Error: Invalid navigation target data. {e}'})

        @self.socketio.on('clear_target')
        def handle_clear_target(data=None): # Ignore data if sent
            navigation_controller = getattr(self, 'navigation_controller', None)
            logger.info("Received clear target command via WebSocket.")
            emit('log', {'msg': "Map navigation target cleared."})

            # Trigger Phase 3 Clear Navigation Logic
            if navigation_controller:
                navigation_controller.clear_target() # Assumes this method exists
                logger.info("Navigation controller instructed to clear target.")
                emit('log', {'msg': 'Map navigation stopped.'})
            else:
                logger.warning("Navigation controller not available to handle 'clear_target'.")
        # --- End Phase 2 Handlers ---

    def _get_motion_state(self, forward, turn):
        """Convert motion values to a readable state (F, B, L, R, S)"""
        if abs(forward) < 0.1 and abs(turn) < 0.1: return "S"
        if abs(turn) > abs(forward): return "R" if turn > 0.1 else "L"
        else: return "F" if forward > 0.1 else "B"
        return "S" # Default stop

    def _telemetry_and_pose_thread(self):
        """Send periodic telemetry and robot pose updates to clients"""
        logger.info("Telemetry and pose update thread started.")
        battery_drain_counter = 0
        while True:
            # Adjust frequency as needed
            self.socketio.sleep(0.5) # Send updates twice per second

            # --- Phase 1: Robot Pose Update ---
            pose_data = None
            if self.robot_map:
                try:
                    # Add lock in RobotMap if updates become complex or errors occur
                    pose_data = {
                        'col': self.robot_map.pos_x,
                        'row': self.robot_map.pos_y,
                        'angle': self.robot_map.angle
                    }
                    self.socketio.emit('robot_update', pose_data)
                except Exception as e:
                    logger.error(f"Error reading/sending robot pose: {e}", exc_info=False) # Keep log brief
            # --- End Phase 1 ---

            # --- Telemetry Update ---
            battery_drain_counter += 1
            # Simulate battery drain every ~30 seconds (0.5s sleep * 60)
            if battery_drain_counter >= 60:
                 battery_drain_counter = 0
                 if self.telemetry["battery"] > 0:
                     self.telemetry["battery"] -= 1

            # Update other telemetry if needed (e.g., read sensors)
            # For now, only motion state is updated dynamically by 'control' handler

            # Send telemetry (includes motion, battery, auto-nav status)
            try:
                self.socketio.emit('telemetry', self.telemetry)
            except Exception as e:
                 logger.error(f"Error sending telemetry: {e}", exc_info=False)

            # Check if thread should stop? Not implemented, runs forever until server stops.

    def _camera_thread(self):
        """Background thread for camera capture and optional object detection"""
        logger.info("Starting camera capture thread")
        try:
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                 logger.error("!!!!!!!! Failed to open camera !!!!!!!!")
                 self.capture_running = False # Stop thread if camera fails
                 return # Exit thread

            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
            logger.info("Camera opened successfully.")

        except Exception as e:
             logger.error(f"!!!!!!!! Exception opening camera: {e} !!!!!!!!", exc_info=True)
             self.capture_running = False
             return

        while self.capture_running:
            try:
                success, frame = self.camera.read()
                if not success or frame is None:
                    logger.warning("Failed to read frame from camera, skipping cycle.")
                    time.sleep(0.1) # Wait a bit before retrying
                    continue

                # --- Object Detection ---
                current_boxes = [] # Boxes for this frame
                if self.detect_objects and self.object_detector:
                    try:
                        # Run detection. Navigation command sending is handled inside inference
                        # based on the detector's auto_navigation state.
                        current_boxes = self.object_detector.inference(frame)
                    except Exception as e:
                        logger.error(f"Error during object detection inference: {e}", exc_info=False)
                # --- End Object Detection ---

                # --- Update Shared Frame and Boxes ---
                with self.frame_lock:
                    self.latest_frame = frame.copy() # Store copy for streaming thread
                    self.latest_boxes = current_boxes # Store boxes found in this frame

                # Limit frame processing rate / yield CPU
                time.sleep(0.03) # Aim for ~30fps max processing rate

            except Exception as e:
                 logger.error(f"Error in camera thread loop: {e}", exc_info=True)
                 time.sleep(1) # Avoid spamming errors

        # Clean up camera when thread stops
        if self.camera:
            try:
                self.camera.release()
                logger.info("Camera released.")
            except Exception as e:
                 logger.error(f"Error releasing camera: {e}")
            self.camera = None

    def _draw_boxes(self, frame, boxes):
        """Draw detection boxes on the frame"""
        for box in boxes:
            try:
                x1, y1, x2, y2 = box['x1'], box['y1'], box['x2'], box['y2']
                label = f"{box['label']} {box['conf']:.2f}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            except Exception as e:
                 logger.warning(f"Error drawing box {box}: {e}") # Log briefly


    def _generate_frames(self):
        """Generator function for MJPEG video streaming"""
        logger.info("Video streaming started for a client.")
        while True:
            frame_to_send = None
            boxes_to_draw = []
            with self.frame_lock:
                if self.latest_frame is not None:
                    frame_to_send = self.latest_frame.copy()
                    if self.object_overlay:
                         boxes_to_draw = self.latest_boxes # Get boxes under lock

            if frame_to_send is None:
                #logger.debug("No frame available for streaming yet.") # Too noisy
                time.sleep(0.1) # Wait if no frame
                continue

            try:
                # Draw boxes if overlay enabled (outside lock to avoid holding it)
                if boxes_to_draw: # Check if list is not empty
                     self._draw_boxes(frame_to_send, boxes_to_draw)

                # Add status text (e.g., AUTO for object following)
                status_text = []
                if self.object_detector and self.object_detector.auto_navigation:
                    status_text.append("AUTO-FOLLOW")
                if self.navigation_controller and self.navigation_controller.is_navigating:
                     status_text.append("MAP-NAV") # Indicate map navigation active

                if status_text:
                    status_str = " | ".join(status_text)
                    cv2.putText(frame_to_send, status_str, (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2) # Red text

                # Encode frame as JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90] # Quality setting
                success, buffer = cv2.imencode('.jpg', frame_to_send, encode_param)

                if not success:
                     logger.warning("Failed to encode frame to JPEG")
                     time.sleep(0.1)
                     continue

                # Yield the frame in MJPEG format
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

            except Exception as e:
                 logger.error(f"Error generating video frame: {e}", exc_info=False)
                 # If a client disconnects, this loop might error, socketio usually handles it
                 # Break or implement better client disconnect detection if needed
                 time.sleep(0.5)

            # Control frame rate slightly (browser MJPEG handling also plays a role)
            time.sleep(0.03) # ~30 fps theoretical max yield rate

        logger.info("Video streaming stopped for a client.")


    def start(self):
        """Start the server, camera thread, and background tasks"""
        logger.info("Starting server components...")
        # Start camera capture thread
        self.capture_running = True
        self.capture_thread = Thread(target=self._camera_thread, daemon=True)
        self.capture_thread.start()

        # Start telemetry/pose thread (now started on first client connect)
        # self.socketio.start_background_task(self._telemetry_and_pose_thread)

        # Start the Flask-SocketIO server (blocking call)
        try:
            logger.info(f"Starting Flask-SocketIO server on 0.0.0.0:{self.http_port}")
            self.socketio.run(self.app, host='0.0.0.0', port=self.http_port,
                              debug=False, use_reloader=False) # Disable Flask debug/reloader
        except Exception as e:
            logger.error(f"!!!!!!!! Failed to start Flask-SocketIO server: {e} !!!!!!!!", exc_info=True)
        finally:
            logger.info("Flask-SocketIO server process ended.")
            # Ensure cleanup happens even if server fails to start or stops unexpectedly
            self.stop()

    def stop(self):
        """Stop the server threads and release resources"""
        if not self.capture_running: # Avoid multiple stop calls
             return
        logger.info("Stopping server components...")

        # Stop camera thread first
        self.capture_running = False
        if self.capture_thread and self.capture_thread.is_alive():
            logger.info("Waiting for camera thread to stop...")
            self.capture_thread.join(timeout=2.0) # Wait max 2 seconds
            if self.capture_thread.is_alive():
                 logger.warning("Camera thread did not stop gracefully.")
        # Release camera resource if join failed or thread wasn't running
        if self.camera:
            try:
                self.camera.release()
                logger.info("Camera released during stop.")
            except Exception as e:
                 logger.error(f"Error releasing camera during stop: {e}")
            self.camera = None

        # Note: Background tasks started with socketio.start_background_task
        # are typically managed by socketio itself upon shutdown.

        logger.info("Server components stopped.")

# Example of running just the server (for testing, normally run via main.py)
if __name__ == '__main__':
    print("Running server in standalone test mode.")
    # Create mock/dummy components for testing
    class MockMotorController:
        CMD_STOP = "S"
        def process_joystick_input(self, f, t): print(f"Mock Move: F={f}, T={t}")
        def emergency_stop(self): print("Mock Emergency Stop")
        def cleanup(self): print("Mock Motor Cleanup")
    class MockObjectDetector:
        auto_navigation = False
        def inference(self, frame): return [] # No detections
        def set_auto_navigation(self, enabled): self.auto_navigation=enabled; return enabled
    class MockRobotMap:
         pos_x, pos_y, angle = 10.0, 10.0, 90.0
         grid_size = 20
         def move(self, cmd): pass # Map doesn't move in this test
         def start(self): print("Mock Map Start")
         def stop(self): print("Mock Map Stop")

    # Instantiate server with mocks
    server = RCTankServer(
        motor_controller=MockMotorController(),
        object_detection=MockObjectDetector(),
        robot_map=MockRobotMap(),
        navigation_controller=None # No navigation logic in this test
    )

    # Basic signal handling for standalone test
    def handle_sigint_test(sig, frame):
        print("\nCtrl+C received, stopping server...")
        server.stop()
        # Allow server.start() to exit naturally after socketio shutdown
    signal.signal(signal.SIGINT, handle_sigint_test)

    server.start() # Run the server (blocking)
    print("Server has shut down.")