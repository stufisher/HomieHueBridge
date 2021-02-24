import os
import shutil
import time
import logging
import argparse

import homie

from homie_hue_bridge.HueSSDP import SSDP
from homie_hue_bridge.HueBridgeEmulator import (
    HueBridgeEmulator,
    get_mac,
    get_ip_address,
)


logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG)

# Device list
# https://github.com/Koenkk/zigbee-herdsman-converters/blob/8f82cbff612d74b9684b41e980f45d4631f600cc/devices.js#L1186
# https://github.com/VonOx/Gladys/blob/master/server/test/services/philips-hue/lights.json

# LWB004 => on off brightness bulb
# LOM001 => on off plug


class BridgeDevice:
    def __init__(self, did, config, properties, homie, update_hue_device):
        self._did = did
        self._config = config
        self._properties = properties
        self._homie = homie
        self._update_hue_device = update_hue_device
        self.subscribe()

    def subscribe(self):
        for p in self._properties:
            prop = self._config.get(f"property_{p}", p)
            addr = f"{self._homie.baseTopic}/{self._config['address']}/{prop}"
            logger.info("Subscribing to %s", addr)
            self._mqtt_subscribe(addr, self.mqttHandler)

    def _mqtt_subscribe(self, topic, callback):
        self._homie._checkBeforeSetup()

        if not self._homie.subscribe_all:
            self._homie.subscriptions.append((topic, int(self._homie.qos)))

        if self._homie.mqtt_connected:
            self._homie._subscribe()

        self._homie.mqtt.message_callback_add(topic, callback)

    def set(self, property, payload, retain=True):
        addr = f"{self._homie.baseTopic}/{self._config['address']}/{property}/set"
        logger.info("Updating homie from hue %s to %s", addr, payload)
        self._homie.mqtt.publish(
            addr, payload=str(payload), retain=retain,
        )

    def mqttHandler(self, mqttc, obj, msg):
        parts = msg.topic.split("/")
        if parts[0] != self._homie.baseTopic:
            return

        prop = parts[-1]
        mapped_prop = None
        for k, v in self._config.items():
            if k.startswith("property_"):
                if v == prop:
                    mapped_prop = k.replace("property_", "")

        if mapped_prop:
            logger.info("Mapping property %s to %s", prop, mapped_prop)
            prop = mapped_prop

        value = msg.payload.decode("utf-8")

        if prop == "on":
            mapped_value = {
                str(self._config.get(f"value_on", "1")): True,
                str(self._config.get(f"value_off", "0")): False,
            }

            if value in mapped_value:
                logger.info("Mapping value %s, to %s", value, mapped_value[value])
                value = mapped_value[value]

            else:
                value = value == "1"

        logger.info("Updating hue from homie %s, %s", msg.topic, value)
        self._update_hue_device(self._did, prop, value)

    def update_from_hue(self, on, cri, bri):
        values = {
            "on": {
                True: self._config.get(f"value_on", 1),
                False: self._config.get(f"value_off", 0),
            },
            "color": cri,
            "brightness": bri,
        }

        for prop in self._properties:
            p = self._config.get(f"property_{prop}", prop)
            if prop == "on":
                self.set(p, values["on"][on])
            else:
                self.set(p, values[prop])


class Huebridge:
    _devices = {}

    def __init__(self, homie, args, config):
        self._args = args
        self._homie = homie
        self._config = config

        self.setup()

    def _device_changed(self, lid, on, cri, bri):
        if lid in self._devices:
            self._devices[lid].update_from_hue(on, cri, bri)

        else:
            logger.warning("Recieved update for unregistered device %s", lid)

    def _sync_devices(self):
        hue_devices = self.hb.get_devices()
        for did, device_config in self._config["HUEDEVICES"].items():
            if did not in hue_devices:
                self.hb.add_device(did, device_config["type"], device_config["name"])

            self._devices[did] = BridgeDevice(
                did,
                device_config,
                self.hb.get_properties(device_config["type"]),
                self._homie,
                self.hb.set_light_state,
            )

        to_rem = []
        for hid in hue_devices.keys():
            if hid not in self._devices:
                to_rem.append(hid)

        for hid in to_rem:
            self.hb.remove_device(hid)

        self.hb.save_config()

    def setup(self):
        if self._args.mac:
            mac = self._args.mac
        else:
            mac = "%012x" % get_mac()
            
        if self._args.bind:
            ip = self._args.bind
        else:
            ip = get_ip_address(self._args.port)

        self.ssdp = SSDP(ip, self._args.port, mac)
        self.ssdp.start()

        config_dir = self._args.config_dir or "config"
        if not os.path.exists(f"{config_dir}/hue.json"):
            shutil.copyfile(
                f"{os.path.dirname(__file__)}/data/base.json", f"{config_dir}/hue.json"
            )

        self.hb = HueBridgeEmulator(ip, self._args.port, mac, f"{config_dir}/hue.json")
        self.hb.add_light_callbacks(self._device_changed)
        self._sync_devices()
        self.hb.start()

    def shutdown(self):
        self.ssdp.shutdown()
        self.hb.shutdown()


def parse_args():
    parser = argparse.ArgumentParser(description="Homie Hue Bridge")
    parser.add_argument(
        "--port", default=8005, dest="port", help="Port to run hue hub server on",
    )
    parser.add_argument(
        "--bind", dest="bind", help="IP to bind to",
    )
    parser.add_argument(
        "--mac", dest="mac", help="Mac address to broadcast on",
    )
    parser.add_argument(
        "--config-dir", dest="config_dir", help="Config dir to use",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    config_dir = args.config_dir or "config"
    config = homie.loadConfigFile(f"{config_dir}/huebridge.json")
    Homie = homie.Homie(config)
    hue = Huebridge(Homie, args, config)

    Homie.setFirmware("huebridge", "1.0.0")
    Homie.setup()

    try:
        while True:
            time.sleep(1)

    finally:
        hue.shutdown()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Quitting.")
