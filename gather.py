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

DEVICE_MAC =         ['C4:0E:54:C5:A9:EA', 'DB:47:A9:51:E7:68']
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


def dbus_error(error):
    print("D-Bus call failed: ", error)
    mainloop.quit()

def start_adapter(path):
    obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
    obj.StartDiscovery(dbus_interface=ADAPTER_IFACE)

def device_connected(path):
    for sv in [sv for sv in services if sv.startswith(path)]:
        obj = bus.get_object(BLUEZ_SERVICE_NAME, sv)
        notifying = obj.Get(GATT_CHRC_IFACE, "Notifying", dbus_interface=DBUS_PROP_IFACE)
        if not notifying:
            print(f"{path} restarting notifications")
            obj.StartNotify(dbus_interface=GATT_CHRC_IFACE)

def start_device(path):
    def try_reconnect(path):
        def reconnect_failed(error, path):
            timeout = 15
            print(f"{path} connection failed retrying in {timeout}s: {error}")
            GLib.timeout_add(timeout * 1000, lambda path=path: try_reconnect(path))

        print(f"{path} trying to reconnect")
        obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
        obj.Connect(reply_handler=lambda:(),
                error_handler=lambda error: reconnect_failed(error, path),
                dbus_interface=DEVICE_IFACE)

    def conn_changed(val, path):
        if val:
            print(f"{path} connected")
            device_connected(path)
        else:
            print(f"{path} disconnected")
            try_reconnect(path)

    def prop_changed(iface, changed_props, invalidated_props, path):
        if "Connected" in changed_props:
            conn_changed(changed_props["Connected"], path)

    obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
    obj.connect_to_signal("PropertiesChanged", prop_changed, path_keyword='path')
    conn = obj.Get(DEVICE_IFACE, "Connected", dbus_interface=DBUS_PROP_IFACE)
    conn_changed(conn, path)

def start_service(path):
    def motion_changed(iface, changed_props, invalidated_props, path):
        if "Value" in changed_props:
            x, y, z = struct.unpack("<hhh", bytes(changed_props["Value"]))
            msg = f"{path} {time.time():.6f} {x:5} {y:5} {z:5}\n"
            print(msg, end='')
            motion_log.write(msg)
            motion_log.flush()

    obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
    obj.connect_to_signal("PropertiesChanged", motion_changed, path_keyword='path')
    obj.StartNotify(dbus_interface=GATT_CHRC_IFACE)

def interfaces_added(path, ifaces):
    global adapters, devices, services
    if ADAPTER_IFACE in ifaces:
        adapters.append(path)
        start_adapter(path)
    if DEVICE_IFACE in ifaces and ifaces[DEVICE_IFACE]["Address"] in DEVICE_MAC:
        devices.append(path)
        start_device(path)
    if GATT_CHRC_IFACE in ifaces and ifaces[GATT_CHRC_IFACE]["UUID"] == MOTION_CHRC_UUID:
        services.append(path)
        start_service(path)

def interfaces_removed(path, ifaces):
    global adapters, devices, services
    if ADAPTER_IFACE in ifaces and path in adapters:
        adapters.remove(path)
    if DEVICE_IFACE in ifaces and path in devices:
        devices.remove(path)
    if GATT_CHRC_IFACE in ifaces and path in services:
        services.remove(path)

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

    mainloop.run()

if __name__ == '__main__':
    main()
