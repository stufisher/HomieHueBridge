#!/usr/bin/python
import os
import time
import json
import socket
import random
from http.server import HTTPServer
from datetime import datetime, timedelta
from threading import Thread
from collections import defaultdict
from uuid import getnode as get_mac
import logging

import requests

from homie_hue_bridge.HueSSDP import SSDP
from homie_hue_bridge.HueHTTPServer import HueHTTPServer


logger = logging.getLogger(__name__)

# Stolen from:
# https://github.com/mariusmotea/HueBridgeEmulator
# https://github.com/mariusmotea/diyHue/blob/master/BridgeEmulator/HueEmulator3.py


def get_ip_address(listen_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", listen_port))
    return s.getsockname()[0]


def get_unique_id():
    return (
        ":".join("%02x" % random.randint(0, 255) for x in range(6))
        + "-"
        + str(random.randint(0, 12))
    )


class HueBridgeEmulator:
    run_service = True
    _light_request_callbacks = []

    def __init__(self, ip, port, mac, config_file="config.json"):
        self._ip = ip
        self._port = port
        self._mac = mac
        self._config_file = config_file

        self.sensors_state = {}
        self.bridge_config = defaultdict(lambda: defaultdict(str))

        # load config files
        try:
            with open(self._config_file, "r") as fp:
                self.bridge_config = json.load(fp)
                logger.info("Config loaded")
        except Exception:
            logger.exception("Config file was not loaded")

        self.generate_sensors_state()

        self.bridge_config["config"]["ipaddress"] = self._ip
        self.bridge_config["config"]["mac"] = (
            mac[0]
            + mac[1]
            + ":"
            + mac[2]
            + mac[3]
            + ":"
            + mac[4]
            + mac[5]
            + ":"
            + mac[6]
            + mac[7]
            + ":"
            + mac[8]
            + mac[9]
            + ":"
            + mac[10]
            + mac[11]
        )
        self.bridge_config["config"]["bridgeid"] = mac.upper()

    def start(self):
        self._scheduler_thread = Thread(target=self.scheduler_processor)
        self._scheduler_thread.start()

        HueHTTPServer.set_parent(self)
        self.httpd = HTTPServer(("", self._port), HueHTTPServer)
        logger.info("Starting httpd on %d..." % self._port)
        self._server_thread = Thread(target=self.httpd.serve_forever)
        self._server_thread.start()

    def shutdown(self):
        self.run_service = False
        logger.info("Waiting for scheduler thread to end")
        self._scheduler_thread.join()

        self.httpd.shutdown()
        self._server_thread.join()

        self.save_config()
        logger.info("Config saved")

    def generate_sensors_state(self):
        for sensor in self.bridge_config["sensors"]:
            if (
                sensor not in self.sensors_state
                and "state" in self.bridge_config["sensors"][sensor]
            ):
                self.sensors_state[sensor] = {"state": {}}
                for key in self.bridge_config["sensors"][sensor]["state"].keys():
                    if key in ["lastupdated", "presence", "flag", "dark", "status"]:
                        self.sensors_state[sensor]["state"].update(
                            {key: "2017-01-01T00:00:00"}
                        )

    def get_devices(self):
        return self.bridge_config["lights"]

    def add_device(self, did, dtype, name):
        device_db = None

        with open(f"{os.path.dirname(__file__)}/data/device_types.json") as db_file:
            device_db = json.load(db_file)

        if device_db:
            if dtype in device_db:
                device = device_db[dtype]["data"]
                device["name"] = name
                device["uniqueid"] = get_unique_id()

                self.bridge_config["lights"][did] = device
                return device

            else:
                raise KeyError(f"Could not find device type {dtype}")

        else:
            raise OSError("Could not open device db")

    def get_properties(self, dtype):
        device_db = None

        with open(f"{os.path.dirname(__file__)}/data/device_types.json") as db_file:
            device_db = json.load(db_file)

        if device_db:
            if dtype in device_db:
                return device_db[dtype]["properties"]

            else:
                raise KeyError(f"Could not find device type {dtype}")

        else:
            raise OSError("Could not open device db")

    def remove_device(self, did):
        if did in self.bridge_config["lights"]:
            del self.bridge_config["lights"][did]

        else:
            raise KeyError(f"No such device {did}")

    def save_config(self):
        with open(self._config_file, "w") as fp:
            json.dump(
                self.bridge_config, fp, sort_keys=True, indent=4, separators=(",", ": ")
            )

    def scheduler_processor(self):
        while self.run_service:
            for schedule in self.bridge_config["schedules"].keys():
                if self.bridge_config["schedules"][schedule]["status"] == "enabled":
                    if self.bridge_config["schedules"][schedule][
                        "localtime"
                    ].startswith("W"):
                        pices = self.bridge_config["schedules"][schedule][
                            "localtime"
                        ].split("/T")
                        if int(pices[0][1:]) & (1 << 6 - datetime.today().weekday()):
                            if pices[1] == datetime.now().strftime("%H:%M:%S"):
                                logger.info("Execute schedule: %s", schedule)
                                self.send_request(
                                    self.bridge_config["schedules"][schedule][
                                        "command"
                                    ]["address"],
                                    self.bridge_config["schedules"][schedule][
                                        "command"
                                    ]["method"],
                                    json.dumps(
                                        self.bridge_config["schedules"][schedule][
                                            "command"
                                        ]["body"]
                                    ),
                                )
                    elif self.bridge_config["schedules"][schedule][
                        "localtime"
                    ].startswith("PT"):
                        if self.bridge_config["schedules"][schedule][
                            "starttime"
                        ] == datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"):
                            logger.info("Execute timer: %s", schedule)
                            self.send_request(
                                self.bridge_config["schedules"][schedule]["command"][
                                    "address"
                                ],
                                self.bridge_config["schedules"][schedule]["command"][
                                    "method"
                                ],
                                json.dumps(
                                    self.bridge_config["schedules"][schedule][
                                        "command"
                                    ]["body"]
                                ),
                            )
                            self.bridge_config["schedules"][schedule][
                                "status"
                            ] = "disabled"
                    else:
                        if self.bridge_config["schedules"][schedule][
                            "localtime"
                        ] == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                            logger.info("Execute schedule: %s", schedule)
                            self.send_request(
                                self.bridge_config["schedules"][schedule]["command"][
                                    "address"
                                ],
                                self.bridge_config["schedules"][schedule]["command"][
                                    "method"
                                ],
                                json.dumps(
                                    self.bridge_config["schedules"][schedule][
                                        "command"
                                    ]["body"]
                                ),
                            )
            if (
                datetime.now().strftime("%M:%S") == "00:00"
            ):  # auto save configuration every hour
                self.save_config()
            self.rules_processor(True)
            time.sleep(1)

    def rules_processor(self, scheduler=False):
        self.bridge_config["config"]["localtime"] = datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S"
        )  # required for operator dx to address /config/localtime
        for rule in self.bridge_config["rules"].keys():
            if self.bridge_config["rules"][rule]["status"] == "enabled":
                execute = True
                for condition in self.bridge_config["rules"][rule]["conditions"]:
                    url_pices = condition["address"].split("/")
                    if condition["operator"] == "eq":
                        if condition["value"] == "true":
                            if not self.bridge_config[url_pices[1]][url_pices[2]][
                                url_pices[3]
                            ][url_pices[4]]:
                                execute = False
                        elif condition["value"] == "false":
                            if self.bridge_config[url_pices[1]][url_pices[2]][
                                url_pices[3]
                            ][url_pices[4]]:
                                execute = False
                        else:
                            if not int(
                                self.bridge_config[url_pices[1]][url_pices[2]][
                                    url_pices[3]
                                ][url_pices[4]]
                            ) == int(condition["value"]):
                                execute = False
                    elif condition["operator"] == "gt":
                        if not int(
                            self.bridge_config[url_pices[1]][url_pices[2]][
                                url_pices[3]
                            ][url_pices[4]]
                        ) > int(condition["value"]):
                            execute = False
                    elif condition["operator"] == "lt":
                        if int(
                            not self.bridge_config[url_pices[1]][url_pices[2]][
                                url_pices[3]
                            ][url_pices[4]]
                        ) < int(condition["value"]):
                            execute = False
                    elif condition["operator"] == "dx":
                        if not self.sensors_state[url_pices[2]][url_pices[3]][
                            url_pices[4]
                        ] == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                            execute = False
                    elif condition["operator"] == "ddx":
                        if not scheduler:
                            execute = False
                        else:
                            ddx_time = datetime.strptime(
                                condition["value"], "PT%H:%M:%S"
                            )
                            if not (
                                datetime.strptime(
                                    self.sensors_state[url_pices[2]][url_pices[3]][
                                        url_pices[4]
                                    ],
                                    "%Y-%m-%dT%H:%M:%S",
                                )
                                + timedelta(
                                    hours=ddx_time.hour,
                                    minutes=ddx_time.minute,
                                    seconds=ddx_time.second,
                                )
                            ) == datetime.now().replace(microsecond=0):
                                execute = False
                    elif condition["operator"] == "in":
                        periods = condition["value"].split("/")
                        if condition["value"][0] == "T":
                            timeStart = datetime.strptime(
                                periods[0], "T%H:%M:%S"
                            ).time()
                            timeEnd = datetime.strptime(periods[1], "T%H:%M:%S").time()
                            now_time = datetime.now().time()
                            if timeStart < timeEnd:
                                if not timeStart <= now_time <= timeEnd:
                                    execute = False
                            else:
                                if not (timeStart <= now_time or now_time <= timeEnd):
                                    execute = False

                if execute:
                    logger.info("rule %s is triggered", rule)
                    for action in self.bridge_config["rules"][rule]["actions"]:
                        Thread(
                            target=self.send_request,
                            args=[
                                "/api/"
                                + self.bridge_config["rules"][rule]["owner"]
                                + action["address"],
                                action["method"],
                                json.dumps(action["body"]),
                            ],
                        ).start()

    def send_request(self, url, method, data, timeout=3, delay=0):
        if delay != 0:
            time.sleep(delay)
        if not url.startswith("http"):
            url = "http://127.0.0.1" + url
        head = {"Content-type": "application/json"}
        if method == "POST":
            if type(data) is dict:
                response = requests.post(url, data=data)
            else:
                response = requests.post(
                    url, data=bytes(data, "utf8"), timeout=timeout, headers=head
                )
            return response.text
        elif method == "PUT":
            response = requests.put(
                url, data=bytes(data, "utf8"), timeout=timeout, headers=head
            )
            return response.text
        elif method == "GET":
            response = requests.get(url, timeout=timeout, headers=head)
            return response.text

    def add_light_callbacks(self, fn):
        if fn not in self._light_request_callbacks:
            self._light_request_callbacks.append(fn)

    def send_light_request(self, light, data):
        # print("Update light " + light + " with " + json.dumps(data))
        for fn in self._light_request_callbacks:
            fn(light, data.get("on"), data.get("ct"), data.get("bri"))

    def set_light_state(self, light, property, value):
        self.bridge_config["lights"][light]["state"]
        if self.bridge_config["lights"][light]:
            if property in self.bridge_config["lights"][light]["state"]:
                logger.info("Updating %s %s %s", light, property, value)
                self.bridge_config["lights"][light]["state"][property] = value
            else:
                logger.warning(
                    "Trying to update none existant light property: %s", property
                )

        else:
            logger.warning("Trying to update none existant light: %s", light)

    def get_configured_lights(self):
        ret = {}
        for lid, light in self.bridge_config.get("lights", {}).items():
            ret[lid] = {"name": light["name"], "on": light["state"]["on"]}

        return ret

    def update_group_stats(
        self, light
    ):  # set group stats based on lights status in that group
        for group in self.bridge_config["groups"]:
            if light in self.bridge_config["groups"][group]["lights"]:
                for key, value in self.bridge_config["lights"][light]["state"].items():
                    if key not in ["on", "reachable"]:
                        self.bridge_config["groups"][group]["action"][key] = value
                any_on = False
                all_on = True
                bri = 0
                for group_light in self.bridge_config["groups"][group]["lights"]:
                    if self.bridge_config["lights"][light]["state"]["on"] == True:
                        any_on = True
                    else:
                        all_on = False
                    bri += self.bridge_config["lights"][light]["state"]["bri"]
                avg_bri = bri / len(self.bridge_config["groups"][group]["lights"])
                self.bridge_config["groups"][group]["state"] = {
                    "any_on": any_on,
                    "all_on": all_on,
                    "bri": avg_bri,
                    "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
                }

    def scan_for_lights(self):  # scan for ESP8266 lights and strips
        logger.info(
            "Scan for lights: %s",
            json.dumps(
                [{"success": {"/lights": "Searching for new devices"}}],
                sort_keys=True,
                indent=4,
                separators=(",", ": "),
            ),
        )

    def description(self):
        return (
            """<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>http://"""
            + self._ip
            + """:"""
            + str(self._port)
            + """/</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>HH Emulator ("""
            + self._ip
            + """)</friendlyName>
<manufacturer>Signify</manufacturer>
<manufacturerURL>http://www.philips.com</manufacturerURL>
<modelDescription>Philips hue Personal Wireless Lighting</modelDescription>
<modelName>Philips hue bridge 2015</modelName>
<modelNumber>BSB002</modelNumber>
<modelURL>http://www.meethue.com</modelURL>
<serialNumber>"""
            + self._mac
            + """</serialNumber>
<UDN>uuid:2f402f80-da50-11e1-9b23-"""
            + self._mac
            + """</UDN>
<presentationURL>index.html</presentationURL>
<iconList>
<icon>
<mimetype>image/png</mimetype>
<height>48</height>
<width>48</width>
<depth>24</depth>
<url>hue_logo_0.png</url>
</icon>
</iconList>
</device>
</root>
"""
        )
