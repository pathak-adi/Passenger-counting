from flask import Flask, render_template, Response, request, redirect, url_for
import argparse
import numpy as np
import datetime
import threading
import random
import cv2
import sys
import os
import serial
import struct
import time
from scipy import interpolate
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

TRACK_COLOUR_MAP = ((255,0,255),(255,0,0), (0,255,0),(255,255,0))
app = Flask(__name__)
ser = serial.Serial(cmd_device, 115207, timeout=None)

framebuffer = [None, None]
buffer_num = 0
stop_now = threading.Event()
config_update = threading.Event()

READ_LENGTH = (2,2,1,2,1,1,1,1,2,1,2,1,)

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

def set_tof_conf(addr, val):
    res, data = send_rs485_data(DEV_ADDR, 1, addr, val)
    return data

def get_ceiling_height():
    return get_tof_conf(0)

def get_min_height():
    return get_tof_conf(1)

def get_signal_threshold():
    return get_tof_conf(10)

def set_ceiling_height(height):
    return set_tof_conf(0, height)

def set_min_height(height):
    return set_tof_conf(1, height)

def set_signal_threshold(signal):
    return set_tof_conf(10, signal)

# Test read a sensor data
send_rs485_data(DEV_ADDR, 1, 9, 0)
SENSOR_IMG_WIDTH, SENSOR_IMG_HEIGHT, MAX_TRACKERS = struct.unpack('3B', ser.read(3))
ser.read(SENSOR_IMG_WIDTH * SENSOR_IMG_HEIGHT * 2 + 8*MAX_TRACKERS)

UPSAMPLE_WIDTH = SENSOR_IMG_WIDTH + (SENSOR_IMG_WIDTH - 1) * 4
UPSAMPLE_HEIGHT = SENSOR_IMG_HEIGHT + (SENSOR_IMG_HEIGHT - 1) * 4
SENSOR_IMG_ARR_SIZE = SENSOR_IMG_WIDTH * SENSOR_IMG_HEIGHT
DISPLAY_WIDTH = UPSAMPLE_WIDTH * 4
DISPLAY_HEIGHT = UPSAMPLE_HEIGHT * 4

CEILING_HEIGHT = get_ceiling_height()
MIN_HEIGHT = get_min_height()
SIGNAL_THRESHOLD = get_signal_threshold()
NEW_CEILING_HEIGHT = CEILING_HEIGHT
NEW_MIN_HEIGHT = MIN_HEIGHT
NEW_SIGNAL_THRESHOLD = SIGNAL_THRESHOLD
RELEARN_BG = False

def main():
    global buffer_num
    global CEILING_HEIGHT
    global MIN_HEIGHT
    global SIGNAL_THRESHOLD
    global NEW_CEILING_HEIGHT
    global NEW_MIN_HEIGHT
    global NEW_SIGNAL_THRESHOLD
    global RELEARN_BG
    line_count = [0,0]

    trackers = [[0,[],0],[0,[],0],[0,[],0],[0,[],0],[0,[],0],[0,[],0],[0,[],0],[0,[],0]]
    while(True):
        if config_update.is_set():
            set_min_height(NEW_MIN_HEIGHT)
            set_ceiling_height(NEW_CEILING_HEIGHT)
            set_signal_threshold(NEW_SIGNAL_THRESHOLD)
            CEILING_HEIGHT = get_ceiling_height()
            MIN_HEIGHT = get_min_height()
            SIGNAL_THRESHOLD = get_signal_threshold()
            if RELEARN_BG:
                set_tof_conf(5, 100)
                RELEARN_BG = False
            config_update.clear()
        for tracker in trackers:
            tracker[2] += 1
            tracker[2] = min(tracker[2], 3)
        
        send_rs485_data(DEV_ADDR, 1, 9, 0)
        tic = time.time()
        sensor_data = ser.read(3 + SENSOR_IMG_ARR_SIZE * 2)
        tracker_data = ser.read(8 * MAX_TRACKERS)
        serial_read_time = time.time() - tic
        # First 3 bytes are width, height, num of trackers, it was read in the beginning, so disregard it

        heightmap  = np.array(struct.unpack(f'{SENSOR_IMG_ARR_SIZE}h', sensor_data[3:]), dtype=np.int16).reshape((SENSOR_IMG_HEIGHT, SENSOR_IMG_WIDTH))

        for i in range(MAX_TRACKERS):
            x, y, new, active, excluded = struct.unpack('2hBBBx', tracker_data[i*8:(i+1)*8])
            #print(x, y, new, active, excluded)
            if new:
                trackers[i][1] = []
            if active:
                trackers[i][2] = 0
            if len(trackers[i][1]) == 50:
                trackers[i][1].pop(0)
            trackers[i][0]  = excluded
            trackers[i][1].append((int(x), int(y)))

        hi = get_tof_conf(6)
        lo = get_tof_conf(7)
        line_count[0] += hi
        line_count[1] += lo

        heightmap = np.maximum(np.minimum(CEILING_HEIGHT, heightmap),0)
        f = interpolate.interp2d(np.arange(SENSOR_IMG_WIDTH), np.arange(SENSOR_IMG_HEIGHT), heightmap, kind='linear')
        resize_map = f(np.arange(0,SENSOR_IMG_WIDTH, SENSOR_IMG_WIDTH/UPSAMPLE_WIDTH), np.arange(0,SENSOR_IMG_HEIGHT, SENSOR_IMG_HEIGHT/UPSAMPLE_HEIGHT))
        blob_map = ((CEILING_HEIGHT - resize_map.astype(np.float64)) / CEILING_HEIGHT * 255).astype(np.uint8)
        colourmap = cv2.applyColorMap(blob_map, cv2.COLORMAP_RAINBOW)

        target_map = colourmap

        for i,tracker in enumerate(trackers):
            if tracker[2] == 3:
                continue
            path = tracker[1]
            if not path:
                continue
            cv2.circle(target_map, path[-1], 1, TRACK_COLOUR_MAP[i%4], 1)
            if tracker[0]:
                cv2.drawMarker(target_map, path[-1], TRACK_COLOUR_MAP[i%4], markerSize=8, thickness=2)
            cv2.putText(
                target_map, str(i), (path[-1][0], path[-1][1] - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.25, TRACK_COLOUR_MAP[i%4]
            )
            if len(path) > 1: 
                cv2.polylines(target_map, [np.array(path)], False, TRACK_COLOUR_MAP[i%4])

        cv2.line(target_map, (0, UPSAMPLE_HEIGHT // 2), (UPSAMPLE_WIDTH, UPSAMPLE_HEIGHT // 2), (0,255,0), 1)
        framebuffer[buffer_num] = cv2.resize(target_map, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
        cv2.putText(
            framebuffer[buffer_num], str(line_count[0]), (0, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0),
            thickness=2
        )
        cv2.putText(
            framebuffer[buffer_num], str(line_count[1]), (DISPLAY_WIDTH // 2, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0),
            thickness=2
        )
        elapsed = time.time() - tic
        print('Serial Read time:', serial_read_time)
        print('Overall: {:.3f} ms, FPS: {}'.format(elapsed * 1000, int(1/elapsed) if elapsed > 0 else 0 ))
        buffer_num = (buffer_num + 1) % 2
        time.sleep(0.08)

def get_img():
    global buffer_num
    while True:
        b_num = 0
        if buffer_num == 0:
            b_num = 1

        _, frame = cv2.imencode('.jpg', framebuffer[b_num])
        frame = frame.tobytes()
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result
        #time.sleep(0.05)

@app.route('/config', methods=['POST'])
def set_config():
    global NEW_CEILING_HEIGHT
    global NEW_MIN_HEIGHT
    global NEW_SIGNAL_THRESHOLD
    global RELEARN_BG
    try:
        new_height = int(request.form['cheight'])
        new_min_height = int(request.form['minheight'])
        new_signal_threshold = int(request.form['sigthres'])
        if new_height == CEILING_HEIGHT and new_min_height == MIN_HEIGHT and new_signal_threshold == SIGNAL_THRESHOLD:
            return redirect(url_for('index'))
    except:
        return redirect(url_for('index'))

    if not config_update.is_set():
        if new_height != CEILING_HEIGHT:
            RELEARN_BG = True
        NEW_CEILING_HEIGHT = new_height
        NEW_MIN_HEIGHT = new_min_height
        NEW_SIGNAL_THRESHOLD = new_signal_threshold
        config_update.set()
        while config_update.is_set():
            pass
    return redirect(url_for('index'))

@app.route('/video_feed')
def video_feed():
    #Video streaming route. Put this in the src attribute of an img tag
    return Response(get_img(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/')
def index():
    global CEILING_HEIGHT
    global MIN_HEIGHT
    global SIGNAL_THRESHOLD
    """Video streaming home page."""
    return render_template('index.html', ceil_height=CEILING_HEIGHT, min_height=MIN_HEIGHT, signal_threshold=SIGNAL_THRESHOLD)

if __name__ == '__main__':
    main_thread = threading.Thread(target=main)
    main_thread.daemon = True
    main_thread.start()

    app.run(debug=True, host='0.0.0.0', use_reloader=False)
