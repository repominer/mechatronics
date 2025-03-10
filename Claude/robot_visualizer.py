import pygame
import math
import sys
import time
import threading
from queue import Queue
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('robot_visualizer')

class RobotVisualizer:
    """
    Virtual model of the robot on a 20x20 grid using Pygame.
    The robot is represented as an arrow pointing in its current direction.
    """
    
    # Define movement constants to match motor controller
    MOVE_FORWARD = "F"
    MOVE_BACKWARD = "B"
    TURN_LEFT = "L"
    TURN_RIGHT = "R"
    STOP = "S"
    
    def __init__(self, grid_size=20, cell_size=30, 
                 start_x=10, start_y=10, start_angle=90):
        """
        Initialize the robot visualizer
        
        Args:
            grid_size: Size of the grid (grid_size x grid_size)
            cell_size: Size of each cell in pixels
            start_x: Starting X position (0-based)
            start_y: Starting Y position (0-based)
            start_angle: Starting angle in degrees (0 = right, 90 = up)
        """
        self.grid_size = grid_size
        self.cell_size = cell_size
        self.window_size = grid_size * cell_size
        
        # Robot state
        self.robot_x = float(start_x)
        self.robot_y = float(start_y)
        self.robot_angle = start_angle  # In degrees, 0 = right, 90 = up
        self.move_speed = 0.1  # Grid cells per movement
        self.turn_speed = 10   # Degrees per turn
        
        # Movement history for drawing trail
        self.movement_history = [(start_x, start_y)]
        self.max_history = 100  # Maximum number of points to keep in history
        
        # Command queue and thread control
        self.command_queue = Queue()
        self.running = False
        self.render_thread = None
        self.update_thread = None
        
        # Display info
        self.font = None
        self.screen = None
        
        # Initialize Pygame
        pygame.init()
        
        logger.info(f"Initialized robot visualizer on {grid_size}x{grid_size} grid")
    
    def _init_display(self):
        """Initialize the Pygame display"""
        pygame.display.init()
        self.screen = pygame.display.set_mode((self.window_size, self.window_size + 100))
        pygame.display.set_caption("Robot Visualizer")
        self.font = pygame.font.SysFont(None, 24)
        
    def _process_events(self):
        """Process Pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            # Handle keyboard input
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_UP or event.key == pygame.K_w:
                    self.command_queue.put(self.MOVE_FORWARD)
                elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                    self.command_queue.put(self.MOVE_BACKWARD)
                elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                    self.command_queue.put(self.TURN_LEFT)
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                    self.command_queue.put(self.TURN_RIGHT)
                elif event.key == pygame.K_SPACE:
                    self.command_queue.put(self.STOP)
                elif event.key == pygame.K_r:
                    # Reset robot position
                    self.robot_x = self.grid_size / 2
                    self.robot_y = self.grid_size / 2
                    self.robot_angle = 90
                    self.movement_history = [(self.robot_x, self.robot_y)]
        
        return True
    
    def _draw_grid(self):
        """Draw the grid on the screen"""
        # Fill the background
        self.screen.fill((0, 0, 0))
        
        # Draw grid lines
        for i in range(self.grid_size + 1):
            # Vertical lines
            pygame.draw.line(
                self.screen, 
                (50, 50, 50), 
                (i * self.cell_size, 0), 
                (i * self.cell_size, self.window_size)
            )
            
            # Horizontal lines
            pygame.draw.line(
                self.screen, 
                (50, 50, 50), 
                (0, i * self.cell_size), 
                (self.window_size, i * self.cell_size)
            )
        
        # Draw coordinate labels
        for i in range(0, self.grid_size):
            # X-axis labels
            x_label = self.font.render(str(i), True, (200, 200, 200))
            self.screen.blit(x_label, (i * self.cell_size + 5, 5))
            
            # Y-axis labels
            y_label = self.font.render(str(i), True, (200, 200, 200))
            self.screen.blit(y_label, (5, i * self.cell_size + 5))
    
    def _draw_movement_trail(self):
        """Draw the movement history trail"""
        if len(self.movement_history) < 2:
            return
        
        points = []
        for x, y in self.movement_history:
            screen_x = x * self.cell_size
            screen_y = y * self.cell_size
            points.append((screen_x, screen_y))
        
        # Draw trail as connected line segments
        pygame.draw.lines(self.screen, (0, 150, 255), False, points, 2)
    
    def _draw_robot(self):
        """Draw the robot as an arrow"""
        # Robot center in screen coordinates
        center_x = self.robot_x * self.cell_size
        center_y = self.robot_y * self.cell_size
        
        # Calculate arrow points
        angle_rad = math.radians(self.robot_angle)
        
        # Arrow size (adjust as needed)
        arrow_size = self.cell_size * 0.4
        
        # Calculate arrow points
        # Tip of the arrow
        tip_x = center_x + arrow_size * math.sin(angle_rad)
        tip_y = center_y - arrow_size * math.cos(angle_rad)
        
        # Base of the arrow
        base_x = center_x - arrow_size * math.sin(angle_rad)
        base_y = center_y + arrow_size * math.cos(angle_rad)
        
        # Left wing
        left_angle = angle_rad + math.radians(135)
        left_x = tip_x + arrow_size * 0.5 * math.sin(left_angle)
        left_y = tip_y - arrow_size * 0.5 * math.cos(left_angle)
        
        # Right wing
        right_angle = angle_rad - math.radians(135)
        right_x = tip_x + arrow_size * 0.5 * math.sin(right_angle)
        right_y = tip_y - arrow_size * 0.5 * math.cos(right_angle)
        
        # Draw the arrow
        pygame.draw.polygon(
            self.screen, 
            (255, 0, 0), 
            [(tip_x, tip_y), (left_x, left_y), (base_x, base_y), (right_x, right_y)],
            0
        )
        
        # Draw a circle at the robot's center
        pygame.draw.circle(self.screen, (255, 255, 0), (int(center_x), int(center_y)), 5)
    
    def _draw_status(self):
        """Draw status information at the bottom of the screen"""
        # Draw a status bar at the bottom
        pygame.draw.rect(
            self.screen, 
            (30, 30, 30), 
            (0, self.window_size, self.window_size, 100)
        )
        
        # Draw position and angle information
        pos_text = f"Position: ({self.robot_x:.2f}, {self.robot_y:.2f})"
        angle_text = f"Angle: {self.robot_angle:.2f}°"
        
        pos_surface = self.font.render(pos_text, True, (255, 255, 255))
        angle_surface = self.font.render(angle_text, True, (255, 255, 255))
        
        controls_text = "Controls: Arrow keys/WASD to move, Space to stop, R to reset"
        controls_surface = self.font.render(controls_text, True, (200, 200, 200))
        
        self.screen.blit(pos_surface, (10, self.window_size + 10))
        self.screen.blit(angle_surface, (10, self.window_size + 40))
        self.screen.blit(controls_surface, (10, self.window_size + 70))
    
    def _render_loop(self):
        """Main rendering loop"""
        clock = pygame.time.Clock()
        self._init_display()
        
        while self.running:
            # Process events
            if not self._process_events():
                self.running = False
                break
            
            # Draw everything
            self._draw_grid()
            self._draw_movement_trail()
            self._draw_robot()
            self._draw_status()
            
            # Update the display
            pygame.display.flip()
            
            # Cap the frame rate
            clock.tick(60)
    
    def _update_loop(self):
        """Update loop for processing movement commands"""
        while self.running:
            # Check if there's a command in the queue
            try:
                command = self.command_queue.get(timeout=0.1)
                self._process_command(command)
                
                # Add current position to movement history
                self.movement_history.append((self.robot_x, self.robot_y))
                
                # Trim history if too long
                if len(self.movement_history) > self.max_history:
                    self.movement_history = self.movement_history[-self.max_history:]
                
                # Small delay to make movements visible
                time.sleep(0.1)
            except:
                # No command available, just continue
                pass
    
    def _process_command(self, command):
        """Process a movement command"""
        logger.debug(f"Processing command: {command}")
        
        if command == self.MOVE_FORWARD:
            # Move forward in the direction of the current angle
            angle_rad = math.radians(self.robot_angle)
            self.robot_x += self.move_speed * math.sin(angle_rad)
            self.robot_y -= self.move_speed * math.cos(angle_rad)
            
        elif command == self.MOVE_BACKWARD:
            # Move backward in the opposite direction of the current angle
            angle_rad = math.radians(self.robot_angle)
            self.robot_x -= self.move_speed * math.sin(angle_rad)
            self.robot_y += self.move_speed * math.cos(angle_rad)
            
        elif command == self.TURN_LEFT:
            # Turn left (counter-clockwise)
            self.robot_angle = (self.robot_angle + self.turn_speed) % 360
            
        elif command == self.TURN_RIGHT:
            # Turn right (clockwise)
            self.robot_angle = (self.robot_angle - self.turn_speed) % 360
        
        # Ensure robot stays within grid bounds
        self.robot_x = max(0, min(self.robot_x, self.grid_size - 1))
        self.robot_y = max(0, min(self.robot_y, self.grid_size - 1))
    
    def apply_command(self, command):
        """
        Apply a movement command to the robot
        
        Args:
            command: One of the movement constants (F, B, L, R, S)
        """
        if not self.running:
            logger.warning("Cannot apply command: Visualizer not running")
            return
        
        self.command_queue.put(command)
    
    def start(self):
        """Start the visualizer"""
        if self.running:
            logger.warning("Visualizer already running")
            return
        
        self.running = True
        
        # Start render thread
        self.render_thread = threading.Thread(target=self._render_loop)
        self.render_thread.daemon = True
        self.render_thread.start()
        
        # Start update thread
        self.update_thread = threading.Thread(target=self._update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        logger.info("Robot visualizer started")
    
    def stop(self):
        """Stop the visualizer"""
        self.running = False
        
        if self.render_thread:
            self.render_thread.join(timeout=1)
        
        if self.update_thread:
            self.update_thread.join(timeout=1)
        
        pygame.quit()
        logger.info("Robot visualizer stopped")


# Example standalone usage
if __name__ == "__main__":
    visualizer = RobotVisualizer()
    visualizer.start()
    
    try:
        # Keep main thread alive
        while visualizer.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        visualizer.stop()