import argparse
import numpy as np
import datetime
import threading
import random
import sys
import os
import serial
import struct
import time
from PyCRC.CRC16 import CRC16
import subprocess as sp

np.set_printoptions(threshold=sys.maxsize, linewidth=200)

parser = argparse.ArgumentParser(description='TOF UART Commands and Configurations')
parser.add_argument(
    'rs485_dev', metavar='RS485Device', type=str,
    help="The tty device that connects to the RS485 on the TOF"
)
parser.add_argument(
    'dev_addr', metavar='DeviceAddress', type=int,
    help="TOF device address"
)
args = parser.parse_args()

cmd_device = args.rs485_dev
DEV_ADDR = args.dev_addr

ser = serial.Serial(cmd_device, 115207, timeout=None)


READ_LENGTH = (2, 2, 1, 2, 1, 1, 1, 1, 2, 1, 2, 1,)


def send_rs485_data(dev_address, rw, address, data):
    send_id = random.randint(0, 255)
    msg_id = send_id - 1
    if rw == 0:
        data_format = "=BBBB"
        data_hex = struct.pack(data_format, send_id, dev_address, rw, address)
    else:
        data_format = "=BBBBH" if READ_LENGTH[address] == 2 else "=BBBBB"
        data_hex = struct.pack(data_format, send_id, dev_address, rw, address, data)
    crc16 = CRC16().calculate(data_hex)
    data_hex += struct.pack('H', crc16)
    ser.write(b'\xFF\xFF\xFF\xFF')
    ser.write(data_hex)
    ser.read_until(b'\xFE\xFF\xFE\xFF')
    while True:
        try:
            resp = ser.read(3 + READ_LENGTH[address])
            return_crc = struct.unpack('H', ser.read(2))[0]
            resp_crc16 = CRC16().calculate(resp)
            if READ_LENGTH[address] == 2:
                msg_id, resp_addr, status, data = struct.unpack('=BBBH', resp)
            else:
                msg_id, resp_addr, status, data = struct.unpack('=BBBB', resp)

            if msg_id == send_id:
                return status == 0, data
        except:
            return False, 0


def get_tof_conf(addr):
    res, data = send_rs485_data(DEV_ADDR, 0, addr, 0)
    return data




def main():

    line_count = [0, 0]

    while (True):

        tic = time.time()

        serial_read_time = time.time() - tic
        # print('getting data')
        hi = get_tof_conf(6)
        lo = get_tof_conf(7)
        if (hi>0) or (lo>0):
            print(f" In Count:{hi} \n Out Count:{lo}")
            line_count[0] += hi
            line_count[1] += lo
            print(line_count)



if __name__ == '__main__':
    main()
