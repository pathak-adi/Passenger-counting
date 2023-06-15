from datetime import datetime
import serial
import random
import struct
import sys
import argparse
from PyCRC.CRC16 import CRC16
import numpy as np
np.set_printoptions(threshold=sys.maxsize)

READ_LENGTH = (2,2,1,2,1,1,1,1,2,1,2,1,8)
parser = argparse.ArgumentParser(description='TOF UART Commands and Configurations')
parser.add_argument(
    'rs485_dev', metavar='RS485Device', type=str,
    help="The tty device that connects to the RS485 on the TOF"
)
parser.add_argument(
    'dev_addr', metavar='DeviceAddress', type=int,
    help="TOF device address"
)
parser.add_argument(
    'data_addr', metavar='DataAddress', type=int,
    help="Data address on the TOF"
)
parser.add_argument(
    'rw', metavar='ReadWrite', type=int,
    help="0 to read, 1 to write"
)
parser.add_argument(
    'value', metavar='Value', type=int,
    help="Value to write, doesn't matter if reading"
)
args = parser.parse_args()

device = args.rs485_dev
dev_address = args.dev_addr
address = args.data_addr
rw = args.rw
data = args.value
#send_id = random.randint(0, 255)
send_id = 0x7E

ser = serial.Serial(device, 115200, timeout=None)

if rw == 0:
    data_format = "=BBBB"
    data_hex = struct.pack(data_format, send_id, dev_address, rw, address)
else:
    data_format = "=BBBBH" if READ_LENGTH[address] == 2 else "=BBBBB"
    data_hex = struct.pack(data_format, send_id, dev_address, rw, address, data)
crc16 = CRC16().calculate(data_hex)
print("Data CRC16:", crc16)
data_hex += struct.pack('H', crc16)
sent_data = ['{:02X}'.format(b) for b in data_hex]
print("-->", ' '.join(sent_data))
ser.write(b'\xFF\xFF\xFF\xFF')
ser.write(data_hex)
ser.read_until(b'\xFE\xFF\xFE\xFF')

resp = ser.read(3 + READ_LENGTH[address])
return_crc = ser.read(2)
recv_packet = ['{:02X}'.format(b) for b in resp+return_crc]
print("<--", ' '.join(recv_packet))
return_crc = struct.unpack('H', return_crc)[0]
resp_crc16 = CRC16().calculate(resp)
if READ_LENGTH[address] == 2:
    msg_id, resp_addr, status, data = struct.unpack('=BBBH', resp)
elif READ_LENGTH[address] == 1:
    msg_id, resp_addr, status, data = struct.unpack(f'=BBBB', resp)
else:
    recv_data = struct.unpack(f'=BBB{READ_LENGTH[address]}B', resp)
    msg_id = recv_data[0]
    resp_addr = recv_data[1]
    status = recv_data[2]
    data = ['{:X}'.format(d) for d in recv_data[3:]]
print("Msg ID:", msg_id, "Matched" if msg_id == send_id else f"Not Matched {send_id}",)
print("Status:", status, "OK" if status == 0 else "Not OK")
print("Data:", data)
print("CRC check: get", return_crc, "expect", resp_crc16, "-->", "OK" if resp_crc16 == return_crc else "Not OK")

if address == 9:
    WIDTH,HEIGHT,MAX_TRACKERS = struct.unpack('3B', ser.read(3))
    SENSOR_DIM = WIDTH * HEIGHT
    SENSOR_FORMAT = f'{SENSOR_DIM}h'
    heightmap  = np.array(struct.unpack(SENSOR_FORMAT, ser.read(SENSOR_DIM * 2)), dtype=np.int16).reshape((HEIGHT,WIDTH))

    for i in range(MAX_TRACKERS):
        x, y, new, active, excluded = struct.unpack('2h3Bx', ser.read(8))
        print(x, y, new, active, excluded)

    print(heightmap)
