import sys
import struct
import time
from collections import namedtuple

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from threading import Thread


BLUEZ_SERVICE_NAME = 'org.bluez'
DBUS_OM_IFACE =      'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE =    'org.freedesktop.DBus.Properties'

ADAPTER_IFACE =      'org.bluez.Adapter1'
DEVICE_IFACE =       'org.bluez.Device1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE =    'org.bluez.GattCharacteristic1'

DEVICE_MAC =         [
        'C4:0E:54:C5:A9:EA',
        #'DB:47:A9:51:E7:68',
    ]
MOTION_CHRC_UUID         = '00030002-78fc-48fe-8e23-433b3a1942d0'
HEARTRATE_SVC_UUID       = '0000180d-0000-1000-8000-00805f9b34fb'
HEARTRATE_CHRC_UUID      = '00002a37-0000-1000-8000-00805f9b34fb'
HEARTRATE_CTRL_CHRC_UUID = '00050001-78fc-48fe-8e23-433b3a1942d0'

bus = None
log_file = None

def log(*args, **kwargs):
    print(f"{time.time():.6f}", *args, **kwargs, file=log_file)
    print(*args, **kwargs, file=sys.stderr)

def reset_connection(hard):
    log(f"trying to reset connection {hard=}")
    om_iface = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE)
    if hard:
        for path, ifaces in om_iface.GetManagedObjects().items():
            if ADAPTER_IFACE in ifaces:
                obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
                try:
                    obj.StartDiscovery(dbus_interface=ADAPTER_IFACE)
                    log(f"starting discovery on adapter {path}")
                except Exception as exc:
                    log(f"starting discovery on adapter {path} failed: {exc}")
        time.sleep(10)

    for path, ifaces in om_iface.GetManagedObjects().items():
        if DEVICE_IFACE in ifaces and ifaces[DEVICE_IFACE]["Address"] in DEVICE_MAC:
            obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
            conn = obj.Get(DEVICE_IFACE, "Connected", dbus_interface=DBUS_PROP_IFACE)
            if conn:
                if hard:
                    try:
                        obj.Disconnect(dbus_interface=DEVICE_IFACE)
                        log(f"disconnecting from device {path}")
                        time.sleep(4)
                    except Exception as exc:
                        log(f"disconnecting from device {path} failed: {exc}")
            else:
                try:
                    log(f"connecting to device {path}")
                    obj.Connect(dbus_interface=DEVICE_IFACE)
                except Exception as exc:
                    log(f"connecting to device {path} failed: {exc}")

    if hard:
        for path, ifaces in om_iface.GetManagedObjects().items():
            if ADAPTER_IFACE in ifaces:
                obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
                try:
                    obj.StopDiscovery(dbus_interface=ADAPTER_IFACE)
                    log(f"stopping discovery on adapter {path}")
                except Exception as exc:
                    log(f"stopping discovery on adapter {path} failed: {exc}")

    return True

def query_motion():
    log(f"trying to read motion")
    om_iface = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE)
    for path, ifaces in om_iface.GetManagedObjects().items():
        if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == MOTION_CHRC_UUID:
            try:
                log(f"reading motion from characteristic {path}")
                obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
                val = obj.ReadValue({}, dbus_interface=GATT_CHRC_IFACE)
                x, y, z = struct.unpack("<hhh", bytes(val))
                log(f"! motion {path} {x} {y} {z}")
            except Exception as exc:
                log(f"reading motion from characteristic {path} failed: {exc}")

    return True

def query_heartrate():
    log(f"trying to read heartrate")
    om_iface = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE)
    services = []
    for path, ifaces in om_iface.GetManagedObjects().items():
        if GATT_SERVICE_IFACE in ifaces and ifaces[GATT_SERVICE_IFACE]["UUID"] == HEARTRATE_SVC_UUID:
            services.append([path, None, None])
        if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == HEARTRATE_CHRC_UUID:
            service_path = bus.get_object(BLUEZ_SERVICE_NAME, path) \
                    .Get(GATT_CHRC_IFACE, "Service", dbus_interface=DBUS_PROP_IFACE)
            for service in services:
                if service[0] == service_path:
                    service[1] = path
        if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == HEARTRATE_CTRL_CHRC_UUID:
            service_path = bus.get_object(BLUEZ_SERVICE_NAME, path) \
                    .Get(GATT_CHRC_IFACE, "Service", dbus_interface=DBUS_PROP_IFACE)
            for service in services:
                if service[0] == service_path:
                    service[2] = path

    for _, char_path, ctrl_path in services:
        if path is None or ctrl_path is None:
            continue

        try:
            log(f"enabling heart rate collection on characteristic {char_path} with control {ctrl_path}")
            char_obj = bus.get_object(BLUEZ_SERVICE_NAME, char_path)
            ctrl_obj = bus.get_object(BLUEZ_SERVICE_NAME, ctrl_path)
            ctrl_obj.WriteValue(b"\x01", {}, dbus_interface=GATT_CHRC_IFACE)
            time.sleep(16)
            log(f"reading heart rate from characteristic {char_path} with control {ctrl_path}")
            val = char_obj.ReadValue({}, dbus_interface=GATT_CHRC_IFACE)
            hr = int(val[1])
            log(f"! hr {char_path} {ctrl_path} {hr}")
            ctrl_obj.WriteValue(b"\x00", {}, dbus_interface=GATT_CHRC_IFACE)
        except Exception as exc:
            log(f"reading heart rate from characteristic {char_path} with control {ctrl_path} failed: {exc}")

    return True

def loop(timeout, fn):
    while True:
        fn()
        time.sleep(timeout)

if __name__ == "__main__":
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    log_file = open("data/log", "a")
    mainloop = GLib.MainLoop()

    reset_connection(True)
    Thread(target=lambda: loop(5, lambda:reset_connection(False))).start()
    Thread(target=lambda: loop(300, lambda:reset_connection(True))).start()
    Thread(target=lambda: loop(3, query_motion)).start()
    Thread(target=lambda: loop(10, query_heartrate)).start()

    mainloop.run()
