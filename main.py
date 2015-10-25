#!/usr/bin/env python2

import sys
import time
import threading
from RPIO import PWM
import RPIO as GPIO


class Monster():
    """All GPIOs are BCM GPIO numbers.
    """
    def __init__(self, servo_gpio_num=22, solenoid_gpio_num=17):
        PWM.set_loglevel(PWM.LOG_LEVEL_ERRORS)
        self._servo = PWM.Servo()
        self._gpios = {
            'servo': servo_gpio_num,
            'solenoid': solenoid_gpio_num
        }
        GPIO.setup(self._gpios['solenoid'], GPIO.OUT)

    def activate_solenoid(self):
        GPIO.output(self._gpios['solenoid'], True)

    def deactivate_solenoid(self):
        GPIO.output(self._gpios['solenoid'], False)

    def fire_ball(self, active_time=.5):
        """Activate the solenoid for `active_time' seconds."""
        self.activate_solenoid()
        time.sleep(active_time)
        self.deactivate_solenoid()

    def set_servo(self, n):
        self._servo.set_servo(self._gpios['servo'], n)

    def close_door(self):
        self.set_servo(1200)

    def open_door(self):
        self.set_servo(1800)

    def toggle_door(self, time_open=.8):
        self.open_door()
        time.sleep(time_open)
        self.close_door()

    def ball_and_door(self):
        ball_thread = threading.Thread(target=self.fire_ball)
        door_thread = threading.Thread(target=self.toggle_door)

        door_thread.start()
        time.sleep(.5)
        ball_thread.start()

        ball_thread.join()
        door_thread.join()

    def sayhi(self, sleep_s=0.5, reps=5):
        for i in range(reps):
            self.close_door()
            time.sleep(sleep_s)
            self.open_door()
            time.sleep(sleep_s)


if __name__ == "__main__":
    monster = Monster()
    commands = ['sayhi', 'close_door', 'open_door', 'toggle_door', 'fire_ball',
                'ball_and_door']
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print 'Usage: main.py <command>'
        print
        print 'where command is one of:'
        print '\n'.join(['  - ' + c for c in commands])
        sys.exit(1)
    cmd = sys.argv[1]
    getattr(monster, cmd)()

    time.sleep(1)
    GPIO.cleanup()
