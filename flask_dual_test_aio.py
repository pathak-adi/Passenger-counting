import threading
from queue import Queue, Empty
import datetime
import json
import sys
import os
import json
import struct
import time

import numpy as np
import serial
import cv2
from scipy import interpolate
from flask import Flask, render_template, Response, request, redirect, url_for

np.set_printoptions(threshold=sys.maxsize, linewidth=200)

if len(sys.argv) != 3:
    print("Usage: ./flask_dual_test_aio.py <UART TTY device> <RS485 TTY device>")
    sys.exit(1)
device = sys.argv[1]
data_device = sys.argv[2]

SENSOR_IMG_WIDTH = 8 * 2
SENSOR_IMG_HEIGHT = 8
UPSAMPLE_WIDTH = 76
UPSAMPLE_HEIGHT = 36
SENSOR_IMG_ARR_SIZE = SENSOR_IMG_WIDTH * SENSOR_IMG_HEIGHT
DISPLAY_WIDTH = UPSAMPLE_WIDTH * 4
DISPLAY_HEIGHT = UPSAMPLE_HEIGHT * 4

TRACK_COLOUR_MAP = ((255, 0, 255), (255, 0, 0), (0, 255, 0), (255, 255, 0))
app = Flask(__name__)
ser = serial.Serial(device, 115200, timeout=None)
data_ser = serial.Serial(data_device, 115200, timeout=None)

framebuffer = [None, None]
buffer_num = 0
stop_now = threading.Event()
MAX_TRACKERS = 6
config_update = threading.Event()
line_count_queue = Queue()


def get_tof_conf(addr):
    ser.write(struct.pack("BBH", addr, 0, 0))
    ser.read_until(b'\x46\x46')
    resp = struct.unpack('H', ser.read(2))  # Read response
    return resp[0]


def set_tof_conf(addr, val):
    ser.write(struct.pack("BBH", addr, 1, val))
    ser.read_until(b'\x46\x46')
    resp = struct.unpack('H', ser.read(2))  # Read response
    return resp[0]


def get_ceiling_height():
    return get_tof_conf(0)


def get_min_height():
    return get_tof_conf(1)


def get_signal_threshold():
    return get_tof_conf(10)


def set_ceiling_height(height):
    resp = set_tof_conf(0, height)


def set_min_height(height):
    resp = set_tof_conf(1, height)


def set_signal_threshold(signal):
    resp = set_tof_conf(10, signal)


CEILING_HEIGHT = get_ceiling_height()
MIN_HEIGHT = get_min_height()
SIGNAL_THRESHOLD = get_signal_threshold()
NEW_CEILING_HEIGHT = CEILING_HEIGHT
NEW_MIN_HEIGHT = MIN_HEIGHT
NEW_SIGNAL_THRESHOLD = SIGNAL_THRESHOLD
RELEARN_BG = False


def sub():
    data_ser.write("0".encode("UTF-8"))  # Unblock as a just in case
    while (True):
        data_ser.read_until(b'\x41\x41')
        hi, lo = struct.unpack('2B', data_ser.read(2))
        data_ser.write("0".encode("UTF-8"))
        line_count_queue.put((hi, lo))


def main():
    global buffer_num
    global CEILING_HEIGHT
    global MIN_HEIGHT
    global SIGNAL_THRESHOLD
    global NEW_CEILING_HEIGHT
    global NEW_MIN_HEIGHT
    global NEW_SIGNAL_THRESHOLD
    global RELEARN_BG
    line_count = [0, 0]

    trackers = [[0, [], 0], [0, [], 0], [0, [], 0], [0, [], 0], [0, [], 0], [0, [], 0], [0, [], 0], [0, [], 0]]
    while (True):
        if config_update.is_set():
            set_min_height(NEW_MIN_HEIGHT)
            set_ceiling_height(NEW_CEILING_HEIGHT)
            set_signal_threshold(NEW_SIGNAL_THRESHOLD)
            CEILING_HEIGHT = get_ceiling_height()
            MIN_HEIGHT = get_min_height()
            SIGNAL_THRESHOLD = get_signal_threshold()
            if RELEARN_BG:
                set_tof_conf(5, 0)
                RELEARN_BG = False
            config_update.clear()
        for tracker in trackers:
            tracker[2] += 1
            tracker[2] = min(tracker[2], 3)
        ser.write(struct.pack("BBH", 9, 1, 0))
        ser.read_until(b'\x46\x46')
        ser.read(2)  # Read response
        tic = time.time()
        heightmap = np.array(struct.unpack('128h', ser.read(256)), dtype=np.int16).reshape((8, 16))

        for i in range(MAX_TRACKERS):
            # No padding required
            x, y, new, active, excluded = struct.unpack('2hBBBx', ser.read(8))
            print(x, y, new, active, excluded)
            if new:
                trackers[i][1] = []
            if active:
                trackers[i][2] = 0
            if len(trackers[i][1]) == 50:
                trackers[i][1].pop(0)
            trackers[i][0] = excluded
            trackers[i][1].append((int(x), int(y)))
        try:
            while not line_count_queue.empty():
                hi, lo = line_count_queue.get_nowait()
                line_count[0] += hi
                line_count[1] += lo
        except Empty:
            pass

        heightmap = np.maximum(np.minimum(CEILING_HEIGHT, heightmap), 0)
        f = interpolate.interp2d(np.arange(SENSOR_IMG_WIDTH), np.arange(SENSOR_IMG_HEIGHT), heightmap, kind='linear')
        resize_map = f(np.arange(0, SENSOR_IMG_WIDTH, SENSOR_IMG_WIDTH / UPSAMPLE_WIDTH),
                       np.arange(0, SENSOR_IMG_HEIGHT, SENSOR_IMG_HEIGHT / UPSAMPLE_HEIGHT))
        blob_map = ((CEILING_HEIGHT - resize_map.astype(np.float64)) / CEILING_HEIGHT * 255).astype(np.uint8)
        colourmap = cv2.applyColorMap(blob_map, cv2.COLORMAP_RAINBOW)

        target_map = colourmap

        for i, tracker in enumerate(trackers):
            if tracker[2] == 3:
                continue
            path = tracker[1]
            if not path:
                continue
            cv2.circle(target_map, path[-1], 1, TRACK_COLOUR_MAP[i % 4], 1)
            if tracker[0]:
                cv2.drawMarker(target_map, path[-1], TRACK_COLOUR_MAP[i % 4], markerSize=8, thickness=2)
            cv2.putText(
                target_map, str(i), (path[-1][0], path[-1][1] - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.25, TRACK_COLOUR_MAP[i % 4]
            )
            if len(path) > 1:
                cv2.polylines(target_map, [np.array(path)], False, TRACK_COLOUR_MAP[i % 4])

        cv2.line(target_map, (0, UPSAMPLE_HEIGHT // 2), (UPSAMPLE_WIDTH, UPSAMPLE_HEIGHT // 2), (0, 255, 0), 1)
        framebuffer[buffer_num] = cv2.resize(target_map, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
        cv2.putText(
            framebuffer[buffer_num], str(line_count[0]), (0, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0),
            thickness=2
        )
        cv2.putText(
            framebuffer[buffer_num], str(line_count[1]), (200, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0),
            thickness=2
        )
        print('Overall', time.time() - tic)
        buffer_num = (buffer_num + 1) % 2


def get_img():
    global buffer_num
    while True:
        b_num = 0
        if buffer_num == 0:
            b_num = 1

        _, frame = cv2.imencode('.jpg', framebuffer[b_num])
        frame = frame.tobytes()
        yield (
                    b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result
        time.sleep(0.05)


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
    # Video streaming route. Put this in the src attribute of an img tag
    return Response(get_img(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/')
def index():
    global CEILING_HEIGHT
    global MIN_HEIGHT
    global SIGNAL_THRESHOLD
    return render_template('index.html', ceil_height=CEILING_HEIGHT, min_height=MIN_HEIGHT,
                           signal_threshold=SIGNAL_THRESHOLD)


if __name__ == '__main__':
    sub_thread = threading.Thread(target=sub)
    sub_thread.daemon = True
    sub_thread.start()
    main_thread = threading.Thread(target=main)
    main_thread.daemon = True
    main_thread.start()

    app.run(debug=True, host='0.0.0.0', use_reloader=False)
