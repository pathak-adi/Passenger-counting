from datetime import datetime
import struct
import sys

import numpy as np
import serial

if len(sys.argv) != 5:
    print("Usage: ./uart_config.py <TTY device> <address> <r/w> <data>")
    sys.exit(1)

device = sys.argv[1]
address = int(sys.argv[2])
rw = int(sys.argv[3])
data = int(sys.argv[4])

ser = serial.Serial(device, 115200, timeout=None)
ser.write(struct.pack("BBH", address, rw, data))
ser.read_until(b'\x46\x46')
resp = ser.read(2)
print(struct.unpack('H', resp))
if address == 9:
    MAX_TRACKERS = 6
    heightmap  = np.array(struct.unpack('128h', ser.read(256)), dtype=np.int16).reshape((8,16))
    for i in range(MAX_TRACKERS):
        x, y, new, active, excluded = struct.unpack('2h3Bx', ser.read(8))
        print(x, y, new, active, excluded)
