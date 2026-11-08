import json
import shutil
import subprocess
import threading
import unittest
from unittest.mock import Mock, patch

import test_diwali


class FirefoxEffectTests(unittest.TestCase):
    setUp = test_diwali.DiwaliEffectTests.setUp
    message = test_diwali.DiwaliEffectTests.message
    wait_until_running = test_diwali.DiwaliEffectTests.wait_until_running

    def test_frames_are_eight_pixels_bounded_and_smooth(self):
        orbit = self.app["FirefoxOrbit"]()
        previous = None
        for step in range(601):
            t = step * self.app["FIREFOX_FRAME_DELAY"]
            frame = orbit.frame(t)
            self.assertEqual(len(frame), 8)
            for r, g, b, brightness in frame:
                for channel in (r, g, b):
                    self.assertIsInstance(channel, int)
                    self.assertTrue(0 <= channel <= 255)
                self.assertTrue(0 <= brightness <= orbit.max_brightness)
            if previous:
                self.assertLessEqual(
                    round(max(abs(a[3] - b[3]) for a, b in zip(frame, previous)), 3),
                    0.02,
                )
                self.assertLessEqual(
                    max(abs(a[c] - b[c]) for a, b in zip(frame, previous)
                        for c in range(3)), 20
                )
            previous = frame
        self.assertTrue(all(p[3] == 0 for p in orbit.frame(0)))
        self.assertTrue(all(p[3] == 0 for p in orbit.frame(orbit.duration)))
        self.assertEqual(orbit.resting_frame(), [[0, 0, 0, 0.0]] * 8)

    def test_warm_head_and_tail_flow_over_cool_globe_and_wrap(self):
        orbit = self.app["FirefoxOrbit"]()
        for index in range(9):
            frame = orbit.frame(6 + index * 0.75)
            head = index % 8
            self.assertEqual(max(range(8), key=lambda i: frame[i][3]), head)
            r, g, b, _ = frame[head]
            self.assertGreater(r, g)
            self.assertGreater(g, b)
            tail = frame[(head - 1) % 8]
            self.assertGreater(tail[0], tail[2])
            self.assertGreater(tail[3], frame[(head + 1) % 8][3])
            globe = frame[(head + 3) % 8]
            self.assertGreater(globe[2], globe[0])

    def test_dispatch_finishes_off_and_throttles_state_publishing(self):
        times = iter(range(10000))
        self.app["effect_clock"] = lambda: next(times) * 0.05
        self.app["FIREFOX_FRAME_DELAY"] = 0
        with patch.object(self.app["blinkt"], "show") as show:
            self.message(command="pressButton", button="firefox")
            thread = self.app["effect_thread"]
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(show.call_count, 600)
        self.assertEqual(self.publish.call_count, 61)
        self.assertEqual(self.app["get_all_pixels"](), [(0, 0, 0, 0.0)] * 8)

    def test_pixel_update_power_off_and_static_button_interrupt_without_late_clear(self):
        self.app["FIREFOX_FRAME_DELAY"] = 10
        for command in (
            {"command": "setPixels", "pixels": [[20, 40, 60, 0.1]] * 8},
            {"command": "clearPixels"},
            {"command": "pressButton", "button": "C"},
        ):
            with self.subTest(command=command["command"]):
                self.message(command="pressButton", button="firefox")
                thread = self.wait_until_running()
                self.message(**command)
                self.assertFalse(thread.is_alive())
                if command["command"] == "setPixels":
                    self.assertEqual(
                        self.app["get_all_pixels"](), [(20, 40, 60, 0.097)] * 8
                    )
                elif command["command"] == "clearPixels":
                    self.assertEqual(
                        self.app["get_all_pixels"](), [(0, 0, 0, 0.0)] * 8
                    )
                else:
                    self.assertEqual(
                        [p[:3] for p in self.app["get_all_pixels"]()],
                        [(247, 0, 162)] * 8,
                    )

    def test_retrigger_replaces_worker_and_button_a_sends_without_stopping(self):
        self.app["FIREFOX_FRAME_DELAY"] = 10
        self.message(command="pressButton", button="firefox")
        first = self.wait_until_running()
        self.message(command="pressButton", button="firefox")
        second = self.wait_until_running()
        self.assertIsNot(first, second)
        self.assertFalse(first.is_alive())
        self.assertEqual(sum(t.name == "iris-effect" for t in threading.enumerate()), 1)
        self.publish.reset_mock()
        send = Mock(wraps=self.app["send_pixels"])
        with patch.dict(self.app, {"send_pixels": send}):
            self.message(command="pressButton", button="A")
        send.assert_called_once_with("remote-test_control")
        self.assertTrue(second.is_alive())
        self.publish.assert_called_once()
        self.message(command="pressButton", button="diwali")
        self.assertFalse(second.is_alive())
        self.assertIsNot(second, self.wait_until_running())

    def test_already_stopped_worker_does_not_render_or_publish(self):
        stop = threading.Event()
        stop.set()
        with patch.object(self.app["blinkt"], "show") as show:
            self.app["run_firefox"](stop)
        show.assert_not_called()
        self.publish.assert_not_called()

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for web tests")
    def test_browser_matches_device_at_every_frame_including_orbit_seams(self):
        orbit = self.app["FirefoxOrbit"]()
        times = [i * 0.05 for i in range(601)] + [5.999, 6.001, 29.999]
        script = """
const fs = require("fs");
const vm = require("vm");
const context = { times: JSON.parse(process.argv[2]) };
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
process.stdout.write(JSON.stringify(vm.runInContext("times.map(firefoxFrame)", context)));
"""
        result = subprocess.run(
            ["node", "-e", script, str(test_diwali.ROOT / "src" / "effects.js"),
             json.dumps(times)],
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(result.stdout), [orbit.frame(t) for t in times])


if __name__ == "__main__":
    unittest.main()
