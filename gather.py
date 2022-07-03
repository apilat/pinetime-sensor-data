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
MOTION_SVC_UUID =    '00030000-78fc-48fe-8e23-433b3a1942d0'
MOTION_CHRC_UUID =   '00030002-78fc-48fe-8e23-433b3a1942d0'


bus = None
mainloop = None
adapters = []
devices = []
services = []

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
        print("DEV", path, changed_props, invalidated_props)

    obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
    obj.connect_to_signal("PropertiesChanged", prop_changed, path_keyword='path')
    conn = obj.Get(DEVICE_IFACE, "Connected", dbus_interface=DBUS_PROP_IFACE)
    conn_changed(conn, path)

def start_service(path):
    def value_changed(val, path):
        x, y, z = struct.unpack("<hhh", bytes(val))
        msg = f"{time.time():.6f} {path} {x:5} {y:5} {z:5}\n"
        #print(msg, end='')
        motion_log.write(msg)
        motion_log.flush()

    def notifying_changed(val, path):
        if val:
            log(f"{path} started notifying")
        else:
            log(f"{path} stopped notifying")
            if path not in services:
                log(f"{path} disappeared, not starting notify")
                return
            obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
            obj.StartNotify(dbus_interface=GATT_CHRC_IFACE)

    def motion_changed(iface, changed_props, invalidated_props, path):
        if "Value" in changed_props:
            value_changed(changed_props["Value"], path)
        if "Notifying" in changed_props:
            notifying_changed(changed_props["Notifying"], path)
        if "Value" not in changed_props or len(changed_props) > 1:
            print("SVC", path, changed_props, invalidated_props)

    obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
    obj.connect_to_signal("PropertiesChanged", motion_changed, path_keyword='path')
    notifying = obj.Get(GATT_CHRC_IFACE, "Notifying", dbus_interface=DBUS_PROP_IFACE)
    notifying_changed(notifying, path)

def interfaces_added(path, ifaces):
    global adapters, devices, services
    if ADAPTER_IFACE in ifaces:
        adapters.append(path)
        log(f"{path} adapter discovered")
    if DEVICE_IFACE in ifaces and ifaces[DEVICE_IFACE]["Address"] in DEVICE_MAC:
        devices.append(path)
        log(f"{path} device discovered")
    if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == MOTION_CHRC_UUID:
        services.append(path)
        log(f"{path} service discovered")

def interfaces_removed(path, ifaces):
    global adapters, devices, services
    if ADAPTER_IFACE in ifaces and path in adapters:
        adapters.remove(path)
        log(f"{path} adapter removed")
    if DEVICE_IFACE in ifaces and path in devices:
        devices.remove(path)
        log(f"{path} device removed")
    if GATT_CHRC_IFACE in ifaces and path in services:
        services.remove(path)
        log(f"{path} service removed")

def log(*args, **kwargs):
    print(f"{time.time():.6f}", *args, **kwargs, file=sys.stderr)

def fix_services():
    for sv in services:
        obj = bus.get_object(BLUEZ_SERVICE_NAME, sv)


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

    query_interval = 100
    GLib.timeout_add(query_interval, query_services)

    mainloop.run()

if __name__ == '__main__':
    main()
