import time
import random
import socket
import struct

from threading import Thread
import logging

logger = logging.getLogger(__name__)


class SSDP:
    def __init__(self, ip, port, mac):
        self._ip = ip
        self._port = port
        self._mac = mac

        self._search_running = False
        self._broadcast_running = False

    def start(self):
        self._search_running = True
        self._broadcast_running = True

        self.search_thread = Thread(
            target=self.search, args=(self._ip, self._port, self._mac)
        )
        self.broadcast_thread = Thread(
            target=self.broadcast, args=(self._ip, self._port, self._mac)
        )

        self.search_thread.start()
        self.broadcast_thread.start()

    def shutdown(self):
        self._search_running = False
        self._broadcast_running = False

        logger.info("Waiting for ssdp threads")
        self.search_thread.join()
        self.broadcast_thread.join()

    def search(self, ip, port, mac):
        ssdp_addr = "239.255.255.250"
        ssdp_port = 1900
        multicast_group_c = ssdp_addr
        server_address = ("", ssdp_port)
        response_message = (
            "HTTP/1.1 200 OK\r\nHOST: 239.255.255.250:1900\r\nEXT:\r\nCACHE-CONTROL: max-age=100\r\nLOCATION: http://"
            + ip
            + ":"
            + str(port)
            + "/description.xml\r\nSERVER: Linux/3.14.0 UPnP/1.0 IpBridge/1.20.0\r\nhue-bridgeid: "
            + (mac[:6] + "FFFE" + mac[6:]).upper()
            + "\r\n"
        )
        custom_response_message = {
            0: {
                "st": "upnp:rootdevice",
                "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac + "::upnp:rootdevice",
            },
            1: {
                "st": "uuid:2f402f80-da50-11e1-9b23-" + mac,
                "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac,
            },
            2: {
                "st": "urn:schemas-upnp-org:device:basic:1",
                "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac,
            },
        }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(server_address)

        group = socket.inet_aton(multicast_group_c)
        mreq = struct.pack("4sL", group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        logger.info("Starting ssdp search...")

        while self._search_running:
            data, address = sock.recvfrom(1024)
            data = data.decode("utf-8")
            if data[0:19] == "M-SEARCH * HTTP/1.1":
                if data.find("ssdp:discover") != -1:
                    time.sleep(random.randrange(1, 10) / 10)
                    logger.debug("Sending M-Search response to %s", address[0])
                    for x in range(3):
                        sock.sendto(
                            bytes(
                                response_message
                                + "ST: "
                                + custom_response_message[x]["st"]
                                + "\r\nUSN: "
                                + custom_response_message[x]["usn"]
                                + "\r\n\r\n",
                                "utf8",
                            ),
                            address,
                        )
            time.sleep(0.5)

    def broadcast(self, ip, port, mac):
        ssdp_addr = "239.255.255.250"
        ssdp_port = 1900
        msearch_interval = 2
        multicast_group_s = (ssdp_addr, ssdp_port)
        message = (
            "NOTIFY * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nCACHE-CONTROL: max-age=100\r\nLOCATION: http://"
            + ip
            + ":"
            + str(port)
            + "/description.xml\r\nSERVER: Linux/3.14.0 UPnP/1.0 IpBridge/1.20.0\r\nNTS: ssdp:alive\r\nhue-bridgeid: "
            + (mac[:6] + "FFFE" + mac[6:]).upper()
            + "\r\n"
        )
        custom_message = {
            0: {
                "nt": "upnp:rootdevice",
                "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac + "::upnp:rootdevice",
            },
            1: {
                "nt": "uuid:2f402f80-da50-11e1-9b23-" + mac,
                "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac,
            },
            2: {
                "nt": "urn:schemas-upnp-org:device:basic:1",
                "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac,
            },
        }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(msearch_interval + 0.5)
        ttl = struct.pack("b", 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

        logger.info("Starting ssdp broadcast...")

        while self._broadcast_running:
            for x in range(3):
                sock.sendto(
                    bytes(
                        message
                        + "NT: "
                        + custom_message[x]["nt"]
                        + "\r\nUSN: "
                        + custom_message[x]["usn"]
                        + "\r\n\r\n",
                        "utf8",
                    ),
                    multicast_group_s,
                )
                sock.sendto(
                    bytes(
                        message
                        + "NT: "
                        + custom_message[x]["nt"]
                        + "\r\nUSN: "
                        + custom_message[x]["usn"]
                        + "\r\n\r\n",
                        "utf8",
                    ),
                    multicast_group_s,
                )
            time.sleep(60)
