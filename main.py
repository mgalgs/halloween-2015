#!/usr/bin/env python2

import sys
import time
import threading
import subprocess
import os
import signal

from RPIO import PWM
import RPIO as GPIO
from smbus import SMBus

# I apologize for all the shelling.  I actually was using pyglet at first
# but it was cutting out unreliably...
SOUND_DIR = '/root/sounds'

def play_sound(snd):
    subprocess.Popen(['mpg123', '-q',
                      os.path.join(SOUND_DIR, snd)])

def loop_sound(snd):
    subprocess.Popen(['mpg123', '-q', '--loop', '-1',
                      os.path.join(SOUND_DIR, snd)])


class Monster():
    """Monster class.  Should only be used with a context manager!

    All GPIOs are BCM GPIO numbers.
    """

    I2C_BUS_NUM = 0
    SERVO_I2C_ADDR = 0xa

    SERVO_CMD_OPEN = 1
    SERVO_CMD_CLOSE = 2
    SERVO_CMD_TWITCH = 3

    DISTANCE_UPDATE_SECONDS = .2

    def __init__(self, solenoid_gpio_num=17,
                 echo_trigger_gpio_num=24, echo_gpio_num=25):
        self._gpios = {
            'solenoid': solenoid_gpio_num,
            'echo_trigger': echo_trigger_gpio_num,
            'echo': echo_gpio_num,
        }
        self._rangefinder_settled = False
        self._distance_lock = threading.Lock()
        self._distance = 999999999

    def __enter__(self):
        PWM.set_loglevel(PWM.LOG_LEVEL_ERRORS)
        GPIO.setup(self._gpios['solenoid'], GPIO.OUT)
        GPIO.setup(self._gpios['echo_trigger'], GPIO.OUT)
        GPIO.setup(self._gpios['echo'], GPIO.IN)
        self._i2c_bus = SMBus()
        self._i2c_bus.open(Monster.I2C_BUS_NUM)
        self.close_door()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._cm_active = False
        self._i2c_bus.close()
        GPIO.cleanup()

    def activate_solenoid(self):
        GPIO.output(self._gpios['solenoid'], True)

    def deactivate_solenoid(self):
        GPIO.output(self._gpios['solenoid'], False)

    def fire_ball(self, active_time=.3):
        """Activate the solenoid for `active_time' seconds."""
        self.activate_solenoid()
        time.sleep(active_time)
        self.deactivate_solenoid()

    def i2c_write(self, cmd, max_iters):
        for i in range(max_iters):
            try:
                self._i2c_bus.write_byte(Monster.SERVO_I2C_ADDR, cmd)
                return
            except IOError:
                time.sleep(.5)
                pass
        print "I2C Contention! Couldn't send command:", cmd

    def close_door(self):
        self.i2c_write(Monster.SERVO_CMD_CLOSE, 10)

    def open_door(self):
        self.i2c_write(Monster.SERVO_CMD_OPEN, 10)

    def twitch_door(self):
        self.i2c_write(Monster.SERVO_CMD_TWITCH, 10)

    def toggle_door(self, time_open=.8):
        self.open_door()
        time.sleep(time_open)
        self.close_door()

    def ball_and_door(self):
        self.twitch_door()
        time.sleep(1)
        self.fire_ball()
        time.sleep(1)
        self.fire_ball()

    # based on http://www.modmypi.com/blog/hc-sr04-ultrasonic-range-sensor-on-the-raspberry-pi
    def measure_distance(self):
        """Returns the distance (in meters) to the object being looked at.

        Probably should only happen in a thread due to all the sleeping
        """
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
        pulse_start = time.time()
        cnt = 0
        while not GPIO.input(self._gpios['echo']):
            pulse_start = time.time() # maybe pass would be better? might actually more cpu though...
            cnt += 1
            if cnt > 20000:
                return 999999999
        # we got a pulse, measure it's width by polling until it goes low
        # again.
        cnt = 0
        pulse_end = time.time()
        while GPIO.input(self._gpios['echo']):
            pulse_end = time.time()
            cnt += 1
            if cnt > 20000:
                return 999999999

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

    def set_distance(self, distance):
        with self._distance_lock:
            self._distance = distance

    def get_distance(self):
        with self._distance_lock:
            return self._distance

    def watch_distance(self):
        while self._keep_watching:
            distance = self.measure_distance()
            self.set_distance(distance)
            time.sleep(Monster.DISTANCE_UPDATE_SECONDS)
        print 'done watching distance'

    def monster_loop(self, trigger_threshold_meters=1.0,
                     come_closer_meters=2.0):
        loop_sound('background.mp3')
        self._keep_watching = True
        dist_thread = threading.Thread(target=self.watch_distance)
        dist_thread.start()
        try:
            last_come_closer = 0
            distances = [0, 0, 0] # simple moving average...
            while True:
                distances.insert(0, self.get_distance())
                distances.pop()
                distance = sum(distances) / 3.0
                print 'distances, distance:', distances, distance
                if distance < come_closer_meters and \
                   distance > trigger_threshold_meters and \
                   time.time() - last_come_closer > 12:
                    print 'come closer...'
                    play_sound('come-closer.mp3')
                    last_come_closer = time.time()
                elif distance < trigger_threshold_meters:
                    play_sound('vocal-leave-now-happy-halloween.mp3')
                    time.sleep(1)
                    print 'FIRE!'
                    self.ball_and_door()
                    time.sleep(10)
                time.sleep(.3)
        except KeyboardInterrupt:
            print "Interrupt received. Exiting loop."
        except SystemExit:
            print "Exiting loop."
        self._keep_watching = False
        print 'waiting for threads to exit...'
        dist_thread.join()
        print "ok, we're outta here"

    def sayhi(self, sleep_s=0.5, reps=5):
        for i in xrange(reps):
            self.open_door()
            time.sleep(sleep_s)
            self.close_door()
            time.sleep(sleep_s)


def sigterm_handler(signal, frame):
    print 'Got SIGTERM, terminating...'
    sys.exit(0)


if __name__ == "__main__":
    commands = ['sayhi', 'close_door', 'open_door', 'toggle_door',
                'twitch_door', 'fire_ball',
                'ball_and_door', 'print_distance', 'monitor_distance',
                'monster_loop']
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print 'Usage: main.py <command>'
        print
        print 'where command is one of:'
        print '\n'.join(['  - ' + c for c in commands])
        sys.exit(1)
    cmd = sys.argv[1]
    try:
        os.setpgrp()
    except:
        pass # doesn't work when running under systemd
    signal.signal(signal.SIGTERM, sigterm_handler)
    with Monster() as monster:
        if len(sys.argv) > 2:
            getattr(monster, cmd)(*sys.argv[2:])
        else:
            getattr(monster, cmd)()

    try:
        os.killpg(0, signal.SIGKILL)
    except:
        pass # ditto
