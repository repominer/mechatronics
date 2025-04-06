#!/usr/bin/env python3
from smbus2 import SMBus
import time

# PCA9685 I2C address (default 0x40)
PCA9685_ADDR = 0x40

# Register definitions (from PCA9685 datasheet)
MODE1      = 0x00
LED0_ON_L  = 0x06

def set_full_on(bus, channel, on, off):
    """
    Sets a channel to full on.
    Writes to the channel registers to set the "full on" flag.
    """
    reg = LED0_ON_L + 4 * channel
    # Data: LEDn_ON_L = 0, LEDn_ON_H = 0x10 (full on flag), LEDn_OFF_L = 0, LEDn_OFF_H = 0.
    data = [on & 0xFF, (on >> 8) & 0xFF, off & 0xFF, (off >> 8) & 0xFF]
    bus.write_i2c_block_data(PCA9685_ADDR, reg, data)

def set_off(bus, channel):
    """
    Turns the channel completely off.
    """
    reg = LED0_ON_L + 4 * channel
    data = [0, 0, 0, 0]
    bus.write_i2c_block_data(PCA9685_ADDR, reg, data)

def main():
    # Open I2C bus 7 (as determined by your i2cdetect results)
    bus = SMBus(7)
    
    # Reset MODE1 register to 0 (normal mode)
    bus.write_byte_data(PCA9685_ADDR, MODE1, 0x00)
    time.sleep(0.1)  # Allow oscillator to stabilize

    print("Setting channel 0 to FULL ON for 5 seconds...")
    set_full_on(bus, channel=0, on=0, off=2049)
    time.sleep(5)
    
    print("Turning channel 0 OFF for 1 second...")
    set_off(bus, channel=0)
    time.sleep(1)
    
    bus.close()

if __name__ == "__main__":
    main()
