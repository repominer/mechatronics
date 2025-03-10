import time
import threading
import logging
from robot_visualizer import RobotVisualizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('visualizer_integration')

class VirtualRobotIntegration:
    """
    Integrates the motor controller with the robot visualizer.
    Acts as a proxy that receives commands and forwards them to both
    the physical robot (via motor controller) and virtual model.
    """
    
    def __init__(self, motor_controller=None, grid_size=20, use_visualization=True):
        """
        Initialize the integration between motor controller and visualizer
        
        Args:
            motor_controller: MotorController instance (optional)
            grid_size: Size of the visualization grid
            use_visualization: Whether to enable visualization
        """
        self.motor_controller = motor_controller
        self.use_visualization = use_visualization
        
        # Create the visualizer
        if use_visualization:
            self.visualizer = RobotVisualizer(
                grid_size=grid_size, 
                cell_size=30,
                start_x=grid_size / 2,
                start_y=grid_size / 2,
                start_angle=90  # Starting facing up (y+)
            )
        else:
            self.visualizer = None
        
        # Track if we're running
        self.running = False
        self.thread = None
        
        # Store original motor controller send_command
        self.original_send_command = None
        if motor_controller:
            self.original_send_command = motor_controller.send_command
        
        logger.info("Virtual robot integration initialized")
    
    def start(self):
        """Start the visualizer and integration"""
        if self.running:
            logger.warning("Integration already running")
            return
        
        # Start the visualizer if enabled
        if self.use_visualization and self.visualizer:
            self.visualizer.start()
        
        # Install hooks if we have a motor controller
        if self.motor_controller and self.original_send_command:
            self.motor_controller.send_command = self._send_command_hook
        
        # Mark as running
        self.running = True
        
        logger.info("Virtual robot integration started")
    
    def stop(self):
        """Stop the visualizer and integration"""
        if not self.running:
            return
        
        # Stop the visualizer if enabled
        if self.use_visualization and self.visualizer:
            self.visualizer.stop()
        
        # Restore original send_command if we hooked it
        if self.motor_controller and self.original_send_command:
            self.motor_controller.send_command = self.original_send_command
        
        # Mark as stopped
        self.running = False
        
        logger.info("Virtual robot integration stopped")
    
    def _send_command_hook(self, command, source="integration"):
        """
        Hook for motor controller's send_command that also updates visualization
        """
        # Call the original function
        result = self.original_send_command(command, source)
        
        # Update the visualization
        if self.running and self.use_visualization and self.visualizer:
            self.visualizer.apply_command(command)
        
        return result
    
    def apply_command(self, command, source="direct"):
        """
        Apply a command directly to the virtual model.
        Does NOT call the motor controller to avoid recursion.
        """
        # Send to virtual model only
        if self.running and self.use_visualization and self.visualizer:
            self.visualizer.apply_command(command)
            logger.debug(f"Applied command to visualization: {command} from {source}")
        
        return True


# Example of how to use with the motor controller
class MotorControllerMock:
    """Simple mock for testing without the actual motor controller"""
    CMD_FORWARD = "F"
    CMD_BACKWARD = "B"
    CMD_LEFT = "L"
    CMD_RIGHT = "R"
    CMD_STOP = "S"
    
    def send_command(self, command, source="mock"):
        print(f"[MOCK] Sending command: {command} from {source}")
        return True


if __name__ == "__main__":
    # Example usage with mock motor controller
    mock_controller = MotorControllerMock()
    integration = VirtualRobotIntegration(motor_controller=mock_controller)
    
    # Start the integration
    integration.start()
    
    try:
        # Example command sequence
        commands = [
            "F", "F", "F",   # Move forward 3 steps
            "R", "R",        # Turn right 20 degrees
            "F", "F",        # Move forward 2 steps
            "L", "L", "L",   # Turn left 30 degrees
            "F", "F", "F",   # Move forward 3 steps
            "S"              # Stop
        ]
        
        for cmd in commands:
            if integration.motor_controller:
                integration.motor_controller.send_command(cmd, "test")
            else:
                integration.apply_command(cmd, "test")
            time.sleep(0.5)  # Pause between commands
        
        # Keep the visualizer open
        print("Sequence complete. Press Ctrl+C to exit...")
        while integration.running:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        integration.stop()