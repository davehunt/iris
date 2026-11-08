import colorsys
import configparser
from itertools import cycle
import json
import logging
import math
import random
import threading
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
    defaults = [
        {"name": "🩷", "pixels": [[247, 0, 162, 0.1]] * 8},
        {"name": "🎉", "pixels": [[255, 0, 0, 0.1]] * 8},
        {"name": "🙂", "pixels": [[0, 150, 14, 0.1]] * 8},
        {
            "name": "🫂",
            "pixels": [
                [4, 50, 255, 0.1],
                [0, 150, 255, 0.3],
                [0, 252, 255, 0.2],
                [117, 213, 255, 0.1],
                [117, 213, 255, 0.1],
                [0, 252, 255, 0.2],
                [0, 150, 255, 0.3],
                [4, 50, 255, 0.1],
            ],
        },
        {
            "name": "🌈",
            "pixels": [
                [255, 0, 0, 0.1],
                [255, 38, 0, 0.1],
                [255, 146, 0, 0.1],
                [254, 251, 0, 0.1],
                [0, 249, 0, 0.1],
                [4, 50, 255, 0.1],
                [147, 32, 146, 0.1],
                [255, 64, 255, 0.1],
            ],
        },
        {
            "name": "🍰",
            "pixels": [
                [255, 0, 0, 0.1],
                [234, 234, 234, 0.1],
                [247, 206, 70, 0.1],
                [247, 206, 70, 0.1],
                [234, 234, 234, 0.1],
                [234, 234, 234, 0.1],
                [247, 206, 70, 0.1],
                [247, 206, 70, 0.1],
            ],
        },
    ]

    def __init__(self):
        try:
            with open(self._path, mode="r") as fp:
                self.custom = json.load(fp)["presets"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            self.custom = []

    @property
    def presets(self):
        return self.defaults + self.custom

    def add(self, name, pixels):
        # TODO catch exception when preset name is not unique
        self.custom.append({"name": name, "pixels": pixels})
        self.save()

    def rename(self, from_name, to_name):
        for p in self.custom:
            p.update(("name", to_name) for k, v in p.items() if v == from_name)
        self.save()

    def remove(self, name):
        self.custom[:] = [p for p in self.custom if p.get("name") != name]
        self.save()

    def save(self):
        with open("presets.json", mode="w") as fp:
            json.dump({"presets": self.custom}, fp, indent=4)


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
    if button not in (
        buttonshim.NAMES[buttonshim.BUTTON_A],
        buttonshim.NAMES[buttonshim.BUTTON_E],
    ):
        stop_effect()
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
    elif button == "rainbow":
        rainbow()
    elif button == "valentines":
        valentines()
    elif button == "xmas":
        xmas()
    elif button == "diwali":
        start_effect(run_diwali)
    elif button == "firefox":
        start_effect(run_firefox)


effect_lock = threading.RLock()
effect_stop = threading.Event()
effect_thread = None
effect_clock = time.monotonic


def start_effect(target):
    """Run an interruptible effect in the background, replacing any current one."""
    global effect_stop, effect_thread
    with effect_lock:
        stop_effect()
        effect_stop = threading.Event()
        effect_thread = threading.Thread(
            target=target, args=(effect_stop,), name="iris-effect", daemon=True
        )
        effect_thread.start()


def stop_effect():
    with effect_lock:
        thread = effect_thread
        if thread is None or not thread.is_alive():
            return
        effect_stop.set()
        if thread is not threading.current_thread():
            thread.join(timeout=2)


def show_frame(pixels):
    for i, p in enumerate(pixels):
        blinkt.set_pixel(i, *p)
    blinkt.show()


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _mix(a, b, amount):
    return [a[i] + (b[i] - a[i]) * amount for i in range(4)]


class DiwaliCelebration:
    """Deterministic frames for the Diwali celebration.

    Diyas light one by one and flicker gently, a rangoli shimmer moves outward
    from the centre, festival sparkles burst over gold, then the diyas settle.
    """

    duration = 60.0
    max_brightness = 0.3
    lamp_brightness = (0.08, 0.2)
    lamp_colours = [
        (255, 110, 20),
        (255, 147, 41),
        (255, 183, 76),
        (255, 147, 41),
        (255, 147, 41),
        (255, 183, 76),
        (255, 147, 41),
        (255, 110, 20),
    ]
    rangoli_colours = [(255, 0, 144), (0, 206, 190), (148, 0, 211), (255, 183, 76)]
    sparkle_colours = [(255, 0, 144), (0, 206, 190), (148, 0, 211), (0, 230, 90)]
    gold = (255, 183, 76)
    light_interval = 0.5
    light_fade = 0.4
    rangoli = (16.0, 24.0)
    rangoli_speed = 1.5
    sparkles = (30.0, 36.0)
    transition = 1.0
    settle = 3.0
    burst_length = 1.2
    burst_speed = 5.0

    def __init__(self, seed=None):
        rng = random.Random(seed)
        self.num_pixels = len(self.lamp_colours)
        self.centre = (self.num_pixels - 1) / 2
        self.flicker = [
            (
                rng.uniform(0, math.tau),
                rng.uniform(0, math.tau),
                rng.uniform(1.3, 2.1),
                rng.uniform(2.9, 4.3),
            )
            for _ in range(self.num_pixels)
        ]
        start = self.sparkles[0] + 0.5
        self.bursts = [
            (start + k * 1.8, rng.choice(self.sparkle_colours)) for k in range(3)
        ]

    def _envelope(self, t, window):
        start, end = window
        if not start <= t <= end:
            return 0.0
        return _clamp(min(t - start, end - t) / self.transition)

    def _lamp(self, i, t):
        p1, p2, w1, w2 = self.flicker[i]
        amplitude = _clamp((self.duration - t) / self.settle)
        wave = 0.3 * math.sin(w1 * t + p1) + 0.2 * math.sin(w2 * t + p2)
        level = 0.5 + wave * amplitude
        low, high = self.lamp_brightness
        r, g, b = self.lamp_colours[i]
        return [r, g * (0.85 + 0.15 * level), b, low + (high - low) * level]

    def _rangoli(self, i, t):
        phase = abs(i - self.centre) - self.rangoli_speed * (t - self.rangoli[0])
        index = math.floor(phase)
        frac = _clamp((phase - index - 0.7) / 0.3)
        colours = self.rangoli_colours
        a = colours[index % len(colours)]
        b = colours[(index + 1) % len(colours)]
        colour = [a[c] + (b[c] - a[c]) * frac for c in range(3)]
        return colour + [0.15 + 0.03 * math.sin(4 * t + i)]

    def _sparkle(self, i, t):
        pixel = list(self.gold) + [0.08]
        distance = abs(i - self.centre) - 0.5
        for start, colour in self.bursts:
            age = t - start
            if not 0 <= age < self.burst_length:
                continue
            ring = _clamp(1 - abs(distance - age * self.burst_speed))
            fade = 1 - age / self.burst_length
            intensity = ring * fade * _clamp(age / 0.15)
            pixel = _mix(pixel, list(colour) + [0.28], intensity)
        return pixel

    def frame(self, t):
        pixels = []
        for i in range(self.num_pixels):
            lit = _clamp((t - i * self.light_interval) / self.light_fade)
            if lit == 0:
                pixels.append([0, 0, 0, 0.0])
                continue
            pixel = self._lamp(i, t)
            pixel[3] *= lit
            if (amount := self._envelope(t, self.rangoli)) > 0:
                pixel = _mix(pixel, self._rangoli(i, t), amount)
            if (amount := self._envelope(t, self.sparkles)) > 0:
                pixel = _mix(pixel, self._sparkle(i, t), amount)
            r, g, b, brightness = pixel
            pixels.append(
                [
                    round(r),
                    round(g),
                    round(b),
                    round(_clamp(brightness, 0, self.max_brightness), 3),
                ]
            )
        return pixels

    def resting_frame(self):
        return self.frame(self.duration)


DIWALI_FRAME_DELAY = 0.05
DIWALI_PUBLISH_INTERVAL = 0.5


class FirefoxOrbit:
    """A gold fox and flowing ember tail orbit a blue/violet globe."""

    duration = 30.0
    num_pixels = 8
    orbit_period = 6.0
    max_brightness = 0.3

    def frame(self, t):
        fade = _clamp(min(t, self.duration - t) / 1.5)
        head = t * self.num_pixels / self.orbit_period
        pixels = []
        for i in range(self.num_pixels):
            globe = (1 + math.sin(math.tau * i / self.num_pixels - t * 0.4)) / 2
            pixel = _mix([18, 35, 160, 0.06], [85, 24, 185, 0.08], globe)
            # Circular lobes wrap the tail smoothly from LED 7 back to LED 0.
            for offset, width, strength, colour in (
                (2.5, 1.6, 0.65, [240, 48, 12, 0.18]),
                (1.25, 0.95, 0.85, [255, 106, 16, 0.24]),
                (0, 0.65, 1.0, [255, 192, 52, 0.28]),
            ):
                angle = math.tau * (i - head + offset) / self.num_pixels
                lobe = math.exp(
                    (math.cos(angle) - 1) / (width * math.tau / self.num_pixels) ** 2
                )
                pixel = _mix(pixel, colour, lobe * strength)
            pixels.append(
                [round(c) for c in pixel[:3]]
                + [round(_clamp(pixel[3] * fade, 0, self.max_brightness), 3)]
            )
        return pixels

    def resting_frame(self):
        return [[0, 0, 0, 0.0] for _ in range(self.num_pixels)]


FIREFOX_FRAME_DELAY = 0.05
FIREFOX_PUBLISH_INTERVAL = 0.5


def run_animation(stop_event, celebration, frame_delay, publish_interval):
    start = effect_clock()
    last_publish = None
    while (
        not stop_event.is_set()
        and (elapsed := effect_clock() - start) < celebration.duration
    ):
        show_frame(celebration.frame(elapsed))
        # Publishing every frame would flood PubNub; the web view samples it.
        if last_publish is None or elapsed - last_publish >= publish_interval:
            send_pixels()
            last_publish = elapsed
        if stop_event.wait(frame_delay):
            return
    if not stop_event.is_set():
        show_frame(celebration.resting_frame())
        send_pixels()


def run_diwali(stop_event, celebration=None):
    run_animation(
        stop_event, celebration or DiwaliCelebration(),
        DIWALI_FRAME_DELAY, DIWALI_PUBLISH_INTERVAL,
    )


def run_firefox(stop_event, orbit=None):
    run_animation(
        stop_event, orbit or FirefoxOrbit(),
        FIREFOX_FRAME_DELAY, FIREFOX_PUBLISH_INTERVAL,
    )


def clear():
    stop_effect()
    blinkt.clear()
    blinkt.show()
    send_pixels()


def marquee(pattern, delay=0.1, duration=10):
    clear()
    pixels = [[0, 0, 0, 0]] * blinkt.NUM_PIXELS
    start_time = time.time()
    while time.time() - start_time < duration:
        pixels.append(next(pattern))
        pixels.pop(0)
        set_pixels(pixels)
        time.sleep(0.1)
    clear()


def valentines():
    pattern = cycle(
        [
            [247, 0, 162, 0.1],
            [247, 0, 162, 0.1],
            [247, 0, 162, 0.5],
            [247, 0, 162, 0.5],
            [247, 0, 162, 0.9],
            [247, 0, 162, 0.9],
            [247, 0, 162, 0.5],
            [247, 0, 162, 0.5],
        ]
    )
    marquee(pattern)


def xmas():
    pattern = cycle([[255, 0, 0, 0.1], [255, 255, 255, 0.1]])
    marquee(pattern, delay=0.2)


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
            send_pixels()
            send_presets()
        elif status.category == PNStatusCategory.PNDecryptionErrorCategory:
            logging.error("Error")
            buttonshim.set_pixel(255, 0, 0)
            time.sleep(5)
            connect()

    def message(self, pubnub, message):
        logging.info(f"message: {message.message}")
        command = message.message["command"]
        if command == "setPixels":
            stop_effect()
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
    channel = f"{pnconfig.user_id}_control"
    if channel not in pubnub.get_subscribed_channels():
        buttonshim.set_pixel(0, 0, 255)
        pubnub.subscribe().channels(channel).with_presence().execute()


pm = PresetsManager()
pubnub.add_listener(MySubscribeCallback())
connect()
