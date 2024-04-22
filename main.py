#!/usr/bin/python3

import hid
import sacn
import layout
import time
import queue
import threading
import platform

RK61_PLUS_VID = 0x258a
RK61_PLUS_PID = 0xf8
IP = "127.0.0.84"

receiver = sacn.sACNreceiver(IP)
rk61 = hid.enumerate(RK61_PLUS_VID, RK61_PLUS_PID)
h = hid.device()
packets_queue = queue.Queue(5)
packet_sender_stop_event = threading.Event()
last_packets: list[bytes] = []
receiver_started = False
device_founded = True


@receiver.listen_on('universe', universe=1)
def sacn_callback(packet: sacn.DataPacket):
    global last_packets

    dmx_data = packet.dmxData
    colors = []

    for i in range(0, min(16 * 6 * 3, len(dmx_data)), 3):
        colors.append((dmx_data[i], dmx_data[i + 1], dmx_data[i + 2]))

    colors_dict = layout.colors_list_to_keys_dict(colors)
    packets = layout.colors_dict_to_usb_packets(colors_dict)

    # print("sending packets:")
    for packet in packets:
        if packets_queue.not_full:
            packets_queue.put(packet)

    last_packets = packets


def usb_packet_sender():
    while not packet_sender_stop_event.is_set():
        try:
            packet = packets_queue.get()
            # print(packet.hex(" "))
            h.send_feature_report(packet)
        except queue.Empty:
            if packet_sender_stop_event.is_set():
                break
            else:
                # resend last packets
                for packet in last_packets:
                    h.send_feature_report(packet)


def check_rk():
    global rk61, rk_path, receiver_started, device_founded
    rk61 = hid.enumerate(RK61_PLUS_VID, RK61_PLUS_PID)
    rk_path = None

    if platform.system() == "Windows":
        for interface in rk61:
            if interface['usage_page'] == 65280:
                rk_path = interface['path']
                device_founded = True
                # break
    elif platform.system() == "Linux":
        if len(rk61) >= 2:
            rk_path = rk61[1]['path']
            device_founded = True

    if rk_path is None:
        print("rk61-plus not found, listening")
        receiver_started = False
        device_founded = False
        receiver.remove_listener(sacn_callback)
        time.sleep(3)


if __name__ == "__main__":
    rk_path = None

    while rk_path is None:
        check_rk()

    packet_sender_thread = threading.Thread(target=usb_packet_sender, daemon=True)
    packet_sender_thread.start()

    receiver_started = True

    print(f"sACN listening on {IP}")

    h.open_path(rk_path)
    h.set_nonblocking(1)

    receiver.start()

    try:
        while True:
            check_rk()
            time.sleep(1.5)

            if not receiver_started and device_founded:
                h = hid.device()
                h.open_path(rk_path)
                h.set_nonblocking(1)

                print(f"sACN listening on {IP}")
                receiver_started = True
                receiver.register_listener('universe', universe=1, func=sacn_callback)


    except KeyboardInterrupt:
        print("Exiting...")
        receiver.stop()
        packet_sender_stop_event.set()
