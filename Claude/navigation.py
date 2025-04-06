# navigation.py
import math
import time
import threading
import logging

logger = logging.getLogger('navigation')
# Ensure logger output is visible
# logging.basicConfig(level=logging.DEBUG) # Use DEBUG to see detailed Nav Steps

class NavigationController:
    """
    Handles navigation logic to move the robot towards a target point on the map
    using only 90-degree turns (Manhattan movement: X then Y).
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

        # --- Tuning Parameters ---
        # Thresholds for considering alignment/position reached
        self.position_threshold = 0.3 # How close for X or Y alignment
        self.target_threshold = 0.5   # How close for final target reached
        self.angle_threshold = 10.0   # Allowed angle deviation (degrees) for axis alignment
        # Loop frequency control
        self.loop_delay = 0.1 # seconds (10 Hz)

        logger.info("NavigationController initialized (90-Degree Turn Mode).")

    def set_target(self, target_row, target_col):
        with self._lock:
            if target_row is None or target_col is None:
                logger.warning("Invalid target provided: row or col is None.")
                return
            new_target = {'row': float(target_row), 'col': float(target_col)}
            if new_target == self.target and self.is_navigating:
                 logger.info(f"Target {new_target} is the same as current, navigation continues.")
                 return

            self.target = new_target
            logger.info(f"Navigation target set to {self.target}")

            if not self.is_navigating:
                self.is_navigating = True
                self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_start")
                time.sleep(0.1)
                self._nav_thread = threading.Thread(target=self._navigation_loop, daemon=True)
                self._nav_thread.start()
            else:
                logger.info("Navigation already in progress, target updated.")

    def clear_target(self):
        with self._lock:
            if self.is_navigating or self.target:
                logger.info("Clearing navigation target and stopping.")
            self.target = None
            self.is_navigating = False
            self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_clear")

    def _normalize_angle_diff(self, diff):
        """Normalize angle difference to the range [-180, 180]."""
        diff = (diff + 180) % 360 - 180
        return diff

    def _navigation_loop(self):
        logger.info("Navigation loop started (90-Degree Turn Mode).")

        while True: # Loop controlled by self.is_navigating check inside
            with self._lock:
                if not self.is_navigating or not self.target:
                    logger.debug("Navigation condition false, exiting loop.")
                    self.is_navigating = False
                    break
                target_row = self.target['row']
                target_col = self.target['col']

            # --- Get Current State ---
            try:
                current_row = self.robot_map.pos_y
                current_col = self.robot_map.pos_x
                current_angle = self.robot_map.angle
            except Exception as e:
                logger.error(f"Error reading robot pose: {e}. Skipping step.")
                time.sleep(self.loop_delay * 2)
                continue

            # --- Check if Overall Target Reached ---
            # Using manhattan distance isn't quite right, use euclidean for final check
            final_delta_row = target_row - current_row
            final_delta_col = target_col - current_col
            distance_to_target = math.sqrt(final_delta_row**2 + final_delta_col**2)

            if distance_to_target < self.target_threshold:
                logger.info(f"Target ({target_col:.1f}, {target_row:.1f}) reached! Dist: {distance_to_target:.2f}")
                self.clear_target()
                break

            # --- Manhattan Navigation Logic (X first, then Y) ---
            command = None
            action = "Idle"
            delta_col = target_col - current_col

            # 1. Align and Move Horizontally (X / Column) first
            if abs(delta_col) > self.position_threshold:
                # Need to align/move in X direction
                x_target_angle = 0.0 if delta_col > 0 else 180.0 # 0=Right (East), 180=Left (West)
                angle_diff = self._normalize_angle_diff(x_target_angle - current_angle)

                if abs(angle_diff) > self.angle_threshold:
                    # Need to turn to face X direction
                    command = self.motor_controller.CMD_LEFT if angle_diff > 0 else self.motor_controller.CMD_RIGHT
                    action = f"Aligning X (Target Angle: {x_target_angle:.0f})"
                else:
                    # Aligned correctly, move forward in X direction
                    command = self.motor_controller.CMD_FORWARD
                    action = "Moving X"
            else:
                # X position is aligned, now handle Y position
                delta_row = target_row - current_row # Recalculate delta_row needed here

                if abs(delta_row) > self.position_threshold: # Need Y movement (check position threshold again)
                     # Need to align/move in Y direction
                    # Remember: Y increases downwards (row index increases)
                    y_target_angle = 270.0 if delta_row > 0 else 90.0 # 270=Down (South), 90=Up (North)
                    angle_diff = self._normalize_angle_diff(y_target_angle - current_angle)

                    if abs(angle_diff) > self.angle_threshold:
                        # Need to turn to face Y direction
                        command = self.motor_controller.CMD_LEFT if angle_diff > 0 else self.motor_controller.CMD_RIGHT
                        action = f"Aligning Y (Target Angle: {y_target_angle:.0f})"
                    else:
                        # Aligned correctly, move forward in Y direction
                        command = self.motor_controller.CMD_FORWARD
                        action = "Moving Y"
                else:
                     # Both X and Y are within position_threshold, but not target_threshold? Stop.
                     # This might happen if thresholds are different.
                     logger.info("X/Y position aligned but target threshold not met. Stopping.")
                     command = self.motor_controller.CMD_STOP
                     action = "Stopping near target"
                     self.clear_target() # Clear target as we are stopping
                     break # Exit loop


            # --- Send Command ---
            if command:
                 logger.debug(f"Nav Step: Target=({target_col:.1f},{target_row:.1f}), "
                             f"Current=({current_col:.1f},{current_row:.1f}), Angle={current_angle:.1f}, "
                             #f"TargetAngle={target_angle_deg:.1f}, Diff={angle_diff:.1f}, " # Not relevant now
                             f"Dist={distance_to_target:.1f}. Action: {action}")
                 self.motor_controller.send_command(command, "navigation")
            # No else needed, if command is None, no action is sent (e.g., if perfectly aligned but Y needs no move)


            # --- Loop Delay ---
            time.sleep(self.loop_delay)
            # End of while loop

        # Ensure motors are stopped when loop exits
        self.motor_controller.send_command(self.motor_controller.CMD_STOP, "nav_loop_end")
        logger.info("Navigation loop thread finished.")