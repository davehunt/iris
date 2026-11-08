import configparser
import logging
import runpy
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from pubnub.builders import SubscribeBuilder
from pubnub.endpoints.pubsub.publish import Publish
from pubnub.enums import PNStatusCategory


class CompatibilityTests(unittest.TestCase):
    def test_startup_and_messages_with_current_sdk(self):
        def read_config(config, filenames, encoding=None):
            config.read_dict(
                {
                    "device1": {"name": "local-test"},
                    "device2": {"name": "remote-test"},
                    "pubnub": {
                        "subscribe_key": "sub-c-test",
                        "publish_key": "pub-c-test",
                    },
                }
            )
            return []

        native_modules = {
            "RPi": ModuleType("RPi"),
            "RPi.GPIO": ModuleType("RPi.GPIO"),
            "smbus": ModuleType("smbus"),
        }
        with patch.dict(sys.modules, native_modules):
            import blinkt
            import buttonshim

            with (
                patch.object(configparser.ConfigParser, "read", read_config),
                patch.object(logging, "FileHandler", return_value=logging.NullHandler()),
                patch.object(logging, "basicConfig"),
                patch.object(buttonshim, "setup"),
                patch.object(blinkt, "show"),
                patch.object(SubscribeBuilder, "execute") as subscribe,
                patch.object(Publish, "pn_async") as publish,
            ):
                source = Path(__file__).resolve().parents[1] / "src" / "iris.py"
                app = runpy.run_path(str(source))
                pubnub = app["pubnub"]
                try:
                    subscribe.assert_called_once()
                    self.assertEqual(pubnub.config.user_id, "local-test")
                    callback = app["MySubscribeCallback"]()
                    callback.status(
                        pubnub,
                        SimpleNamespace(category=PNStatusCategory.PNConnectedCategory),
                    )
                    self.assertEqual(publish.call_count, 2)
                    pixels = [[20, 40, 60, 0.1]] * 8
                    callback.message(
                        pubnub,
                        SimpleNamespace(
                            message={"command": "setPixels", "pixels": pixels}
                        ),
                    )
                    self.assertEqual(
                        app["get_all_pixels"](), [(20, 40, 60, 0.097)] * 8
                    )
                    self.assertEqual(publish.call_count, 3)
                    self.assertEqual(
                        publish.call_args.args[0], app["my_publish_callback"]
                    )
                finally:
                    pubnub.stop()


if __name__ == "__main__":
    unittest.main()
