/* Name: main.c
 * Author: Mitchel Humpherys
 * Copyright: 2015
 * License: Creative Commons
 */

#include <avr/io.h>
#include <util/delay.h>
#include <stdint.h>
#include <stdbool.h>
#include <util/twi.h>
#include <avr/interrupt.h>

#define __unused __attribute__((unused))

#define SERVO_CMD_OPEN 1
#define SERVO_CMD_CLOSE 2
#define SERVO_CMD_TWITCH 3


static void led_init(void)
{
    DDRD = 1 << 4;              /* make PD4 an output */
}

static void servo_set_degrees(uint8_t degrees);

/*
 * http://www.electroons.com/electroons/servo_control.html
 * http://eliaselectronics.com/atmega-servo-tutorial/
 */
static void servo_init(uint8_t init_degrees)
{
    /*
     * COM1A1:0 = 2 means clear OC1A on ICR1 match, non-inverting mode
     * WGM13:0 = 14 means: fast PWM counting to ICR1
     * CS12:0 = 2 means: Prescaler 8
     */
    TCCR1A = (1 << COM1A1) | (1 << WGM11);
    TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS11);

    /*
     * 16 MHz CPU, pulse width of 20 ms, means we need a pulse every
     * 320,000 cycles.  We can't count to 320,000 with a 16-bit register,
     * so we prescale it by 8 (we count by 8's).  We need to count by 8's
     * to 40,000 to get the 20 ms pulse.
     */
    ICR1 = 40000 - 1; // 16000000 / (8 * 50) = 320000 / 8 = 40000

    servo_set_degrees(init_degrees);
    DDRB |= (1 << PB1); // OC1A set to output
}

/*
 * lookup table for OCR1A value needed to move the servo to the given
 * degree (indexed by degrees).  We're counting to 40,000, so a 5% duty
 * cycle is 2,000 and a 10% duty cycle is 4,000.
 *
 * Constructed with a linear interpolation, found in lerp.el in
 * https://github.com/mgalgs/spideyween.
 */
static uint16_t servo_angle_to_ocr1a[180] = {
    2000, 2011, 2022, 2033, 2044, 2055, 2066, 2077, 2088, 2100, 2111, 2122, 2133, 2144, 2155, 2166, 2177, 2188, 2200, 2211, 2222, 2233, 2244, 2255, 2266, 2277, 2288, 2300, 2311, 2322, 2333, 2344, 2355, 2366, 2377, 2388, 2400, 2411, 2422, 2433, 2444, 2455, 2466, 2477, 2488, 2500, 2511, 2522, 2533, 2544, 2555, 2566, 2577, 2588, 2600, 2611, 2622, 2633, 2644, 2655, 2666, 2677, 2688, 2700, 2711, 2722, 2733, 2744, 2755, 2766, 2777, 2788, 2800, 2811, 2822, 2833, 2844, 2855, 2866, 2877, 2888, 2900, 2911, 2922, 2933, 2944, 2955, 2966, 2977, 2988, 3000, 3011, 3022, 3033, 3044, 3055, 3066, 3077, 3088, 3100, 3111, 3122, 3133, 3144, 3155, 3166, 3177, 3188, 3200, 3211, 3222, 3233, 3244, 3255, 3266, 3277, 3288, 3300, 3311, 3322, 3333, 3344, 3355, 3366, 3377, 3388, 3400, 3411, 3422, 3433, 3444, 3455, 3466, 3477, 3488, 3500, 3511, 3522, 3533, 3544, 3555, 3566, 3577, 3588, 3600, 3611, 3622, 3633, 3644, 3655, 3666, 3677, 3688, 3700, 3711, 3722, 3733, 3744, 3755, 3766, 3777, 3788, 3800, 3811, 3822, 3833, 3844, 3855, 3866, 3877, 3888, 3900, 3911, 3922, 3933, 3944, 3955, 3966, 3977, 3988
};

static void servo_set_degrees(uint8_t degrees)
{
    if (degrees > 179)
        degrees = 179;
    OCR1A = servo_angle_to_ocr1a[degrees];
}

static void sitfor(uint8_t sitfor)
{
    uint8_t i;

    for (i = 0; i < sitfor; ++i)
        _delay_ms(16);
}

static void led_on(void)
{
    PORTD |= 1 << 4;
}

static void led_off(void)
{
    PORTD &= ~(1 << 4);
}

static void __unused led_toggle(void)
{
    if (PORTD & (1 << 4))
        led_off();
    else
        led_on();
}

static void blinken(int n)
{
    uint8_t i;

    for (i = 0; i < n; ++i) {
        led_on();
        sitfor(1);
        led_off();
        sitfor(1);
    }
}

static void attention(void)
{
    blinken(10);
}

static __unused void send_bit(int bit)
{
    blinken(3);
    if (bit)
        led_on();
    sitfor(50);
}

#define MY_TWI_ADDR 0xa
#define TWA_SHIFT 1

static void i2c_init(void)
{
    /* prescaler = 1 (see next) */
    TWSR = 0;
    /*
     * scl_freq = cpu_hz/(16 + 2(TWBR)4^TWSR)
     *
     * and cpu_hz=16MHz, TWSR=0
     *
     * So with TWBR=12, we get scl_freq=400kHz
     */
    TWBR = 12;

    /* set slave address */
    TWAR = MY_TWI_ADDR << TWA_SHIFT;

    /* enable two-wire with acks enabled */
    TWCR = (1 << TWEA) | (1 << TWEN) | (1 << TWINT) | (1 << TWIE);
}

static void process_data(uint8_t data)
{
    switch (data) {
    case SERVO_CMD_OPEN:
        servo_set_degrees(0);
        blinken(2);
        sitfor(50);
        break;
    case SERVO_CMD_CLOSE:
        servo_set_degrees(180);
        blinken(20);
        sitfor(50);
        break;
    case SERVO_CMD_TWITCH:
        servo_set_degrees(155);
        sitfor(4);
        servo_set_degrees(180);
        blinken(5);
        break;
    default:
        blinken(100);
        sitfor(50);
        break;
    }
}

ISR(TWI_vect)
{
    uint8_t status, data;

    /* read the status */
    status = (TWSR & 0xf8);
    if (status == TW_SR_DATA_ACK) {
        /* we have data! */
        data = TWDR;
        TWCR = (1 << TWEA) | (1 << TWEN) | (1 << TWINT) | (1 << TWIE);
        process_data(data);
    } else if (status == TW_SR_SLA_ACK) {
        /* we got our address. keep waiting for data... */
        TWCR = (1 << TWEA) | (1 << TWEN) | (1 << TWINT) | (1 << TWIE);
    } else {
        TWCR = (1 << TWEA) | (1 << TWEN) | (1 << TWINT) | (1 << TWIE);
        /* might need to drop the TWINT? */
        /* TWCR = (1 << TWEA) | (1 << TWEN) | (1 << TWIE); */
    }
}

int main(void)
{
    i2c_init();
    led_init();
    servo_init(180);
    attention();

    /* allow interrupts */
    sei();

    for(;;) {
        led_toggle();
        sitfor(100);
    }

    return 0;   /* never reached */
}

/* Local Variables: */
/* c-file-style: "k&r" */
/* c-basic-offset: 4 */
/* eval: (progn (setq whitespace-style '(face trailing lines-tail empty indentation::space)) (whitespace-mode)) */
/* End: */
