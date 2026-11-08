import configparser
import json
import logging
import runpy
import shutil
import subprocess
import sys
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from pubnub.builders import SubscribeBuilder
from pubnub.endpoints.pubsub.publish import Publish

ROOT = Path(__file__).resolve().parents[1]


def read_config(config, filenames, encoding=None):
    config.read_dict(
        {
            "device1": {"name": "local-test"},
            "device2": {"name": "remote-test"},
            "pubnub": {"subscribe_key": "sub-c-test", "publish_key": "pub-c-test"},
        }
    )
    return []


class DiwaliEffectTests(unittest.TestCase):
    def setUp(self):
        native_modules = {
            "RPi": ModuleType("RPi"),
            "RPi.GPIO": ModuleType("RPi.GPIO"),
            "smbus": ModuleType("smbus"),
        }
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(sys.modules, native_modules))
        import blinkt
        import buttonshim

        stack.enter_context(patch.object(configparser.ConfigParser, "read", read_config))
        stack.enter_context(
            patch.object(logging, "FileHandler", return_value=logging.NullHandler())
        )
        stack.enter_context(patch.object(logging, "basicConfig"))
        stack.enter_context(patch.object(buttonshim, "setup"))
        stack.enter_context(patch.object(blinkt, "show"))
        stack.enter_context(patch.object(SubscribeBuilder, "execute"))
        self.publish = stack.enter_context(patch.object(Publish, "pn_async"))
        # run_path returns a copy, so use the live globals the functions see.
        self.app = runpy.run_path(str(ROOT / "src" / "iris.py"))["press_button"].__globals__
        stack.callback(self.app["pubnub"].stop)
        stack.callback(self.app["stop_effect"])
        self.callback = self.app["MySubscribeCallback"]()
        self.publish.reset_mock()

    def message(self, **message):
        self.callback.message(self.app["pubnub"], SimpleNamespace(message=message))

    def wait_until_running(self):
        thread = self.app["effect_thread"]
        self.assertIsNotNone(thread)
        self.assertTrue(thread.is_alive())
        return thread

    def test_frames_are_bounded_and_eight_pixels(self):
        celebration = self.app["DiwaliCelebration"](seed=1)
        previous = None
        t = 0.0
        while t <= celebration.duration:
            frame = celebration.frame(t)
            self.assertEqual(len(frame), 8)
            for r, g, b, brightness in frame:
                for channel in (r, g, b):
                    self.assertIsInstance(channel, int)
                    self.assertTrue(0 <= channel <= 255)
                self.assertTrue(0 <= brightness <= celebration.max_brightness)
            if previous:
                # Gentle transitions: no harsh strobe between frames.
                change = max(abs(a[3] - b[3]) for a, b in zip(frame, previous))
                self.assertLessEqual(change, 0.08, f"at {t}s")
            previous = frame
            t = round(t + self.app["DIWALI_FRAME_DELAY"], 2)

    def test_diyas_light_one_by_one_in_warm_colours(self):
        celebration = self.app["DiwaliCelebration"](seed=1)
        lit = [sum(p[3] > 0 for p in celebration.frame(t)) for t in (0.1, 1.1, 3.6)]
        self.assertEqual(lit, [1, 3, 8])
        for r, g, b, brightness in celebration.frame(10):
            self.assertTrue(r >= g > b, (r, g, b))
            self.assertGreater(brightness, 0)

    def test_rangoli_is_symmetric_and_moves_outward(self):
        celebration = self.app["DiwaliCelebration"](seed=1)
        frame = celebration.frame(20)
        self.assertEqual([p[:3] for p in frame], [p[:3] for p in frame[::-1]])
        colours = {tuple(c) for c in celebration.rangoli_colours}
        self.assertTrue(all(tuple(p[:3]) in colours for p in frame))
        step = 1 / celebration.rangoli_speed
        later = celebration.frame(20 + step)
        self.assertEqual([p[:3] for p in later[0:3]], [p[:3] for p in frame[1:4]])
        self.assertEqual([p[:3] for p in later[5:8]], [p[:3] for p in frame[4:7]])

    def test_sparkles_burst_over_gold_and_settle_to_lamps(self):
        celebration = self.app["DiwaliCelebration"](seed=1)
        start, colour = celebration.bursts[1]
        base = celebration.frame(start - 0.1)
        self.assertEqual({tuple(p[:3]) for p in base}, {celebration.gold})
        burst = celebration.frame(start + 1 / celebration.burst_speed)
        self.assertNotEqual(burst[2][:3], list(celebration.gold))
        self.assertGreater(burst[2][3], base[2][3])
        self.assertEqual(burst[2], burst[5])
        resting = celebration.resting_frame()
        self.assertEqual(resting, celebration.frame(celebration.duration))
        self.assertEqual(len({p[3] for p in resting}), 1)

    def test_press_button_runs_in_background_and_ends_on_lamps(self):
        times = iter(range(100))
        self.app["effect_clock"] = lambda: next(times) * 2.0
        self.message(command="pressButton", button="diwali")
        self.app["effect_thread"].join(timeout=5)
        self.assertFalse(self.app["effect_thread"].is_alive())
        resting = self.app["DiwaliCelebration"]().resting_frame()
        expected = [tuple(p[:3]) for p in resting]
        self.assertEqual([p[:3] for p in self.app["get_all_pixels"]()], expected)
        # Frames 2s apart (29 within 60s) each publish, plus the resting state.
        self.assertEqual(self.publish.call_count, 30)

    def test_publishing_is_throttled_below_frame_rate(self):
        times = iter(range(10000))
        self.app["effect_clock"] = lambda: next(times) * 0.05
        self.app["DIWALI_FRAME_DELAY"] = 0
        with patch.object(self.app["blinkt"], "show") as show:
            self.message(command="pressButton", button="diwali")
            self.app["effect_thread"].join(timeout=5)
        # 60s at 20 fps plus the resting frame are shown; ~2 per second are published.
        self.assertEqual(show.call_count, 1200)
        self.assertEqual(self.publish.call_count, 121)

    def test_power_off_interrupts_celebration(self):
        self.app["DIWALI_FRAME_DELAY"] = 10
        self.message(command="pressButton", button="diwali")
        thread = self.wait_until_running()
        self.message(command="clearPixels")
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.app["get_all_pixels"](), [(0, 0, 0, 0.0)] * 8)

    def test_set_pixels_and_other_buttons_interrupt_celebration(self):
        self.app["DIWALI_FRAME_DELAY"] = 10
        self.message(command="pressButton", button="diwali")
        thread = self.wait_until_running()
        pixels = [[20, 40, 60, 0.1]] * 8
        self.message(command="setPixels", pixels=pixels)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.app["get_all_pixels"](), [(20, 40, 60, 0.097)] * 8)

        self.message(command="pressButton", button="diwali")
        thread = self.wait_until_running()
        self.message(command="pressButton", button="C")
        self.assertFalse(thread.is_alive())

    def test_retrigger_restarts_and_partner_send_keeps_running(self):
        self.app["DIWALI_FRAME_DELAY"] = 10
        self.message(command="pressButton", button="diwali")
        first = self.wait_until_running()
        self.message(command="pressButton", button="diwali")
        second = self.wait_until_running()
        self.assertIsNot(first, second)
        self.assertFalse(first.is_alive())
        self.assertEqual(
            sum(t.name == "iris-effect" for t in threading.enumerate()), 1
        )
        self.message(command="pressButton", button="A")
        self.assertTrue(second.is_alive())


@unittest.skipUnless(shutil.which("node"), "Node.js is required for web tests")
class DiwaliWebTests(unittest.TestCase):
    def run_web(self, expression):
        script = """
const fs = require("fs");
const vm = require("vm");
const published = [];
const elements = [{ classList: { hidden: true, toggle(name, value) { this.hidden = value; } } }];
const context = {
  window: {},
  console: { log() {} },
  document: { querySelectorAll: () => elements },
  config: {
    pubnub: { userId: "web" },
    devices: [{ id: "loki", name: "Loki" }, { id: "yuzu", name: "Yuzu" }],
  },
  published,
  elements,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
vm.runInContext("pubnub = { publish: async (m) => published.push(m) };", context);
const result = vm.runInContext(process.argv[2], context);
process.stdout.write(JSON.stringify(result));
"""
        output = subprocess.run(
            ["node", "-e", script, str(ROOT / "src" / "main.js"), expression],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(output.stdout)

    def test_season_is_2026_local_dates_inclusive(self):
        cases = {
            "new Date(2026, 10, 5, 23, 59, 59)": False,
            "new Date(2026, 10, 6, 0, 0, 0)": True,
            "new Date(2026, 10, 8, 15, 16)": True,
            "new Date(2026, 10, 11, 23, 59, 59)": True,
            "new Date(2026, 10, 12, 0, 0, 0)": False,
            "new Date(2027, 10, 8)": False,
            "new Date(2025, 10, 8)": False,
        }
        for date, expected in cases.items():
            with self.subTest(date=date):
                self.assertIs(self.run_web(f"isDiwaliSeason({date})"), expected)

    def test_seasonal_shortcut_visibility(self):
        self.assertEqual(
            self.run_web(
                "updateDiwaliSeason(new Date(2026, 10, 8));"
                "const shown = !elements[0].classList.hidden;"
                "updateDiwaliSeason(new Date(2026, 10, 12));"
                "[shown, !elements[0].classList.hidden]"
            ),
            [True, False],
        )

    def test_light_and_send_to_partner_dispatch(self):
        self.assertEqual(
            self.run_web(
                "lightDiyas('loki'); sendDiyasToPartner('loki');"
                "sendDiyasToPartner('yuzu'); published"
            ),
            [
                {
                    "channel": channel,
                    "message": {
                        "command": "pressButton",
                        "button": "diwali",
                        "from": "web",
                    },
                }
                for channel in ("loki_control", "yuzu_control", "loki_control")
            ],
        )


if __name__ == "__main__":
    unittest.main()
