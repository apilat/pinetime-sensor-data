import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
import math
import json

axis = []
data = [[], [], []]
for line in open(0):
    time, _, x, y, z = line.split()
    time = datetime.fromtimestamp(float(time))
    x, y, z = map(float, (x, y, z))
    axis.append(time)
    data[0].append(x)
    data[1].append(y)
    data[2].append(z)
axis = np.array(axis)
data = [np.array(x) for x in data]

def deltas(data):
    return data - np.roll(data,-1)

def aggregate(data, k):
    data = data.copy()
    data.resize((len(data) + k - 1) // k * k)
    return data.reshape((-1,k)).sum(axis=1) / k

interval = 1
#for i, a in ((0, "x"), (1, "y"), (2, "z")):
for i, a in ((2, "z"),):
    plt.plot(axis[::interval], aggregate(data[i], interval), label=a)
    #plt.plot(axis, deltas(data[i]), label=a)

#abs_deltas = np.array([math.hypot(*ds) for ds in zip(*map(deltas, data))])
#plt.plot(axis[::interval], aggregate(abs_deltas, interval), label="agg")

plt.legend()
plt.show()
