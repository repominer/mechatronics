class Controls:
    def __init__(self):
        self.left = 0
        self.right = 0
        self.direction = [0, 0]
        print('Controls initialized')

    def turn_left(self, degrees=90):
        self.right += 1
        self.left -= 1
        self.direction[0] = -1
        print('Turning left by', degrees, 'degrees')

    def turn_right(self, degrees=90):
        self.left += 1
        self.right -= 1
        self.direction[0] = 1
        print('Turning right by', degrees, 'degrees')

    def go_forward(self, speed=100):
        if self.direction[1] != 1:
            self.left += 1
            self.right += 1
            self.direction[1] = 1
        print('Going forward at', speed, 'percent speed')

    def go_backward(self, speed=100):
        if self.direction[1] != -1:
            self.left = -1
            self.right = -1
            self.direction[1] = -1
        print('Going backward at', speed, 'percent speed')

    def set_motor_speed(self, left, right):
        self.left = left
        self.right = right
        print('Setting motor speed to', left, right)

    def stop(self):
        self.left = 0
        self.right = 0
        self.direction = [0, 0]
        print('Stopping')


if __name__ == '__main__':
    controls = Controls()
    controls.go_forward()
    controls.turn_left()
    controls.set_motor_speed(2, 2)
    controls.stop()
