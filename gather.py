import sys
import struct
import time
from collections import namedtuple

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


BLUEZ_SERVICE_NAME = 'org.bluez'
DBUS_OM_IFACE =      'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE =    'org.freedesktop.DBus.Properties'

ADAPTER_IFACE =      'org.bluez.Adapter1'
DEVICE_IFACE =       'org.bluez.Device1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE =    'org.bluez.GattCharacteristic1'

DEVICE_MAC =         [
        'C4:0E:54:C5:A9:EA',
        'DB:47:A9:51:E7:68',
    ]
MOTION_CHRC_UUID         = '00030002-78fc-48fe-8e23-433b3a1942d0'
HEARTRATE_SVC_UUID       = '0000180d-0000-1000-8000-00805f9b34fb'
HEARTRATE_CHRC_UUID      = '00002a37-0000-1000-8000-00805f9b34fb'
HEARTRATE_CTRL_CHRC_UUID = '00050001-78fc-48fe-8e23-433b3a1942d0'


bus = None
mainloop = None
adapters = []
devices = []
motion_services = []
heartrate_services = []

motion_chrc = None
device_conn_chrc = None
motion_log = None


def start_adapter(path):
    log(f"{path} starting discovery")
    obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
    obj.StartDiscovery(dbus_interface=ADAPTER_IFACE)

def start_device(path):
    def try_reconnect(path):
        if path not in devices:
            log(f"{path} disappeared, not reconnecting")
            return
        def reconnect_failed(error, path):
            timeout = 15
            log(f"{path} connection failed retrying in {timeout}s: {error}")
            GLib.timeout_add(timeout * 1000, lambda path=path: try_reconnect(path))

        log(f"{path} trying to reconnect")
        obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
        obj.Connect(reply_handler=lambda:(),
                error_handler=lambda error: reconnect_failed(error, path),
                dbus_interface=DEVICE_IFACE)

    def conn_changed(val, path):
        if val:
            log(f"{path} connected")
        else:
            log(f"{path} disconnected")
            try_reconnect(path)

    def prop_changed(iface, changed_props, invalidated_props, path):
        if "Connected" in changed_props:
            conn_changed(changed_props["Connected"], path)

    obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
    obj.connect_to_signal("PropertiesChanged", prop_changed, path_keyword='path')
    conn = obj.Get(DEVICE_IFACE, "Connected", dbus_interface=DBUS_PROP_IFACE)
    conn_changed(conn, path)

def start_service(path):
    pass

def interfaces_added(path, ifaces):
    global adapters, devices, motion_services, heartrate_services
    if ADAPTER_IFACE in ifaces:
        adapters.append(path)
        log(f"{path} adapter discovered")
        start_adapter(path)
    if DEVICE_IFACE in ifaces and ifaces[DEVICE_IFACE]["Address"] in DEVICE_MAC:
        devices.append(path)
        log(f"{path} device discovered")
        start_device(path)
    if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == MOTION_CHRC_UUID:
        motion_services.append(path)
        log(f"{path} motion char discovered")
        start_service(path)

    if GATT_SERVICE_IFACE in ifaces and ifaces[GATT_SERVICE_IFACE]["UUID"] == HEARTRATE_SVC_UUID:
        log(f"{path} heartrate svc discovered")
        heartrate_services.append([path, None, None])
    if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == HEARTRATE_CHRC_UUID:
        log(f"{path} heartrate char discovered")
        for sv in heartrate_services:
            if path.startswith(sv[0]):
                sv[1] = path
    if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == HEARTRATE_CTRL_CHRC_UUID:
        log(f"{path} heartrate ctrl discovered")
        for sv in heartrate_services:
            if path.startswith(sv[0]):
                sv[2] = path

def interfaces_removed(path, ifaces):
    global adapters, devices, motion_services, heartrate_services
    if ADAPTER_IFACE in ifaces and path in adapters:
        adapters.remove(path)
        log(f"{path} adapter removed")
    if DEVICE_IFACE in ifaces and path in devices:
        devices.remove(path)
        log(f"{path} device removed")
    if GATT_CHRC_IFACE in ifaces and path in services:
        motion_services.remove(path)
        log(f"{path} motion char removed")
    if GATT_SERVICE_IFACE in ifaces and ifaces[GATT_SERVICE_IFACE]["UUID"] == HEARTRATE_SVC_UUID:
        log(f"{path} heartrate svc removed")
        heartrate_services = [x for x in heartrate_services if x[0] != path]

def log(*args, **kwargs):
    print(f"{time.time():.6f}", *args, **kwargs, file=sys.stderr)

def query_motion_services():
    for sv in motion_services:
        try:
            obj = bus.get_object(BLUEZ_SERVICE_NAME, sv)
            val = obj.ReadValue({}, dbus_interface=GATT_CHRC_IFACE)
            x, y, z = struct.unpack("<hhh", bytes(val))
            msg = f"{time.time():.6f} {sv} {x} {y} {z}\n"
            #print(msg, end='')
            motion_log.write(msg)
            motion_log.flush()
        except Exception as e:
            log(f"{sv} read failed: {e}")
    return True

def query_heartrate_services():
    for sv, char, ctrl in heartrate_services:
        try:
            char_obj = bus.get_object(BLUEZ_SERVICE_NAME, char)
            ctrl_obj = bus.get_object(BLUEZ_SERVICE_NAME, ctrl)
            ctrl_obj.WriteValue(b"\x01", {}, dbus_interface=GATT_CHRC_IFACE)
            def ready():
                val = char_obj.ReadValue({}, dbus_interface=GATT_CHRC_IFACE)
                hr = int(val[1])
                msg = f"{time.time():.6f} {sv} {hr}\n"
                print(msg, end='')
                ctrl_obj.WriteValue(b"\x00", {}, dbus_interface=GATT_CHRC_IFACE)
            GLib.timeout_add(9000, ready)
        except Exception as e:
            log(f"{sv} measure failed: {e}")
    return True

def main():
    global bus, mainloop, motion_log
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    mainloop = GLib.MainLoop()
    motion_log = open("data/motion.log", "a")

    om_iface = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE)
    om_iface.connect_to_signal("InterfacesAdded", interfaces_added)
    om_iface.connect_to_signal("InterfacesRemoved", interfaces_removed)
    for path, ifaces in om_iface.GetManagedObjects().items():
        interfaces_added(path, ifaces)

    query_motion_interval = 100
    GLib.timeout_add(query_motion_interval, query_motion_services)
    query_heartrate_interval = 15000
    GLib.timeout_add(query_heartrate_interval, query_heartrate_services)

    mainloop.run()

if __name__ == '__main__':
    main()
