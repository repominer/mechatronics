#!/usr/bin/env python3
"""
Arduino L298N Raw Serial Control
This script uses direct file operations to communicate with the Arduino,
bypassing all serial drivers and utilities that might cause issues on Jetson.

Commands:
- F: Forward
- B: Backward
- L: Left
- R: Right
- S: Stop
"""

import os
import sys
import glob
import time
import fcntl
import termios
import array

class RawSerialController:
    def __init__(self, port_path):
        """
        Initialize using direct file operations.
        
        Args:
            port_path (str): Serial port path (e.g., '/dev/ttyACM0')
        """
        self.port_path = port_path
        self.port_fd = None
        
        # Check if port exists
        if not os.path.exists(port_path):
            print(f"Error: Port {port_path} does not exist")
            sys.exit(1)
        
        try:
            # Open the port in write-only mode
            self.port_fd = os.open(port_path, os.O_RDWR | os.O_NOCTTY)
            
            # Try to set some basic parameters (may or may not work)
            try:
                # Get current attributes
                attrs = termios.tcgetattr(self.port_fd)
                
                # Set baud rate (B9600 = 9600 baud)
                attrs[4] = attrs[5] = termios.B9600
                
                # 8N1 (8 bits, no parity, 1 stop bit)
                attrs[2] = attrs[2] & ~termios.PARENB & ~termios.CSTOPB | termios.CS8
                
                # No flow control
                attrs[2] = attrs[2] & ~termios.CRTSCTS
                
                # Apply settings
                termios.tcsetattr(self.port_fd, termios.TCSANOW, attrs)
                
                # Flush any pending data
                termios.tcflush(self.port_fd, termios.TCIOFLUSH)
                
                print(f"Successfully configured port {port_path}")
            except Exception as e:
                # If configuration fails, continue anyway with default settings
                print(f"Warning: Could not fully configure port: {e}")
                print("Will attempt to communicate with default settings")
        except Exception as e:
            print(f"Error opening port: {e}")
            sys.exit(1)
    
    def send_command(self, command):
        """
        Send a command character to the Arduino.
        
        Args:
            command (str): One of 'F', 'B', 'L', 'R', 'S'
        """
        if command not in ['F', 'B', 'L', 'R', 'S']:
            print(f"Invalid command: {command}")
            return False
        
        try:
            # Send the command
            bytes_written = os.write(self.port_fd, command.encode())
            
            if bytes_written == 1:
                print(f"Sent command: {command}")
                
                # Optional: Try to read response
                try:
                    # Wait for Arduino to respond
                    time.sleep(0.1)
                    
                    # Read response
                    response_buffer = bytearray(100)
                    bytes_read = os.read(self.port_fd, 100)
                    if bytes_read:
                        response = bytes_read.decode(errors='ignore').strip()
                        print(f"Arduino response: {response}")
                except Exception as e:
                    # Don't fail if we can't read response
                    pass
                
                return True
            else:
                print(f"Failed to send command: wrote {bytes_written} bytes instead of 1")
                return False
        except Exception as e:
            print(f"Error sending command: {e}")
            return False
    
    def close(self):
        """Close the serial port."""
        if self.port_fd is not None:
            os.close(self.port_fd)
            print("Serial port closed")

def find_arduino_port():
    """
    Find the Arduino port.
    
    Returns:
        str: The port name if found, None otherwise
    """
    # Check common locations for Arduino on Linux/Jetson
    common_ports = [
        '/dev/ttyACM0',  # Most common for Arduino Uno/Mega on Linux
        '/dev/ttyUSB0'   # Common for Arduino with FTDI or CH340 chips
    ]
    
    for port in common_ports:
        if os.path.exists(port):
            print(f"Found port at: {port}")
            return port
    
    # If not found, search using patterns
    acm_ports = glob.glob('/dev/ttyACM*')
    if acm_ports:
        print(f"Found ACM port: {acm_ports[0]}")
        return acm_ports[0]
        
    usb_ports = glob.glob('/dev/ttyUSB*')
    if usb_ports:
        print(f"Found USB port: {usb_ports[0]}")
        return usb_ports[0]
    
    print("No suitable ports found")
    return None

def interactive_control(controller):
    """
    Interactive control mode.
    
    Args:
        controller (RawSerialController): The controller instance
    """
    print("\nRaw Serial Control - Interactive Mode")
    print("-------------------------------------")
    print("Commands:")
    print("  F: Forward")
    print("  B: Backward")
    print("  L: Left")
    print("  R: Right")
    print("  S: Stop")
    print("  Q: Quit")
    print("-------------------------------------")
    
    while True:
        command = input("Enter command (F/B/L/R/S/Q): ").upper()
        if command == 'Q':
            # Send stop command before quitting
            controller.send_command('S')
            break
        elif command in ['F', 'B', 'L', 'R', 'S']:
            controller.send_command(command)
        else:
            print(f"Unknown command: {command}")

def check_permissions(port):
    """Check and fix permissions if needed"""
    try:
        # Try to make the port accessible
        os.system(f"sudo chmod 666 {port}")
        print(f"Set permissions on {port}")
        return True
    except:
        return False

def main():
    # Check if running as root (needed for some serial port operations)
    if os.geteuid() != 0:
        print("Warning: This script may require root privileges.")
        print("Consider running with: sudo python3 raw_serial_control.py")
    
    # Get port from command line or find automatically
    if len(sys.argv) > 1 and sys.argv[1].startswith('/dev/'):
        port = sys.argv[1]
    else:
        port = find_arduino_port()
        
    if not port:
        print("No port specified or found. Exiting.")
        return
    
    # Ensure permissions are correct
    check_permissions(port)
    
    try:
        controller = RawSerialController(port)
        
        # Check if a command was specified in arguments
        if len(sys.argv) > 1 and sys.argv[-1].upper() in ['F', 'B', 'L', 'R', 'S']:
            # Single command mode
            controller.send_command(sys.argv[-1].upper())
            controller.close()
        else:
            # Interactive mode
            interactive_control(controller)
            controller.close()
            
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
        # Send stop command when exiting
        if 'controller' in locals():
            controller.send_command('S')
            controller.close()
    except Exception as e:
        print(f"Unexpected error: {e}")
        if 'controller' in locals():
            controller.close()

if __name__ == "__main__":
    main()