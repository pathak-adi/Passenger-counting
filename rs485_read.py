from datetime import datetime
import struct
import sys
import time
import requests
import json
import serial
import asyncio
import logging
from websocket import create_connection
from utils import boot_notification, connected_to_internet

logging.basicConfig(filename='app.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')
logging.warning('Boot Notification')

if len(sys.argv) != 2:
    print("Usage: ./rs485_read.py <RS485 TTY device>")
    sys.exit(1)
device = sys.argv[1]

try:
    ws = create_connection("wss://degjo0ipsa.execute-api.us-east-1.amazonaws.com/production")
except:
    ws = []
    logging.error('Unable to connect to websocket')

internet = connected_to_internet()
if not internet:
    logging.error('no internet')


boot_notification(0)


async def send_data(cin, cout, c_n, t):
    url = 'google.com' #'https://94bup2tdy0.execute-api.us-east-1.amazonaws.com/production/data/append'
    body = {
        'datetime': t,
        'imei': 'PCounter',
        'data': {'in': cin, 'out': cout, 'count': c_n},
    }
    try:
        response = requests.post(url, json.dumps(body))
        # logging.info(response.json())
    except:
        logging.error('Error sending data')
        logging.error(f'Internet connectivity: {connected_to_internet()}')
        response = []


    try:
        item = {
            "action": "sendMessage",
            "data": json.dumps(
                {
                    'datetime': datetime.now().isoformat(),
                    'imei': 'PCounter',
                    'data': {'in': cin, 'out': cout, 'count': c_n},
                }
            )

        }
        ws.send(json.dumps(item))

    except:
        ws.close()
        logging.error('websocket error')
    return response


async def main(device,internet):
    ser = serial.Serial(device, 115200, timeout=None)
    ser.write("0".encode("UTF-8"))
    passenger_onboard = 0

    while True:
        hi, lo, passenger_onboard, t = await get_counter_data(ser,passenger_onboard)

        if not internet:
            internet = connected_to_internet()
            if internet:
                boot_notification(passenger_onboard)
                global ws
                ws = create_connection("wss://degjo0ipsa.execute-api.us-east-1.amazonaws.com/production")

        if datetime.now().hour == 0:
            passenger_onboard = 0

        task = asyncio.create_task(send_data(hi, lo, passenger_onboard, t))


async def get_counter_data(ser,passenger_onboard):
    ser.read_until(b'\x41\x41')
    hi, lo = struct.unpack('2B', ser.read(2))
    ser.write("0".encode("UTF-8"))
    passenger_onboard = passenger_onboard + hi - lo
    t = int(time.time())

    return hi, lo, passenger_onboard, t


asyncio.run(main(device,internet))
