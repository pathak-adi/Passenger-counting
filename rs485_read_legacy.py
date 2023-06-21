from datetime import datetime
import struct
import sys
import time
import requests
import json
import serial
import urllib

from utils import boot_notification


def send_data(cin, cout, c_n):
    url = 'https://analytics.basi-go.com/telematics/api/passenger_counter/'
    t = str(datetime.now())

    body = {
        'datetime': t,
        'in_count': cin,
        'out_count': cout,
        'occupancy': c_n,
        'vehicle': 'KDH043A'
    }
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        response = requests.post(url,headers=headers, data=json.dumps(body))
        print(response.json())
    except:
        print('Error sending data')
        response = []

    return response


def internet_on():
    try:
        urllib.request.urlopen('https://google.com', timeout=10)
        return True
    except urllib.request.URLError as err:
        return False


if len(sys.argv) != 2:
    print("Usage: ./rs485_read.py <RS485 TTY device>")
    sys.exit(1)
device = sys.argv[1]

ser = serial.Serial(device, 115200, timeout=None)

internet = internet_on()
while not internet:
    internet = internet_on()
    time.sleep(15)
    print('no internet')

boot_notification()
ser.write("0".encode("UTF-8"))
passenger_onboard = 0
while True:
    ser.read_until(b'\x41\x41')
    hi, lo = struct.unpack('2B', ser.read(2))
    ser.write("0".encode("UTF-8"))
    passenger_onboard = passenger_onboard + hi - lo
    print(datetime.now(), hi, lo, passenger_onboard)
    if datetime.now().hour == 0:
        passenger_onboard = 0
    send_data(hi, lo, passenger_onboard)
