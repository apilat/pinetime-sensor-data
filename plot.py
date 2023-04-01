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
    time = datetime.fromtimestamp(float(time))
    if msg[1] == "motion":
        x, y, z = int(msg[3]), int(msg[4]), int(msg[5])
        motion_data.append(Datapoint(time, y))
    elif msg[1] == "hr":
        hr = int(msg[4])
        hr_data.append(Datapoint(time, hr))

color = "green"
fig, ax1 = plt.subplots()
ax1.set_xlabel("Time")
ax1.set_ylabel("Orientation", color=color)
ax1.plot([d.timestamp for d in motion_data],
         [d.data for d in motion_data],
         color=color)

color = "red"
ax2 = ax1.twinx()
ax2.set_ylabel("Heart rate", color=color)
ax2.plot([d.timestamp for d in hr_data],
         [d.data for d in hr_data],
         color=color)

fig.tight_layout()
plt.show()
