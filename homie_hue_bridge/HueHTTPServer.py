import time
import hashlib
import logging
import json
from threading import Thread
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class HueHTTPServer(BaseHTTPRequestHandler):
    @staticmethod
    def set_parent(parent):
        HueHTTPServer._parent = parent

    def _set_headers(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        self._set_headers()
        if self.path == "/description.xml":
            self.wfile.write(bytes(self._parent.description(), "utf8"))
        else:
            url_pices = self.path.split("/")
            logger.info(url_pices)
            if len(url_pices) < 3:
                return

            if (
                url_pices[2] in self._parent.bridge_config["config"]["whitelist"]
            ):  # if username is in whitelist
                self._parent.bridge_config["config"][
                    "UTC"
                ] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                self._parent.bridge_config["config"][
                    "localtime"
                ] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                if len(url_pices) == 3:  # print entire config
                    self.wfile.write(
                        json.dumps(self._parent.bridge_config).encode("utf8")
                    )
                elif len(url_pices) == 4:  # print specified object config
                    self.wfile.write(
                        json.dumps(self._parent.bridge_config[url_pices[3]]).encode(
                            "utf8"
                        )
                    )
                elif len(url_pices) == 5:
                    if url_pices[4] == "new":  # return new lights and sensors only
                        self.wfile.write(
                            json.dumps(
                                {
                                    "lastscan": datetime.now().strftime(
                                        "%Y-%m-%dT%H:%M:%S"
                                    )
                                }
                            ).encode("utf8")
                        )
                    else:
                        self.wfile.write(
                            json.dumps(
                                self._parent.bridge_config[url_pices[3]][url_pices[4]]
                            ).encode("utf8")
                        )
                elif len(url_pices) == 6:
                    self.wfile.write(
                        json.dumps(
                            self._parent.bridge_config[url_pices[3]][url_pices[4]][
                                url_pices[5]
                            ]
                        ).encode("utf8")
                    )
            elif (
                url_pices[2] == "nouser" or url_pices[2] == "config"
            ):  # used by applications to discover the bridge
                self.wfile.write(
                    json.dumps(
                        {
                            "name": self._parent.bridge_config["config"]["name"],
                            "datastoreversion": 59,
                            "swversion": self._parent.bridge_config["config"][
                                "swversion"
                            ],
                            "apiversion": self._parent.bridge_config["config"][
                                "apiversion"
                            ],
                            "mac": self._parent.bridge_config["config"]["mac"],
                            "bridgeid": self._parent.bridge_config["config"][
                                "bridgeid"
                            ],
                            "factorynew": False,
                            "modelid": self._parent.bridge_config["config"]["modelid"],
                        }
                    ).encode("utf8")
                )
            else:  # user is not in whitelist
                self.wfile.write(
                    json.dumps(
                        [
                            {
                                "error": {
                                    "type": 1,
                                    "address": self.path,
                                    "description": "unauthorized user",
                                }
                            }
                        ]
                    ).encode("utf8")
                )

    def do_POST(self):
        self._set_headers()
        # print("in post method")
        self.data_string = self.rfile.read(int(self.headers["Content-Length"]))
        post_dictionary = json.loads(self.data_string)
        url_pices = self.path.split("/")
        # print(self.path)
        # print(self.data_string)
        if len(url_pices) == 4:  # data was posted to a location
            if url_pices[2] in self._parent.bridge_config["config"]["whitelist"]:
                if (url_pices[3] == "lights" or url_pices[3] == "sensors") and not bool(
                    post_dictionary
                ):
                    # if was a request to scan for lights of sensors
                    Thread(target=self._parent.scan_for_lights).start()
                    time.sleep(
                        7
                    )  # give no more than 7 seconds for light scanning (otherwise will face app disconnection timeout)
                    self.wfile.write(
                        json.dumps(
                            [
                                {
                                    "success": {
                                        "/" + url_pices[3]: "Searching for new devices"
                                    }
                                }
                            ]
                        ).encode("utf8")
                    )
                else:  # create object
                    # find the first unused id for new object
                    i = 1
                    while (str(i)) in self._parent.bridge_config[url_pices[3]]:
                        i += 1
                    if url_pices[3] == "scenes":
                        post_dictionary.update(
                            {
                                "lightstates": {},
                                "version": 2,
                                "picture": "",
                                "lastupdated": datetime.utcnow().strftime(
                                    "%Y-%m-%dT%H:%M:%S"
                                ),
                            }
                        )
                    elif url_pices[3] == "groups":
                        post_dictionary.update(
                            {
                                "action": {"on": False},
                                "state": {"any_on": False, "all_on": False},
                            }
                        )
                    elif url_pices[3] == "schedules":
                        post_dictionary.update(
                            {"created": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
                        )
                        if post_dictionary["localtime"].startswith("PT"):
                            timmer = post_dictionary["localtime"][2:]
                            (h, m, s) = timmer.split(":")
                            d = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
                            post_dictionary.update(
                                {
                                    "starttime": (datetime.utcnow() + d).strftime(
                                        "%Y-%m-%dT%H:%M:%S"
                                    )
                                }
                            )
                        if not "status" in post_dictionary:
                            post_dictionary.update({"status": "enabled"})
                    elif url_pices[3] == "rules":
                        post_dictionary.update({"owner": url_pices[2]})
                        if not "status" in post_dictionary:
                            post_dictionary.update({"status": "enabled"})
                    elif url_pices[3] == "sensors":
                        if post_dictionary["modelid"] == "PHWA01":
                            post_dictionary.update({"state": {"status": 0}})
                    self._parent.generate_sensors_state()
                    self._parent.bridge_config[url_pices[3]][str(i)] = post_dictionary
                    # print(
                    #     json.dumps(
                    #         [{"success": {"id": str(i)}}],
                    #         sort_keys=True,
                    #         indent=4,
                    #         separators=(",", ": "),
                    #     )
                    # )
                    self.wfile.write(
                        json.dumps(
                            [{"success": {"id": str(i)}}],
                            sort_keys=True,
                            indent=4,
                            separators=(",", ": "),
                        ).encode("utf8")
                    )
            else:
                self.wfile.write(
                    json.dumps(
                        [
                            {
                                "error": {
                                    "type": 1,
                                    "address": self.path,
                                    "description": "unauthorized user",
                                }
                            }
                        ],
                        sort_keys=True,
                        indent=4,
                        separators=(",", ": "),
                    ).encode("utf8")
                )
                logger.warning("%s",
                    json.dumps(
                        [
                            {
                                "error": {
                                    "type": 1,
                                    "address": self.path,
                                    "description": "unauthorized user",
                                }
                            }
                        ],
                        sort_keys=True,
                        indent=4,
                        separators=(",", ": "),
                    )
                )
        elif "devicetype" in post_dictionary:  # this must be a new device registration
            # create new user hash
            s = hashlib.new(
                "ripemd160", post_dictionary["devicetype"][0].encode("utf8")
            ).digest()
            username = s.hex()
            self._parent.bridge_config["config"]["whitelist"][username] = {
                "last use date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
                "create date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
                "name": post_dictionary["devicetype"],
            }
            self.wfile.write(
                json.dumps(
                    [{"success": {"username": username}}],
                    sort_keys=True,
                    indent=4,
                    separators=(",", ": "),
                ).encode("utf8")
            )
            print(
                json.dumps(
                    [{"success": {"username": username}}],
                    sort_keys=True,
                    indent=4,
                    separators=(",", ": "),
                )
            )
        self.end_headers()
        self._parent.save_config()

    def do_PUT(self):
        self._set_headers()
        # print("in PUT method")
        self.data_string = self.rfile.read(int(self.headers["Content-Length"]))
        put_dictionary = json.loads(self.data_string)
        url_pices = self.path.split("/")
        if url_pices[2] in self._parent.bridge_config["config"]["whitelist"]:
            if len(url_pices) == 4:
                self._parent.bridge_config[url_pices[3]].update(put_dictionary)
                response_location = "/" + url_pices[3] + "/"
            if len(url_pices) == 5:
                if url_pices[3] == "schedules":
                    if (
                        "status" in put_dictionary
                        and put_dictionary["status"] == "enabled"
                        and self._parent.bridge_config["schedules"][url_pices[4]][
                            "localtime"
                        ].startswith("PT")
                    ):
                        if "localtime" in put_dictionary:
                            timmer = put_dictionary["localtime"][2:]
                        else:
                            timmer = self._parent.bridge_config["schedules"][
                                url_pices[4]
                            ]["localtime"][2:]
                        (h, m, s) = timmer.split(":")
                        d = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
                        put_dictionary.update(
                            {
                                "starttime": (datetime.utcnow() + d).strftime(
                                    "%Y-%m-%dT%H:%M:%S"
                                )
                            }
                        )
                elif url_pices[3] == "scenes":
                    if "storelightstate" in put_dictionary:
                        for light in self._parent.bridge_config["scenes"][url_pices[4]][
                            "lightstates"
                        ]:
                            self._parent.bridge_config["scenes"][url_pices[4]][
                                "lightstates"
                            ][light]["on"] = self._parent.bridge_config["lights"][
                                light
                            ][
                                "state"
                            ][
                                "on"
                            ]
                            self._parent.bridge_config["scenes"][url_pices[4]][
                                "lightstates"
                            ][light]["bri"] = self._parent.bridge_config["lights"][
                                light
                            ][
                                "state"
                            ][
                                "bri"
                            ]
                            if (
                                "xy"
                                in self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]
                            ):
                                del self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]["xy"]
                            elif (
                                "ct"
                                in self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]
                            ):
                                del self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]["ct"]
                            elif (
                                "hue"
                                in self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]
                            ):
                                del self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]["hue"]
                                del self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]["sat"]
                            if self._parent.bridge_config["lights"][light]["state"][
                                "colormode"
                            ] in ["ct", "xy",]:
                                self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light][
                                    self._parent.bridge_config["lights"][light][
                                        "state"
                                    ]["colormode"]
                                ] = self._parent.bridge_config[
                                    "lights"
                                ][
                                    light
                                ][
                                    "state"
                                ][
                                    self._parent.bridge_config["lights"][light][
                                        "state"
                                    ]["colormode"]
                                ]
                            elif (
                                self._parent.bridge_config["lights"][light]["state"][
                                    "colormode"
                                ]
                                == "hs"
                            ):
                                self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]["hue"] = self._parent.bridge_config["lights"][
                                    light
                                ][
                                    "state"
                                ][
                                    "hue"
                                ]
                                self._parent.bridge_config["scenes"][url_pices[4]][
                                    "lightstates"
                                ][light]["sat"] = self._parent.bridge_config["lights"][
                                    light
                                ][
                                    "state"
                                ][
                                    "sat"
                                ]

                if url_pices[3] == "sensors":
                    for key, value in put_dictionary.items():
                        self._parent.bridge_config[url_pices[3]][url_pices[4]][
                            key
                        ].update(value)
                else:
                    self._parent.bridge_config[url_pices[3]][url_pices[4]].update(
                        put_dictionary
                    )
                response_location = "/" + url_pices[3] + "/" + url_pices[4] + "/"
            if len(url_pices) == 6:
                if url_pices[3] == "groups":  # state is applied to a group
                    if (
                        "scene" in put_dictionary
                    ):  # if group is 0 and there is a scene applied
                        for light in self._parent.bridge_config["scenes"][
                            put_dictionary["scene"]
                        ]["lights"]:
                            self._parent.bridge_config["lights"][light]["state"].update(
                                self._parent.bridge_config["scenes"][
                                    put_dictionary["scene"]
                                ]["lightstates"][light]
                            )
                            if (
                                "xy"
                                in self._parent.bridge_config["scenes"][
                                    put_dictionary["scene"]
                                ]["lightstates"][light]
                            ):
                                self._parent.bridge_config["lights"][light]["state"][
                                    "colormode"
                                ] = "xy"
                            elif (
                                "ct"
                                in self._parent.bridge_config["scenes"][
                                    put_dictionary["scene"]
                                ]["lightstates"][light]
                            ):
                                self._parent.bridge_config["lights"][light]["state"][
                                    "colormode"
                                ] = "ct"
                            elif (
                                "hue"
                                or "sat"
                                in self._parent.bridge_config["scenes"][
                                    put_dictionary["scene"]
                                ]["lightstates"][light]
                            ):
                                self._parent.bridge_config["lights"][light]["state"][
                                    "colormode"
                                ] = "hs"
                            Thread(
                                target=self._parent.send_light_request,
                                args=[
                                    light,
                                    self._parent.bridge_config["scenes"][
                                        put_dictionary["scene"]
                                    ]["lightstates"][light],
                                ],
                            ).start()
                            self._parent.update_group_stats(light)
                    elif "bri_inc" in put_dictionary:
                        self._parent.bridge_config["groups"][url_pices[4]]["action"][
                            "bri"
                        ] += int(put_dictionary["bri_inc"])
                        if (
                            self._parent.bridge_config["groups"][url_pices[4]][
                                "action"
                            ]["bri"]
                            > 254
                        ):
                            self._parent.bridge_config["groups"][url_pices[4]][
                                "action"
                            ]["bri"] = 254
                        elif (
                            self._parent.bridge_config["groups"][url_pices[4]][
                                "action"
                            ]["bri"]
                            < 1
                        ):
                            self._parent.bridge_config["groups"][url_pices[4]][
                                "action"
                            ]["bri"] = 1
                        self._parent.bridge_config["groups"][url_pices[4]]["state"][
                            "bri"
                        ] = self._parent.bridge_config["groups"][url_pices[4]][
                            "action"
                        ][
                            "bri"
                        ]
                        del put_dictionary["bri_inc"]
                        put_dictionary.update(
                            {
                                "bri": self._parent.bridge_config["groups"][
                                    url_pices[4]
                                ]["action"]["bri"]
                            }
                        )
                        for light in self._parent.bridge_config["groups"][url_pices[4]][
                            "lights"
                        ]:
                            self._parent.bridge_config["lights"][light]["state"].update(
                                put_dictionary
                            )
                            Thread(
                                target=self._parent.send_light_request,
                                args=[light, put_dictionary],
                            ).start()
                    elif url_pices[4] == "0":
                        for light in self._parent.bridge_config["lights"].keys():
                            self._parent.bridge_config["lights"][light]["state"].update(
                                put_dictionary
                            )
                            Thread(
                                target=self._parent.send_light_request,
                                args=[light, put_dictionary],
                            ).start()
                        for group in self._parent.bridge_config["groups"].keys():
                            self._parent.bridge_config["groups"][group][
                                url_pices[5]
                            ].update(put_dictionary)
                            if "on" in put_dictionary:
                                self._parent.bridge_config["groups"][group]["state"][
                                    "any_on"
                                ] = put_dictionary["on"]
                                self._parent.bridge_config["groups"][group]["state"][
                                    "all_on"
                                ] = put_dictionary["on"]
                    else:  # the state is applied to particular group (url_pices[4])
                        if "on" in put_dictionary:
                            self._parent.bridge_config["groups"][url_pices[4]]["state"][
                                "any_on"
                            ] = put_dictionary["on"]
                            self._parent.bridge_config["groups"][url_pices[4]]["state"][
                                "all_on"
                            ] = put_dictionary["on"]
                        for light in self._parent.bridge_config["groups"][url_pices[4]][
                            "lights"
                        ]:
                            self._parent.bridge_config["lights"][light]["state"].update(
                                put_dictionary
                            )
                            Thread(
                                target=self._parent.send_light_request,
                                args=[light, put_dictionary],
                            ).start()
                elif url_pices[3] == "lights":  # state is applied to a light
                    Thread(
                        target=self._parent.send_light_request,
                        args=[url_pices[4], put_dictionary],
                    ).start()
                    for key in put_dictionary.keys():
                        if key in ["ct", "xy"]:  # colormode must be set by bridge
                            self._parent.bridge_config["lights"][url_pices[4]]["state"][
                                "colormode"
                            ] = key
                        elif key in ["hue", "sat"]:
                            self._parent.bridge_config["lights"][url_pices[4]]["state"][
                                "colormode"
                            ] = "hs"
                    self._parent.update_group_stats(url_pices[4])
                if (
                    not url_pices[4] == "0"
                ):  # group 0 is virtual, must not be saved in bridge configuration
                    try:
                        self._parent.bridge_config[url_pices[3]][url_pices[4]][
                            url_pices[5]
                        ].update(put_dictionary)
                    except KeyError:
                        self._parent.bridge_config[url_pices[3]][url_pices[4]][
                            url_pices[5]
                        ] = put_dictionary
                if url_pices[3] == "sensors" and url_pices[5] == "state":
                    for key in put_dictionary.keys():
                        self._parent.sensors_state[url_pices[4]]["state"].update(
                            {key: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
                        )
                    if (
                        "flag" in put_dictionary
                    ):  # if a scheduler change te flag of a logical sensor then process the rules.
                        self._parent.rules_processor()
                response_location = (
                    "/" + url_pices[3] + "/" + url_pices[4] + "/" + url_pices[5] + "/"
                )
            if len(url_pices) == 7:
                try:
                    self._parent.bridge_config[url_pices[3]][url_pices[4]][
                        url_pices[5]
                    ][url_pices[6]].update(put_dictionary)
                except KeyError:
                    self._parent.bridge_config[url_pices[3]][url_pices[4]][
                        url_pices[5]
                    ][url_pices[6]] = put_dictionary
                self._parent.bridge_config[url_pices[3]][url_pices[4]][url_pices[5]][
                    url_pices[6]
                ] = put_dictionary
                response_location = (
                    "/"
                    + url_pices[3]
                    + "/"
                    + url_pices[4]
                    + "/"
                    + url_pices[5]
                    + "/"
                    + url_pices[6]
                    + "/"
                )
            response_dictionary = []
            for key, value in put_dictionary.items():
                response_dictionary.append(
                    {"success": {response_location + key: value}}
                )
            self.wfile.write(
                json.dumps(
                    response_dictionary,
                    sort_keys=True,
                    indent=4,
                    separators=(",", ": "),
                ).encode("utf8")
            )
            # print(
            #     json.dumps(
            #         response_dictionary,
            #         sort_keys=True,
            #         indent=4,
            #         separators=(",", ": "),
            #     )
            # )
        else:
            self.wfile.write(
                json.dumps(
                    [
                        {
                            "error": {
                                "type": 1,
                                "address": self.path,
                                "description": "unauthorized user",
                            }
                        }
                    ],
                    sort_keys=True,
                    indent=4,
                    separators=(",", ": "),
                ).encode("utf8")
            )

    def do_DELETE(self):
        self._set_headers()
        url_pices = self.path.split("/")
        if url_pices[2] in self._parent.bridge_config["config"]["whitelist"]:
            del self._parent.bridge_config[url_pices[3]][url_pices[4]]
            self.wfile.write(
                json.dumps(
                    [{"success": "/" + url_pices[3] + "/" + url_pices[4] + " deleted."}]
                ).encode("utf8")
            )
