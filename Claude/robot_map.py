import pygame
import math
import threading
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('robot_map')

class RobotMap:
    """Simple 2D map that tracks robot position and orientation"""
    
    # Command constants
    CMD_FORWARD = "F"
    CMD_BACKWARD = "B"
    CMD_LEFT = "L"
    CMD_RIGHT = "R"
    CMD_STOP = "S"
    
    def __init__(self, grid_size=20, cell_size=30):
        """Initialize the robot map visualization"""
        # Grid parameters
        self.grid_size = grid_size
        self.cell_size = cell_size
        self.window_width = grid_size * cell_size
        self.window_height = grid_size * cell_size + 40  # Extra space for info
        
        # Robot state
        self.pos_x = grid_size / 2  # Start in the middle (grid_size/2, grid_size/2)
        self.pos_y = grid_size / 2
        self.angle = 90  # 0 = right, 90 = up, 180 = left, 270 = down
        
        # Movement parameters
        self.move_distance = 0.2  # Grid cells per movement command
        self.turn_angle = 15     # Degrees per turn command
        
        # Track path history
        self.path = [(self.pos_x, self.pos_y)]
        self.max_path_length = 100
        
        # Pygame elements
        pygame.init()
        self.screen = None
        self.font = None
        self.clock = pygame.time.Clock()
        
        # Thread control
        self.running = False
        self.display_thread = None
        
        logger.info(f"Robot map initialized with grid size {grid_size}x{grid_size}")
    
    def _setup_display(self):
        """Set up the pygame display"""
        self.screen = pygame.display.set_mode((self.window_width, self.window_height))
        pygame.display.set_caption("Robot Map")
        self.font = pygame.font.SysFont(None, 24)
    
    def _handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_UP:
                    self.move(self.CMD_FORWARD)
                elif event.key == pygame.K_DOWN:
                    self.move(self.CMD_BACKWARD)
                elif event.key == pygame.K_LEFT:
                    self.move(self.CMD_LEFT)
                elif event.key == pygame.K_RIGHT:
                    self.move(self.CMD_RIGHT)
                elif event.key == pygame.K_SPACE:
                    self.move(self.CMD_STOP)
                elif event.key == pygame.K_r:  # Reset position
                    self.pos_x = self.grid_size / 2
                    self.pos_y = self.grid_size / 2
                    self.angle = 90
                    self.path = [(self.pos_x, self.pos_y)]
    
    def _draw_grid(self):
        """Draw the grid"""
        # Fill background
        self.screen.fill((0, 0, 0))
        
        # Draw grid lines
        grid_color = (40, 40, 40)
        for i in range(self.grid_size + 1):
            # Horizontal lines
            pygame.draw.line(
                self.screen, 
                grid_color, 
                (0, i * self.cell_size), 
                (self.window_width, i * self.cell_size)
            )
            
            # Vertical lines
            pygame.draw.line(
                self.screen, 
                grid_color, 
                (i * self.cell_size, 0), 
                (i * self.cell_size, self.window_height - 40)
            )
    
    def _draw_robot(self):
        """Draw the robot as an arrow"""
        # Convert grid coordinates to screen coordinates
        center_x = int(self.pos_x * self.cell_size)
        center_y = int(self.pos_y * self.cell_size)
        
        # Draw a circle at the robot's position
        pygame.draw.circle(self.screen, (255, 255, 0), (center_x, center_y), 8)
        
        # Draw an arrow to show the direction
        angle_rad = math.radians(self.angle)
        arrow_length = self.cell_size * 0.4
        
        end_x = center_x + arrow_length * math.cos(angle_rad)
        end_y = center_y - arrow_length * math.sin(angle_rad)
        
        # Draw the arrow line
        pygame.draw.line(self.screen, (255, 0, 0), (center_x, center_y), (end_x, end_y), 3)
        
        # Draw arrow head
        head_size = 6
        pygame.draw.polygon(
            self.screen,
            (255, 0, 0),
            [
                (end_x, end_y),
                (end_x - head_size * math.cos(angle_rad - math.pi/6), 
                 end_y + head_size * math.sin(angle_rad - math.pi/6)),
                (end_x - head_size * math.cos(angle_rad + math.pi/6), 
                 end_y + head_size * math.sin(angle_rad + math.pi/6)),
            ]
        )
    
    def _draw_path(self):
        """Draw the robot's path"""
        if len(self.path) < 2:
            return
            
        # Convert path points to screen coordinates
        screen_points = [(x * self.cell_size, y * self.cell_size) for x, y in self.path]
        
        # Draw a line connecting the points
        pygame.draw.lines(self.screen, (0, 128, 255), False, screen_points, 2)
    
    def _draw_info(self):
        """Draw position and orientation information"""
        # Draw a background bar for text
        pygame.draw.rect(
            self.screen,
            (20, 20, 20),
            (0, self.window_height - 40, self.window_width, 40)
        )
        
        # Draw position text
        pos_text = f"Position: ({self.pos_x:.1f}, {self.pos_y:.1f})  Angle: {self.angle:.1f}°"
        text_surface = self.font.render(pos_text, True, (200, 200, 200))
        self.screen.blit(text_surface, (10, self.window_height - 30))
    
    def _display_loop(self):
        """Main display loop"""
        self._setup_display()
        
        while self.running:
            self._handle_events()
            
            self._draw_grid()
            self._draw_path()
            self._draw_robot()
            self._draw_info()
            
            pygame.display.flip()
            self.clock.tick(30)  # 30 FPS
    
    def start(self):
        """Start the map display"""
        if self.running:
            logger.warning("Map display already running")
            return
            
        self.running = True
        self.display_thread = threading.Thread(target=self._display_loop)
        self.display_thread.daemon = True
        self.display_thread.start()
        
        logger.info("Robot map display started")
    
    def stop(self):
        """Stop the map display"""
        self.running = False
        
        if self.display_thread:
            self.display_thread.join(timeout=1)
            
        pygame.quit()
        logger.info("Robot map display stopped")
    
    def move(self, command):
        """
        Move the robot according to the command
        
        Args:
            command: One of the CMD_* constants
        """
        # Skip if stop command
        if command == self.CMD_STOP:
            return
            
        # Process movement
        if command == self.CMD_FORWARD:
            angle_rad = math.radians(self.angle)
            self.pos_x += self.move_distance * math.cos(angle_rad)
            self.pos_y -= self.move_distance * math.sin(angle_rad)
            
        elif command == self.CMD_BACKWARD:
            angle_rad = math.radians(self.angle)
            self.pos_x -= self.move_distance * math.cos(angle_rad)
            self.pos_y += self.move_distance * math.sin(angle_rad)
            
        elif command == self.CMD_LEFT:
            self.angle = (self.angle + self.turn_angle) % 360
            
        elif command == self.CMD_RIGHT:
            self.angle = (self.angle - self.turn_angle) % 360
        
        # Keep robot within bounds
        self.pos_x = max(0, min(self.pos_x, self.grid_size - 1))
        self.pos_y = max(0, min(self.pos_y, self.grid_size - 1))
        
        # Add to path history
        self.path.append((self.pos_x, self.pos_y))
        
        # Trim path if too long
        if len(self.path) > self.max_path_length:
            self.path = self.path[-self.max_path_length:]

# Standalone test
if __name__ == "__main__":
    robot_map = RobotMap()
    robot_map.start()
    
    try:
        # Simulated movement
        commands = [robot_map.CMD_FORWARD] * 5 + [robot_map.CMD_RIGHT] * 6 + [robot_map.CMD_FORWARD] * 5
        
        for cmd in commands:
            robot_map.move(cmd)
            time.sleep(0.2)
            
        print("Use arrow keys to move the robot, R to reset, ESC to quit")
        while robot_map.running:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        robot_map.stop()