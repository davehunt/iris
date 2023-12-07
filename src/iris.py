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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(message)s",
    handlers=[logging.FileHandler("iris.log"), logging.StreamHandler()],
)

buttonshim.set_pixel(0, 0, 0)
buttonshim.set_brightness(0.1)
button_was_held = False

blinkt.clear()
blinkt.show()

device1 = config["device1"]["name"]
device2 = config["device2"]["name"]

pnconfig = PNConfiguration()
pnconfig.subscribe_key = config["pubnub"]["subscribe_key"]
pnconfig.publish_key = config["pubnub"]["publish_key"]
pnconfig.user_id = device1
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


@buttonshim.on_release(buttonshim.BUTTON_E)
def handle_button_release(button, pressed):
    if not button_was_held:
        clear()


@buttonshim.on_hold(buttonshim.BUTTON_E, hold_time=2)
def handle_button_hold(button):
    global button_was_held
    button_was_held = True
    connect()


def press_button(button):
    if button == buttonshim.NAMES[buttonshim.BUTTON_A]:
        send_pixels(f"{device2}_control")
    elif button == buttonshim.NAMES[buttonshim.BUTTON_B]:
        set_pixels(random.choice(pm.presets)["pixels"])
    elif button == buttonshim.NAMES[buttonshim.BUTTON_C]:
        set_pixels(pm.presets[0]["pixels"])
    elif button == buttonshim.NAMES[buttonshim.BUTTON_D]:
        random_pixels()
    elif button == buttonshim.NAMES[buttonshim.BUTTON_E]:
        global button_was_held
        button_was_held = False


def clear():
    blinkt.clear()
    blinkt.show()
    send_pixels()


def beam(color):
    decay_factor = 1.5
    num_pixels = blinkt.NUM_PIXELS
    bright_pixel = -1
    direction = 1

    for _ in range((num_pixels * 4) - 3):
        for x in range(num_pixels):
            pixel = blinkt.get_pixel(x)
            blinkt.set_pixel(x, pixel[0] / decay_factor, 0, 0)
        bright_pixel += direction

        if bright_pixel >= num_pixels - 1:
            bright_pixel = num_pixels - 1
            direction = -abs(direction)
        if bright_pixel <= 0:
            bright_pixel = 0
            direction = abs(direction)

        blinkt.set_pixel(bright_pixel, *color)
        blinkt.show()
        send_pixels()
        time.sleep(0.05)
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
        send_pixels()
        time.sleep(0.05)
    clear()


def random_pixels():
    for i in range(blinkt.NUM_PIXELS):
        blinkt.set_pixel(
            i,
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255),
        )
    blinkt.show()
    send_pixels()


def random_blink():
    t_end = time.time() + 30
    while time.time() < t_end:
        random_pixels()
        time.sleep(0.05)
    clear()


def publish_message(message, channel=None):
    channel = channel or f"{pnconfig.user_id}_status"
    logging.info(f"publish: channel:{channel}, message:{message}")
    pubnub.publish().channel(channel).message(message).pn_async(my_publish_callback)


def send_presets():
    publish_message({"presets": pm.presets})


def send_pixels(channel=None):
    pixels = [blinkt.get_pixel(i) for i in range(blinkt.NUM_PIXELS)]
    publish_message({"command": "setPixels", "pixels": pixels}, channel)


def set_pixels(pixels):
    for i, p in enumerate(pixels):
        blinkt.set_pixel(i, *p)
    blinkt.show()
    send_pixels()


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
            logging.warn("Disconnected")
            buttonshim.set_pixel(255, 255, 0)
            time.sleep(5)
            connect()
        elif status.category == PNStatusCategory.PNConnectedCategory:
            logging.info("Connected")
            buttonshim.set_pixel(0, 255, 0)
        elif status.category == PNStatusCategory.PNDecryptionErrorCategory:
            logging.error("Error")
            buttonshim.set_pixel(255, 0, 0)
            time.sleep(5)
            connect()

    def message(self, pubnub, message):
        logging.info(f"message: {message.message}")
        command = message.message["command"]
        if command == "setPixels":
            set_pixels(message.message["pixels"])
        elif command == "clearPixels":
            clear()
        elif command == "getPixels":
            send_pixels()
        elif command == "pressButton":
            press_button(message.message["button"])
        elif command == "getPresets":
            send_presets()
        elif command == "savePreset":
            pm.add(message.message["name"], message.message["pixels"])
            send_presets()
        elif command == "renamePreset":
            pm.rename(message.message["fromName"], message.message["toName"])
            send_presets()
        elif command == "deletePreset":
            pm.remove(message.message["name"])
            send_presets()

def connect():
    buttonshim.set_pixel(0, 0, 255)
    pubnub.subscribe().channels(f"{pnconfig.user_id}_control").with_presence().execute()

pm = PresetsManager()
pubnub.add_listener(MySubscribeCallback())
connect()