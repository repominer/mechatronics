import time
import logging
from threading import Lock

# Try to import YOLO, but allow fallback for testing environments
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("WARNING: YOLO not available - running with detection simulation")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('object_detection')

class ObjectDetection:
    """
    Object detection class that identifies objects and determines appropriate
    navigation commands based on their position.
    """
    
    def __init__(self, motor_controller=None, model_path='yolov8s.pt', 
                 confidence=0.5, classes=[0], auto_navigation=False):
        """
        Initialize the object detection module
        
        Args:
            motor_controller: MotorController instance for sending commands
            model_path: Path to the YOLO model
            confidence: Confidence threshold for detection
            classes: Class IDs to detect (0=person by default)
            auto_navigation: Whether to automatically send navigation commands
        """
        self.motor_controller = motor_controller
        self.model_path = model_path
        self.confidence = confidence
        self.classes = classes
        self.auto_navigation = auto_navigation
        
        # Model initialization
        if YOLO_AVAILABLE:
            try:
                self.model = YOLO(model_path)
                logger.info(f"Loaded YOLO model from {model_path}")
            except Exception as e:
                logger.error(f"Error loading YOLO model: {e}")
                self.model = None
        else:
            self.model = None
            logger.warning("YOLO not available - object detection disabled")
        
        # Detection parameters
        self.image_width = 640  # Default frame width
        self.image_height = 640  # Default frame height
        self.center_threshold_left = int(self.image_width * 0.4)  # Left boundary of center zone
        self.center_threshold_right = int(self.image_width * 0.6)  # Right boundary of center zone
    
    def inference(self, frame, navigate=None):
        """
        Run object detection on a frame and determine navigation commands
        
        Args:
            frame: The image frame to process
            navigate: Override auto_navigation setting for this call
        
        Returns:
            boxes: List of detected objects with coordinates and labels
        """
        # Use navigate parameter if provided, otherwise use instance setting
        should_navigate = navigate if navigate is not None else self.auto_navigation
        
        # If no model or frame, return empty results
        if self.model is None or frame is None:
            return []
        
        # Update frame dimensions if they changed
        h, w = frame.shape[:2]
        if w != self.image_width or h != self.image_height:
            self.image_width = w
            self.image_height = h
            self.center_threshold_left = int(w * 0.4)
            self.center_threshold_right = int(w * 0.6)
        
        # Run inference on the frame
        try:
            results = self.model(frame, verbose=False, conf=self.confidence, classes=self.classes)
        except Exception as e:
            logger.error(f"Error during inference: {e}")
            return []
        
        boxes = []
        detected_command = None
        
        # Process detection results
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                box_data = box.xywh[0]  # x-center, y-center, width, height
                xc = int(box_data[0])
                
                # Determine navigation command based on object position
                if xc > self.center_threshold_right:
                    detected_command = self.motor_controller.CMD_LEFT
                elif xc < self.center_threshold_left:
                    detected_command = self.motor_controller.CMD_RIGHT
                else:
                    detected_command = self.motor_controller.CMD_STOP
                
                label = result.names[int(box.cls[0])]
                conf = float(box.conf[0])
                
                # Add detected box to results
                boxes.append({
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "label": label,
                    "conf": conf
                })
        
        # Send navigation command if auto-navigation is enabled
        if should_navigate and self.motor_controller:
            if detected_command:
                self.motor_controller.send_command(detected_command, "detection")
            elif boxes and self.motor_controller:
                # If no command determined but objects detected, stop
                self.motor_controller.send_command(self.motor_controller.CMD_STOP, "detection")
        
        return boxes
    
    def set_auto_navigation(self, enabled):
        """Enable or disable automatic navigation based on detections"""
        self.auto_navigation = enabled
        logger.info(f"Auto navigation {'enabled' if enabled else 'disabled'}")
        return self.auto_navigation