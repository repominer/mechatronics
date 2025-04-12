import time
import threading
import logging
import heapq

logger = logging.getLogger('navigation')

class NavigationController:
    """
    Navigation Controller that computes an optimal path using A* (Q* planning)
    and guides the robot along that path using discrete motor commands.
    
    It uses the robot_map grid and a set of obstacles (stored as (row, col) tuples)
    to compute the optimal path from the current position to the target.
    
    The computed path is then followed by rotating the robot to the correct orientation
    and issuing a forward move for each grid cell.
    """
    def __init__(self, motor_controller, robot_map):
        if not motor_controller or not robot_map:
            raise ValueError("MotorController and RobotMap instances are required.")
        self.motor_controller = motor_controller
        self.robot_map = robot_map
        self.target = None
        self.is_navigating = False
        self._nav_thread = None
        self._lock = threading.Lock()
        self.loop_delay = 0.2      # Delay used during turning
        self.forward_delay = 2   # Delay after a forward command (adjust this to change per-unit movement)
        self.obstacles = set()     # Set of (row, col) tuples representing obstacles
        self.turn_left_delay = 1.95      # Delay for left turn
        self.turn_right_delay = 1.95     # Delay for right turn
        logger.info("NavigationController (optimal path planning) initialized.")

    def update_timing(self, forward_delay=None, turn_left_delay=None, turn_right_delay=None):
        """
        Update the timing parameters for forward and turning commands.
        """
        with self._lock:
            if forward_delay is not None:
                self.forward_delay = forward_delay
            if turn_left_delay is not None:
                self.turn_left_delay = turn_left_delay
            if turn_right_delay is not None:
                self.turn_right_delay = turn_right_delay
        logger.info(f"Navigation timing updated: forward {self.forward_delay}s, left {self.turn_left_delay}s, right {self.turn_right_delay}s")

    @staticmethod
    def manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def get_neighbors(cell, grid_size, obstacles):
        neighbors = []
        row, col = cell
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < grid_size and 0 <= nc < grid_size and ((nr, nc) not in obstacles):
                neighbors.append((nr, nc))
        return neighbors

    @staticmethod
    def a_star_search(start, goal, grid_size, obstacles):
        open_set = []
        heapq.heappush(open_set, (NavigationController.manhattan(start, goal), start))
        came_from = {}
        g_score = {start: 0}
        while open_set:
            current_f, current = heapq.heappop(open_set)
            if current == goal:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.append(start)
                return path[::-1]
            for neighbor in NavigationController.get_neighbors(current, grid_size, obstacles):
                tentative_g = g_score[current] + 1  # cost per move is 1
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + NavigationController.manhattan(neighbor, goal)
                    heapq.heappush(open_set, (f_score, neighbor))
        return None

    def set_target(self, target_row, target_col):
        """
        Set a new navigation target. This method computes the optimal path using A*
        and then starts a thread to follow the path.
        """
        with self._lock:
            if target_row is None or target_col is None:
                logger.warning("Invalid target provided: row or col is None.")
                return
            self.target = {'row': float(target_row), 'col': float(target_col)}
            logger.info(f"Optimal Navigation target set to {self.target}")
            if not self.is_navigating:
                self.is_navigating = True
                self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_optimal_start")
                time.sleep(0.1)
                # Compute the optimal path using A*
                start = (int(round(self.robot_map.pos_y)), int(round(self.robot_map.pos_x)))  # (row, col)
                goal = (int(round(self.target['row'])), int(round(self.target['col'])))
                grid_size = self.robot_map.grid_size
                path = NavigationController.a_star_search(start, goal, grid_size, self.obstacles)
                if path is None:
                    logger.error("No path found to the target.")
                    self.clear_target()
                    return
                logger.info(f"Optimal path computed: {path}")
                # Start following the path in a new thread
                self._nav_thread = threading.Thread(target=self.follow_path, args=(path,), daemon=True)
                self._nav_thread.start()

    def follow_path(self, path):
        """
        Follow the computed path by issuing discrete motor commands.
        Uses time-based delays for turning, similar to the forward movement timing.
        Each cell in the path is assumed to be 1 grid cell apart.
        """
        logger.info("Following optimal path (time-based turning)...")
        for cell in path[1:]:  # Skip the starting cell.
            current_row = int(round(self.robot_map.pos_y))
            current_col = int(round(self.robot_map.pos_x))
            target_row, target_col = cell
            # Determine desired angle based on relative position.
            if target_col > current_col:
                desired_angle = 0      # Right
            elif target_col < current_col:
                desired_angle = 180    # Left
            elif target_row < current_row:
                desired_angle = 90     # Up
            elif target_row > current_row:
                desired_angle = 270    # Down
            else:
                desired_angle = self.robot_map.angle  # Should not occur

            current_angle = int(round(self.robot_map.angle)) % 360
            # Calculate the minimal angular difference.
            delta = (desired_angle - current_angle + 360) % 360

            if delta < 5:
                logger.info(f"Angle within tolerance: current {current_angle}° vs desired {desired_angle}° (diff: {delta}°)")
            elif delta <= 180:
                self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_optimal_turn")
                time.sleep(.5)  # Allow time for the robot to stop before turning
                logger.info(f"Turning left: current {current_angle}° -> desired {desired_angle}° (diff: {delta}°)")
                self.motor_controller.send_command(self.motor_controller.CMD_LEFT, "nav_optimal")
                time.sleep(self.turn_left_delay)
            else:
                self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_optimal_turn")
                time.sleep(.5)  # Allow time for the robot to stop before turning
                logger.info(f"Turning right: current {current_angle}° -> desired {desired_angle}° (diff: {360 - delta}°)")
                self.motor_controller.send_command(self.motor_controller.CMD_RIGHT, "nav_optimal")
                time.sleep(self.turn_right_delay)

            # Move forward one cell.
            self.motor_controller.send_command(self.motor_controller.CMD_FORWARD, "nav_optimal")
            logger.info("Moving forward 1 unit along path.")
            time.sleep(self.forward_delay)

        # Path completed—stop the robot.
        self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_optimal_end")
        logger.info("Optimal path following complete.")
        self.clear_target()

    def clear_target(self):
        with self._lock:
            self.target = None
            self.is_navigating = False
        self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_optimal_clear")
        logger.info("Optimal navigation target cleared.")
