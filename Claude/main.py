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
import shutil # Although imported previously, wasn't used. Keep for now.
import threading

# Local imports
from motor_controller import MotorController
from object_detection import ObjectDetection
from server import RCTankServer # Assuming server.py has the updated __init__
from robot_map import RobotMap
from navigation import NavigationController

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
    """Create static folder (if needed) and return path"""
    # In this version, we just return the path, assuming files exist.
    # The server class handles os.makedirs.
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    return static_dir

def handle_signals(server, robot_map):
    """Set up signal handlers for graceful shutdown"""
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        # Stop server first (which might rely on other components briefly)
        server.stop() # Server stop should handle its threads (like camera)

        # Stop map display thread
        if robot_map:
            robot_map.stop()

        # Motor controller cleanup happens in finally block of main

        sys.exit(0) # Exit gracefully

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def create_motor_controller_with_map(args, robot_map):
    """Create a motor controller that updates the map"""
    # Create the actual motor controller
    motor_controller = MotorController(
        enable_motors=not args.disable_motors
        # Note: control_mode, arduino_port etc are NOT passed here
        # The provided MotorController only uses GPIO currently.
    )

    # Store the original send_command method if map is enabled
    if robot_map:
        original_send_command = motor_controller.send_command

        # Define a new send_command method that also updates the map
        def send_command_with_map(command, source="main"):
            # First call the original method
            success = original_send_command(command, source)

            # Then update the map if command was likely processed
            # (We update even if rate-limited, map shows intended state)
            # Or maybe only update if success? Let's update regardless for now.
            robot_map.move(command) # Update map based on command intention

            return success

        # Replace the method
        motor_controller.send_command = send_command_with_map
        logger.info("Motor controller wrapped to update robot map.")

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
        try:
            robot_map = RobotMap(grid_size=args.grid_size)
            robot_map.start() # Start the display thread
            logger.info("Robot map visualization started")
        except Exception as e:
            logger.error(f"Failed to initialize or start Robot Map: {e}. Disabling map.")
            robot_map = None # Ensure it's None if start fails
    else:
        logger.info("Robot map visualization disabled by command line flag.")


    # Create motor controller with map integration (wrapper applied if map exists)
    motor_controller = create_motor_controller_with_map(args, robot_map)
    navigation_controller = None
    if motor_controller and robot_map: # Check dependencies are available
        try:
            navigation_controller = NavigationController(motor_controller, robot_map)
            logger.info("Navigation controller initialized.")
        except ImportError:
            logger.error("Failed to import NavigationController (navigation.py?). Map navigation will be disabled.")
        except Exception as e:
            logger.error(f"Failed to initialize NavigationController: {e}. Map navigation will be disabled.", exc_info=True)
    else:
         logger.warning("Motor controller or robot map missing, navigation controller disabled.")


    # Initialize object detection
    object_detector = ObjectDetection(
        motor_controller=motor_controller,
        model_path=args.model,
        confidence=args.confidence,
        auto_navigation=args.auto_navigation # Initial state from args
    )

    # Initialize the server **(MODIFIED LINE FOR PHASE 1)**
    server = RCTankServer(
        motor_controller=motor_controller,
        object_detection=object_detector,
        robot_map=robot_map,  # Pass the robot_map instance here
        navigation_controller=navigation_controller,
        http_port=args.port,
        static_folder=static_dir
    )

    # Set up signal handlers (pass server and map for cleanup)
    handle_signals(server, robot_map)

    try:
        # Start the server (this is a blocking call until shutdown)
        logger.info(f"Starting server on port {args.port}...")
        # Server's start method now handles its own threads and the Flask/SocketIO run
        server.start()

    except Exception as e:
        # Catch potential errors during server startup or runtime if not caught by server.start()
        logger.error(f"An error occurred in the main execution: {e}", exc_info=True)
    finally:
        # Clean up resources (some cleanup might be redundant if signal handler ran)
        logger.info("Performing final cleanup...")

        # Server stop should have been called by signal handler or server.start() finally block
        # server.stop() # Call again just in case? Usually handled by signal/finally in start()

        # Map stop should have been called by signal handler
        # if robot_map and robot_map.running:
        #    robot_map.stop()

        # Ensure motor controller cleanup is always called
        if motor_controller:
            motor_controller.cleanup()

        logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()