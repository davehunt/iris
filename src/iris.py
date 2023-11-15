import colorsys
import configparser
import json
import logging
import random
import time

import blinkt
import buttonshim
from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory, PNReconnectionPolicy
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub

config = configparser.ConfigParser()
config.read("config.ini")

logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")

blinkt.clear()
blinkt.show()

pnconfig = PNConfiguration()
pnconfig.subscribe_key = config["pubnub"]["subscribe_key"]
pnconfig.publish_key = config["pubnub"]["publish_key"]
pnconfig.user_id = config["pubnub"]["user_id"]
pnconfig.reconnect_policy = PNReconnectionPolicy.EXPONENTIAL
pubnub = PubNub(pnconfig)


class PresetsManager:
    _path = "presets.json"

    def __init__(self):
        with open(self._path, mode="r") as fp:
            _json = json.load(fp)
        self.presets = _json["presets"]

    def add(self, name, pixels):
        # TODO catch exception when preset name is not unique
        self.presets.append({"name": name, "default": False, "pixels": pixels})
        self.save()

    def rename(self, from_name, to_name):
        for p in self.presets:
            p.update(("name", to_name) for k, v in p.items() if v == from_name)
        self.save()

    def remove(self, name):
        self.presets[:] = [p for p in self.presets if p.get("name") != name]
        self.save()

    def save(self):
        with open("presets.json", mode="w") as fp:
            json.dump({"presets": self.presets}, fp, indent=4)


try:

    @buttonshim.on_press(
        [
            buttonshim.BUTTON_A,
            buttonshim.BUTTON_B,
            buttonshim.BUTTON_C,
            buttonshim.BUTTON_D,
            buttonshim.BUTTON_E,
        ]
    )
    def handle_button_press(button, pressed):
        press_button(buttonshim.NAMES[button])
except FileNotFoundError:
    pass


def press_button(button):
    if button == buttonshim.NAMES[buttonshim.BUTTON_E]:
        clear()


def clear():
    blinkt.clear()
    blinkt.show()
    send_pixels("web")


def flash(color):
    blinkt.set_pixel(0, *color)
    blinkt.show()
    clear()


def rainbow():
    spacing = 360.0 / 16.0
    hue = 0

    blinkt.set_brightness(0.1)
    t_end = time.time() + 30
    while time.time() < t_end:
        hue = int(time.time() * 100) % 360
        for x in range(blinkt.NUM_PIXELS):
            offset = x * spacing
            h = ((hue + offset) % 360) / 360.0
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, 1.0, 1.0)]
            blinkt.set_pixel(x, r, g, b)

        blinkt.show()
        send_pixels("web")
        time.sleep(0.05)
    clear()


def random_blink():
    t_end = time.time() + 30
    while time.time() < t_end:
        for i in range(blinkt.NUM_PIXELS):
            blinkt.set_pixel(
                i,
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
        blinkt.show()
        send_pixels("web")
        time.sleep(0.05)
    clear()


def publish_message(channel, message):
    logging.info(f"publish: channel:{channel}, message:{message}")
    pubnub.publish().channel(channel).message(message).pn_async(my_publish_callback)


def send_presets(channel):
    publish_message(channel, {"presets": pm.presets})


def send_pixels(channel):
    pixels = [blinkt.get_pixel(i) for i in range(blinkt.NUM_PIXELS)]
    publish_message(channel, {"pixels": pixels})


def get_all_pixels():
    return [blinkt.get_pixel(i) for i in range(blinkt.NUM_PIXELS)]


def my_publish_callback(result, status):
    if status.is_error():
        logging.error(status.__dict__)
        logging.error(status.error_data.__dict__)
    else:
        logging.info(result.timetoken)


class MySubscribeCallback(SubscribeCallback):
    def presence(self, pubnub, event):
        action = event.event
        channel = event.channel
        userId = event.uuid
        timeToken = event.timetoken
        occupancy = event.occupancy
        state = event.user_metadata
        logging.info(
            f"presence: action:{action} channel:{channel} userId:{userId} timeToken:{timeToken} occupancy:{occupancy} state:{state}"
        )

    def status(self, pubnub, status):
        if status.category == PNStatusCategory.PNUnexpectedDisconnectCategory:
            logging.info("Disconnected")
            flash((0, 0, 255))
        elif status.category == PNStatusCategory.PNConnectedCategory:
            logging.info("Connected")
            flash((0, 255, 0))
        elif status.category == PNStatusCategory.PNDecryptionErrorCategory:
            logging.info("Error")
            flash((255, 0, 0))

    def message(self, pubnub, message):
        logging.info(f"message: {message.message}")
        command = message.message["command"]
        sender = message.message["from"]
        if command == "setPixels":
            for index, pixel in enumerate(message.message["pixels"]):
                blinkt.set_pixel(index, *pixel)
            blinkt.show()
            send_pixels(sender)
        elif command == "clearPixels":
            clear()
        elif command == "getPixels":
            send_pixels(sender)
        elif command == "pressButton":
            press_button(message.message["button"])
        elif command == "getPresets":
            send_presets(sender)
        elif command == "savePreset":
            pm.add(message.message["name"], message.message["pixels"])
            send_presets(sender)
        elif command == "renamePreset":
            pm.rename(message.message["fromName"], message.message["toName"])
            send_presets(sender)
        elif command == "deletePreset":
            pm.remove(message.message["name"])
            send_presets(sender)


pm = PresetsManager()
pubnub.add_listener(MySubscribeCallback())
pubnub.subscribe().channels(pnconfig.user_id).with_presence().execute()
