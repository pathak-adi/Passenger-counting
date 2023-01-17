from datetime import datetime
import struct
import sys

import serial


if len(sys.argv) != 2:
    print("Usage: ./rs485_read.py <RS485 TTY device>")
    sys.exit(1)
device = sys.argv[1]

ser = serial.Serial(device, 115200, timeout=None)

ser.write("0".encode("UTF-8"))
while(True):
    ser.read_until(b'\x41\x41')
    hi, lo = struct.unpack('2B', ser.read(2))
    ser.write("0".encode("UTF-8"))
    print(datetime.now(), hi, lo)
