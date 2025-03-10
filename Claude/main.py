#!/usr/bin/env python3
"""
RC Tank Control Main Application with Robot Map

This script initializes all components and starts the server:
1. Motor Controller - handles GPIO or Arduino control
2. Object Detection - processes camera frames to detect objects
3. Robot Map - shows robot position on a grid
4. Web Server - provides HTTP and WebSocket interfaces
"""

import os
import sys
import logging
import argparse
import signal
import time
import shutil
import threading

# Local imports
from motor_controller import MotorController
from object_detection import ObjectDetection
from server import RCTankServer
from robot_map import RobotMap

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('main')

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='RC Tank Control with Map')
    
    # Motor control options
    parser.add_argument('--control-mode', choices=['gpio', 'arduino'], 
                        default='gpio',
                        help='Motor control mode: direct GPIO or Arduino serial')
    parser.add_argument('--arduino-port',
                        default='/dev/ttyACM0',
                        help='Arduino serial port (if using arduino mode)')
    parser.add_argument('--baud-rate', type=int,
                        default=9600,
                        help='Arduino serial baud rate')
    parser.add_argument('--disable-motors', action='store_true',
                        help='Disable physical motor control (simulation mode)')
    
    # Server options
    parser.add_argument('--port', type=int,
                        default=8000,
                        help='HTTP and WebSocket server port')
    
    # Object detection options
    parser.add_argument('--model', default='yolov8s.pt',
                        help='Path to YOLO model file')
    parser.add_argument('--confidence', type=float,
                        default=0.5,
                        help='Detection confidence threshold')
    parser.add_argument('--auto-navigation', action='store_true',
                        help='Enable autonomous navigation at startup')
    
    # Map options
    parser.add_argument('--disable-map', action='store_true',
                        help='Disable robot map visualization')
    parser.add_argument('--grid-size', type=int,
                        default=20,
                        help='Size of the map grid')
    
    # Debug options
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')
    
    return parser.parse_args()

def setup_static_files():
    """Create static folder and copy HTML/CSS/JS files"""
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    return static_dir

def handle_signals(server, robot_map):
    """Set up signal handlers for graceful shutdown"""
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        server.stop()
        if robot_map:
            robot_map.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def create_motor_controller_with_map(args, robot_map):
    """Create a motor controller that updates the map"""
    # Create the actual motor controller
    motor_controller = MotorController(
        enable_motors=not args.disable_motors
    )
    
    # Store the original send_command method
    original_send_command = motor_controller.send_command
    
    # Define a new send_command method that also updates the map
    def send_command_with_map(command, source="main"):
        # First call the original method
        result = original_send_command(command, source)
        
        # Then update the map if available
        if robot_map:
            robot_map.move(command)
        
        return result
    
    # Replace the method
    motor_controller.send_command = send_command_with_map
    
    return motor_controller

def main():
    """Main application entry point"""
    args = parse_arguments()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("Initializing RC Tank Control system with robot map")
    
    # Set up static files directory for web server
    static_dir = setup_static_files()
    
    # Initialize the robot map if enabled
    robot_map = None
    if not args.disable_map:
        robot_map = RobotMap(grid_size=args.grid_size)
        robot_map.start()
        logger.info("Robot map visualization started")
    
    # Create motor controller with map integration
    motor_controller = create_motor_controller_with_map(args, robot_map)
    
    # Initialize object detection
    object_detector = ObjectDetection(
        motor_controller=motor_controller,
        model_path=args.model,
        confidence=args.confidence,
        auto_navigation=args.auto_navigation
    )
    
    # Initialize the server
    server = RCTankServer(
        motor_controller=motor_controller,
        object_detection=object_detector,
        http_port=args.port,
        static_folder=static_dir
    )
    
    # Set up signal handlers
    handle_signals(server, robot_map)
    
    try:
        # Start the server (this is a blocking call)
        logger.info("Starting server...")
        server.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        # Clean up resources
        logger.info("Cleaning up resources...")
        server.stop()
        if robot_map:
            robot_map.stop()
        motor_controller.cleanup()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    main()