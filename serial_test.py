# test_arduino.py
import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

try:
    import serial
    print("Serial module info:", serial)
    print("Serial module path:", serial.__file__)
except ImportError as e:
    print(f"Failed to import serial: {e}")
    
# Try to list available serial ports
try:
    import serial.tools.list_ports
    ports = list(serial.tools.list_ports.comports())
    print("\nAvailable serial ports:")
    for port in ports:
        print(f"  {port.device} - {port.description}")
except Exception as e:
    print(f"Error listing ports: {e}")