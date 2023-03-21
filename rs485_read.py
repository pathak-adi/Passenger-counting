from datetime import datetime
import struct
import sys
import time
import requests
import json
import serial
import urllib

from websocket import create_connection
from utils import boot_notification


def send_data(cin, cout, c_n):
    url = 'https://94bup2tdy0.execute-api.us-east-1.amazonaws.com/production/data/append'
    t = int(time.time())

    body = {
        'datetime': t,
        'imei': 'PCounter',
        'data': {'in': cin, 'out': cout, 'count': c_n},
    }
    try:
        response = requests.post(url, json.dumps(body))
        print(response.json())
    except:
        print('Error sending data')
        response = []

    try:
        item = {
            "action": "sendMessage",
            "data": json.dumps(body)

        }
        ws.send(json.dumps(item))

    except:
        ws.close()
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
while internet == False:
    internet = internet_on()
    time.sleep(15)
    print('no intenet')

boot_notification()
ws = create_connection("wss://degjo0ipsa.execute-api.us-east-1.amazonaws.com/production")
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
