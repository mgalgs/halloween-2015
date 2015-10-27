#!/usr/bin/env python2

import sys
import time
import threading
from RPIO import PWM
import RPIO as GPIO


class Monster():
    """All GPIOs are BCM GPIO numbers.
    """
    def __init__(self, solenoid_gpio_num=17,
                 echo_trigger_gpio_num=24, echo_gpio_num=25):
        PWM.set_loglevel(PWM.LOG_LEVEL_ERRORS)
        self._gpios = {
            'solenoid': solenoid_gpio_num,
            'echo_trigger': echo_trigger_gpio_num,
            'echo': echo_gpio_num,
        }
        self.close_door()       # to make sure servo is init'd
        GPIO.setup(self._gpios['solenoid'], GPIO.OUT)
        GPIO.setup(self._gpios['echo_trigger'], GPIO.OUT)
        GPIO.setup(self._gpios['echo'], GPIO.IN)
        self._rangefinder_settled = False

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
        pass

    def close_door(self):
        pass

    def open_door(self):
        pass

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

    # based on http://www.modmypi.com/blog/hc-sr04-ultrasonic-range-sensor-on-the-raspberry-pi
    def measure_distance(self, settle_rangefinder=False):
        """Probably should only happen in a thread due to all the sleeping"""
        if not self._rangefinder_settled:
            # let the sensor settle
            GPIO.output(self._gpios['echo_trigger'], False)
            time.sleep(2)
            self._rangefinder_settled = True

        # 10 us pulse
        GPIO.output(self._gpios['echo_trigger'], True)
        time.sleep(0.00001)
        GPIO.output(self._gpios['echo_trigger'], False)
        # interrupt might be better?
        while not GPIO.input(self._gpios['echo']):
            pulse_start = time.time() # maybe pass would be better? might actually more cpu though...
        # we got a pulse, measure it's width by polling until it goes low
        # again.
        while GPIO.input(self._gpios['echo']):
            pulse_end = time.time()

        pulse_duration = pulse_end - pulse_start
        sound_mps = 343.0         # speed of sound: 343 m/s
        distance = sound_mps * pulse_duration
        # and the pulse width is actually the time it takes to get to the
        # object *and back*, so we need to divide by two to get just the
        # distance:
        distance /= 2.0
        # Because the datasheet says:
        #
        #   we suggest to use over 60ms measurement cycle, in order to
        #   prevent trigger signal to the echo signal.
        #
        # We'll use 80ms to be safe
        time.sleep(.08)
        return distance

    def print_distance(self):
        print 'Distance: ', self.measure_distance(), ' meters'

    def monitor_distance(self, iters=10):
        iters = int(iters)      # we pass strings from the command line below...
        for i in xrange(iters):
            self.print_distance()
            sys.stdin.flush()

    def sayhi(self, sleep_s=0.5, reps=5):
        for i in xrange(reps):
            self.close_door()
            time.sleep(sleep_s)
            self.open_door()
            time.sleep(sleep_s)


if __name__ == "__main__":
    commands = ['sayhi', 'close_door', 'open_door', 'toggle_door', 'fire_ball',
                'ball_and_door', 'print_distance', 'monitor_distance']
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print 'Usage: main.py <command>'
        print
        print 'where command is one of:'
        print '\n'.join(['  - ' + c for c in commands])
        sys.exit(1)
    cmd = sys.argv[1]
    monster = Monster()
    if len(sys.argv) > 2:
        getattr(monster, cmd)(*sys.argv[2:])
    else:
        getattr(monster, cmd)()

    time.sleep(1)
    GPIO.cleanup()
