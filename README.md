## Homie Hue Bridge

Brdige homie-esp8266 devices to Philips Hue. Two way synchronises between hue and homie devices. 

Available Hue types [mapped homie properties]:

* plug [on]
* light [on, brightness]
* colorlight [on, brightness, color]

Specify homie devices to mirror in `huebridge.json`

```json
    "1": {
      "name": "Living Room",
    	"type": "light",
    	"address": "abcdef/light",
    },
    "2": {
      "name": "Fan",
    	"type": "plug",
    	"address": "dfgdfg56/relay"
    }
```

```bash
pip install
mkdir config
cp examples/huebridge.json config/huebridge.json
homie-hue-bridge
```

To specify options
```bash
homie-hue-bridge -?
```

Mostly stolen from:

https://github.com/mariusmotea/HueBridgeEmulator
https://github.com/mariusmotea/diyHue/blob/master/BridgeEmulator/HueEmulator3.py

Todo:

* No sensor support
* Plug appears as colourlight in hub even though metadata looks correct?
