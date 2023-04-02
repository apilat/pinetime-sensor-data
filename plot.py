import matplotlib.pyplot as plt
from collections import namedtuple
from datetime import datetime
import numpy as np

Datapoint = namedtuple("Datapoint", ("timestamp", "data"))

motion_data = []
hr_data = []
for line in open(0):
    if line.strip() == '': continue
    time, *msg = line.split(' ')
    if msg[0] != '!': continue
    time = float(time)
    if msg[1] == "motion":
        x, y, z = int(msg[3]), int(msg[4]), int(msg[5])
        motion_data.append(Datapoint(time, (x, y, z)))
    elif msg[1] == "hr":
        hr = int(msg[4])
        hr_data.append(Datapoint(time, hr))

def chunks(data, window=30):
    chunks = []
    cur = []
    left = window
    last = None
    for d in data:
        if last is not None:
            left -= d.timestamp - last
        last = d.timestamp
        if left < 0:
            if cur:
                chunks.append(cur)
            cur = []
            left = window
        cur.append(d)
    chunks.append(cur)
    return chunks

def process_motion(motion_data):
    xs, ys = [], []
    for ds in chunks(motion_data):
        xs.append(datetime.fromtimestamp(np.mean([d.timestamp for d in ds])))
        ys.append(np.std([d.data[1] for d in ds]))
    return xs, ys

def process_hr(hr_data):
    xs, ys = [], []
    for ds in chunks(hr_data):
        xs.append(datetime.fromtimestamp(np.mean([d.timestamp for d in ds])))
        ds = [d for d in ds if d.data != 0]
        if ds:
            ys.append(np.mean([d.data for d in ds]))
        else:
            ys.append(float('nan'))
    return xs, ys

xs, ys = process_motion(motion_data)
color = "green"
fig, ax1 = plt.subplots()
ax1.set_xlabel("Time")
ax1.set_ylabel("Relative motion", color=color)
ax1.plot(xs, ys, color=color, marker='.')

xs, ys = process_hr(hr_data)
color = "red"
ax2 = ax1.twinx()
ax2.set_ylabel("Heart rate", color=color)
ax2.plot(xs, ys, color=color, marker='.')

fig.tight_layout()
plt.show()
