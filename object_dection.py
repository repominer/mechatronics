from ultralytics import YOLO
import threading
import time
import Jetson.GPIO as GPIO

model = YOLO('yolov8s.pt')

class ObjectDetection:
    def __init__(self, enable_motors=True):
        # Initialize YOLO model properties
        self.last_command = None
        self.command_cooldown = 0.5  # Seconds between sending same command
        self.last_command_time = 0
        self.motors_enabled = enable_motors
        
        # Define L298N control pins (using your previous pin setup)
        # Motor A
        self.in1_pin = 23  # spi1_sck
        self.in2_pin = 21  # spi1_din
        # Motor B
        self.in3_pin = 19  # spi1_dout
        self.in4_pin = 26  # spi1_cs1
        
        self.motor_pins = [self.in1_pin, self.in2_pin, self.in3_pin, self.in4_pin]
        
        if self.motors_enabled:
            # Set up GPIO
            GPIO.setmode(GPIO.BOARD)
            for pin in self.motor_pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)  # Initialize all pins to LOW
            print("Motors initialized and ready")
        else:
            print("Motors disabled - running in detection-only mode")
    
    def send_motor_command(self, command):
        """Send command to motors via GPIO pins"""
        if not self.motors_enabled:
            print(f"Would send command to motors: {command}")
            return
        
        # Stop all motors first
        for pin in self.motor_pins:
            GPIO.output(pin, GPIO.LOW)
        
        # Execute the appropriate command
        if command == "F":  # Forward - both motors forward
            GPIO.output(self.in1_pin, GPIO.LOW)
            GPIO.output(self.in2_pin, GPIO.LOW)
            GPIO.output(self.in3_pin, GPIO.LOW)
            GPIO.output(self.in4_pin, GPIO.LOW)
            print("Motors: Moving Forward")
            
        elif command == "R":  # Left - right motor forward, left motor stopped/backward
            GPIO.output(self.in1_pin, GPIO.LOW)
            GPIO.output(self.in2_pin, GPIO.HIGH)  # Left motor backward
            GPIO.output(self.in3_pin, GPIO.HIGH)
            GPIO.output(self.in4_pin, GPIO.LOW)   # Right motor forward
            print("Motors: Turning Right")
            
        elif command == "L":  # Right - left motor forward, right motor stopped/backward
            GPIO.output(self.in1_pin, GPIO.HIGH)
            GPIO.output(self.in2_pin, GPIO.LOW)   # Left motor forward
            GPIO.output(self.in3_pin, GPIO.LOW)
            GPIO.output(self.in4_pin, GPIO.HIGH)  # Right motor backward
            print("Motors: Turning Left")
            
        elif command == "S":  # Stop - all motors stopped
            # All pins already set to LOW
            print("Motors: Stopped")
            
        return command
    
    def inference(self, img):
        """Run object detection and determine navigation commands."""
        results = model(img, verbose=False, conf=0.5, classes=0)
        
        boxes = []
        detected_command = None
        
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                xc, _, _, _ = map(int, box.xywh[0])
                
                # Determine navigation command based on object position
                if xc > 360:
                    detected_command = "R"  # Right
                elif xc < 280:
                    detected_command = "L"  # Left
                else:
                    detected_command = "F"  # Forward/Straight
                
                label = result.names[int(box.cls[0])]
                conf = float(box.conf[0])
                
                boxes.append({
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "label": label,
                    "conf": conf
                })
        
        # Send command if it's different or enough time has elapsed
        current_time = time.time()
        if detected_command and (self.last_command != detected_command or 
                              current_time - self.last_command_time > self.command_cooldown):
            self.send_motor_command(detected_command)
            self.last_command = detected_command
            self.last_command_time = current_time
        
        # If no objects detected, send stop command
        if not boxes and self.last_command != "S":
            self.send_motor_command("S")
            self.last_command = "S"
            self.last_command_time = current_time
            
        return boxes
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        if self.motors_enabled:
            # Stop all motors
            for pin in self.motor_pins:
                GPIO.output(pin, GPIO.LOW)
            # Small delay to ensure motors stop
            time.sleep(0.1)
            # Clean up GPIO
            GPIO.cleanup()
            print("Motors stopped and GPIO cleaned up")
        else:
            print("No cleanup needed (motors were disabled)")

# Example usage:
# detector = ObjectDetection(enable_motors=True)
# try:
#     # Your camera capture code here
#     # while True:
#     #     frame = camera.read()
#     #     boxes = detector.inference(frame)
# except KeyboardInterrupt:
#     detector.cleanup()