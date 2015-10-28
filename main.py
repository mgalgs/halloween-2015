#!/usr/bin/env python2

import sys
import time
import threading
import subprocess
from RPIO import PWM
import RPIO as GPIO
from smbus import SMBus


class RefCount():
    def __init__(self):
        self._cnt = 0
        self._lock = threading.Lock()

    def __enter__(self):
        self.inc()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.dec()

    def inc(self):
        with self._lock:
            self._cnt += 1

    def dec(self):
        with self._lock:
            self._cnt -= 1

    def cnt(self):
        with self._lock:
            return self._cnt


class Monster():
    """Monster class.  Should only be used with a context manager!

    All GPIOs are BCM GPIO numbers.
    """

    I2C_BUS_NUM = 0
    SERVO_I2C_ADDR = 0xa
    SERVO_CMD_OPEN = 1
    SERVO_CMD_CLOSE = 2

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
        self._io_refcnt = RefCount()

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

    def fire_ball(self, active_time=.5):
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
                print "i2c bus contention..."
                time.sleep(.5)
                pass
        print "Couldn't send command:", cmd

    def close_door(self, max_iters=3):
        self.i2c_write(Monster.SERVO_CMD_CLOSE, max_iters)

    def open_door(self, max_iters=3):
        self.i2c_write(Monster.SERVO_CMD_OPEN, max_iters)

    def toggle_door(self, time_open=.8):
        self.open_door()
        time.sleep(time_open)
        self.close_door()

    def fire_ball_drop_cnt(self):
        self.fire_ball()
        self._io_refcnt.dec()

    def toggle_door_drop_cnt(self):
        self.toggle_door()
        self._io_refcnt.dec()

    def ball_and_door(self):
        ball_thread = threading.Thread(target=self.fire_ball_drop_cnt)
        door_thread = threading.Thread(target=self.toggle_door_drop_cnt)

        # two threads will have outstanding I/O.  Need two refcounts.  The
        # counts will be dropped when the threads are done with their work.
        # There must be a cleaner way of doing this but, I'm tired...
        self._io_refcnt.inc()
        self._io_refcnt.inc()

        door_thread.start()
        time.sleep(.5)
        ball_thread.start()

        ball_thread.join()
        door_thread.join()

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

    def monster_loop(self, iters=None, trigger_threshold_meters=.3):
        iters = int(iters)
        print 'running', iters if iters is not None else 'unlimited', 'iters'
        self._keep_watching = True
        dist_thread = threading.Thread(target=self.watch_distance)
        dist_thread.start()
        try:
            cnt = 0
            while True:
                distance = self.get_distance()
                if distance < trigger_threshold_meters:
                    print 'FIRE!'
                    self.ball_and_door()
                time.sleep(1)
                cnt += 1
                if iters is not None and cnt > iters:
                    break
        except KeyboardInterrupt:
            print "Interrupt received. Exiting loop."
        self._keep_watching = False
        print 'waiting for threads to exit...'
        dist_thread.join()
        print 'waiting for any outstanding I/O...'
        while self._io_refcnt.cnt() > 0:
            print "waiting for I/O..."
            time.sleep(1)
        print "ok, we're outta here"

    def sayhi(self, sleep_s=0.5, reps=5):
        for i in xrange(reps):
            self.open_door()
            time.sleep(sleep_s)
            self.close_door()
            time.sleep(sleep_s)


if __name__ == "__main__":
    commands = ['sayhi', 'close_door', 'open_door', 'toggle_door', 'fire_ball',
                'ball_and_door', 'print_distance', 'monitor_distance',
                'monster_loop']
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print 'Usage: main.py <command>'
        print
        print 'where command is one of:'
        print '\n'.join(['  - ' + c for c in commands])
        sys.exit(1)
    cmd = sys.argv[1]
    with Monster() as monster:
        if len(sys.argv) > 2:
            getattr(monster, cmd)(*sys.argv[2:])
        else:
            getattr(monster, cmd)()

    time.sleep(1)
