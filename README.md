# Iris

Iris connects two remote Raspberry Pi Zero 2 W devices over the internet. Each
device has a Pimoroni Blinkt! eight-pixel LED array and a Button SHIM. A static
web page can monitor and control both devices.

## How it works

The Python service in [`src/iris.py`](src/iris.py) runs on each Raspberry Pi.
It:

- controls the local Blinkt! LEDs and Button SHIM;
- publishes local LED state and presets on a `<device>_status` PubNub channel;
- subscribes to a `<device>_control` PubNub channel;
- handles remote pixel updates, preset management, and button/effect commands.

The browser UI in [`src/index.html`](src/index.html) and
[`src/main.js`](src/main.js) subscribes to both status channels and publishes
control messages to either device. The UI is static and has no application
server.

## Special presets and browser previews

Presets show just their emoji, with the text name available on hover or keyboard
focus. Built-in defaults and saved presets come from the device's reported list.
Saved presets without an emoji get a bookmark emoji without changing their
stored names. Animated preset controls use Bootstrap's
play/stop (browser preview), lightbulb (apply to device), and send (partner) icons,
with tooltips and accessible labels.
Static presets use an edit icon to load into the custom editor and a lightbulb
to apply directly to the device without changing the editor.
Preview status is announced to screen readers without adding text beneath rows.

Each device's presets list also includes **Rainbow**, **Valentine's**,
**Christmas**, **Diwali**, and **Firefox**, even before the device connects. **Preview**
animates that row's eight LEDs in the browser only; it does not publish any
commands, change the live device display, or overwrite custom pixels. All LED
simulators (live devices, static preset swatches, and animated previews) use the
same per-LED brightness rendering: off LEDs are transparent with a faint outline;
lit LEDs retain strong RGB colour, with opacity and an outer glow increasing on
a perceptual square-root brightness scale. LEDs at brightness 0.1 or below have
no outer glow, keeping their edges crisp. This keeps dim LEDs colourful against
white while the halo distinguishes their intensity. Lit white LEDs use an opaque
white fill so dark backgrounds cannot turn them gray, plus a stronger outline to
distinguish them from transparent off LEDs on light backgrounds. This includes
the Christmas preview's white lights at brightness 0.1; their raw brightness
and the glow threshold are unchanged.
Screen colours are illustrative,
not a calibrated
reproduction of physical LEDs. Original RGB and brightness values are retained
for editing and sending, without applying brightness twice. Rainbow runs for
30 seconds, Valentine's and Christmas for 10 seconds, Diwali for 60 seconds,
and Firefox for 30 seconds,
matching the device effects. Diwali finishes on steady lamps; the other previews clear.

Press **Stop preview** to end it early. Starting another preview in that device
card, refreshing its presets, loading static pixels, or applying/sending pixels
or effects stops its preview. The other device's preview can run independently.
**Apply** starts the real effect on the card's device; **Send to partner** starts
it on the other device. Both use the existing `pressButton` command. Static and
saved presets retain their existing load/send/edit behavior and wire/storage
format. The browser-only catalogue lives in [`src/effects.js`](src/effects.js);
keep its frames and timing aligned with the device effects when changing them.

## Firefox orbit

The year-round **🦊 Firefox** special preset is an original colour and
motion homage, not a logo reproduction. A gold head, orange sweep and soft ember
tail flow around a deep blue/violet globe, wrapping the linear eight LEDs every
six seconds. The 30-second animation fades in and out over 1.5 seconds and ends
with the LEDs off. Frames update at 20 fps, with per-LED brightness below 0.3
and no strobing.

The browser preview uses the same deterministic colours, brightness and timing
as the device. It stays browser-only; **Apply** and **Send to partner** explicitly
publish `{"command": "pressButton", "button": "firefox"}` to the chosen device.
Like Diwali, it runs in the interruptible background worker and publishes state
about twice a second. Power off, pixel updates and other effect/preset buttons
stop it; retriggering restarts it. Button A sends the current pixels to the
partner without stopping the animation. No seasonal shortcut is added.

## Diwali celebration

The Diwali celebration is a one-minute LED sequence: eight warm amber, gold
and orange diyas light one by one and flicker gently and independently; a
symmetric magenta, turquoise, violet and gold rangoli shimmer moves outward
from the centre; a few colourful festival sparkles burst outward over gold and
fade; then the diyas return. Most of the sequence is calm diya light, and it
ends with the lamps left steadily lit, like a preset. Brightness stays at or
below 0.3 and transitions are gradual, with no strobing.

The celebration is available year-round from the 🪔 button in each device
card's header. From 6 to 11 November 2026 inclusive, by the browser's local
date, each device also shows a prominent **Light the diyas** card with a
**Send to partner** option that starts the celebration on the other device.
These dates apply to 2026 only; update `DIWALI_SEASON` in
[`src/main.js`](src/main.js) for future years. The date only controls the
shortcut: nothing starts automatically and an active effect is never replaced.

Both actions publish `{"command": "pressButton", "button": "diwali"}` to the
target device's `<device>_control` channel. The device runs the sequence in a
background thread, so it keeps responding to commands. Power off, a pixel
update or another effect/preset button interrupts it; pressing it again
restarts it; the device's send-to-partner button (A) sends the current frame
without interrupting. While running, the device publishes its LED state about
twice a second rather than every frame. Devices without this feature ignore
the unknown button.

## Configuration

Runtime configuration is deliberately untracked:

- Copy [`_config.ini`](_config.ini) to `config.ini` on each Pi and set the
  device names and PubNub keys.
- Copy [`src/_config.js`](src/_config.js) to `src/config.js` for the web page
  and set the matching device IDs and browser PubNub keys.

The device names are also the PubNub user IDs and form the channel names. For
example, a device named `lokipizero2w` uses `lokipizero2w_control` and
`lokipizero2w_status`.

Keep generated configuration files private. Both are ignored by
[`.gitignore`](.gitignore).

## Raspberry Pi deployment

The deployment target is Raspberry Pi OS Lite (64-bit), Debian 13 (Trixie),
with the distribution's Python 3.13 on a Pi Zero 2 W. Raspberry Pi's
[OS downloads](https://www.raspberrypi.com/software/operating-systems/) list
this model as compatible. Create a fresh virtual environment on the new card.

Use Debian's `python3-rpi.gpio` and `python3-smbus` packages for native hardware
bindings and a `--system-site-packages` virtual environment for the pinned
packages in [`requirements.txt`](requirements.txt).

The systemd service uses the tracked [`start.sh`](start.sh), which changes to
its own directory and launches `venv/bin/python`. Systemd orders startup
after networking. Useful operational commands are:

```sh
sudo systemctl status iris.service --no-pager
sudo systemctl restart iris.service
journalctl -u iris.service -f
```

Run the service from its project directory when testing manually, because it
reads `config.ini`, writes `iris.log`, and stores custom presets in
`presets.json` relative to the working directory.

## Web deployment

Publish the contents of `src/` as static files, including the generated
`src/config.js`.

The page loads Bootstrap, Bootstrap Icons, and the PubNub JavaScript SDK from
CDNs, so browser access requires those network requests to succeed.

## Clean rebuild

Rebuild one Pi at a time on a new card and keep the old card untouched until
the replacement has been tested. The two Pis use the same source and PubNub
keys, but each must have its own device name. Only one installation of a given
device identity should be online at a time.

### 1. Record and back up the current device

Before changing a Pi, record its hostname, device names, OS version, and
service configuration:

```sh
hostname
cat /etc/os-release
systemctl cat iris.service
cd "$HOME/iris"
git status --short --branch
cp -a config.ini "config.ini.backup.$(date +%Y%m%d%H%M%S)"
if [ -f presets.json ]; then
  cp -a presets.json "presets.json.backup.$(date +%Y%m%d%H%M%S)"
fi
```

Copy `config.ini` and, if present, `presets.json` off the old card to a secure
backup on your computer. Also retain the browser's `src/config.js` if it exists.
Create a fresh virtual environment during installation.
Keep the existing installation until the new installation has been verified.
Stop the old service before moving its device identity to the new installation:

```sh
sudo systemctl stop iris.service
```

### 2. Prepare the new card for headless access

In [Raspberry Pi Imager](https://www.raspberrypi.com/software/), choose
Raspberry Pi Zero 2 W and the latest Raspberry Pi OS Lite **64-bit, Trixie**
image. Select the new microSD card carefully:
writing an image erases the selected card.

Configure a hostname, your chosen non-root username/password, locale/timezone,
Wi-Fi SSID/password and wireless country, and enable SSH (prefer your public
key). The Zero 2 W needs **2.4 GHz Wi-Fi**.
Write and verify the image, power off the Pi, swap cards, then boot.
Connect from your computer using `ssh USER@HOSTNAME.local`; use the Pi's
router-assigned IP if mDNS is unavailable. Keep passwords and keys private.

Fit the Blinkt! and Button SHIM to the Pi's 40-pin GPIO header with power off,
using the manufacturer's orientation/stacking instructions and a suitable
power supply. A bare Zero 2 W may need a soldered header.
[Blinkt!](https://github.com/pimoroni/blinkt/blob/master/library/blinkt.py)
uses BCM GPIO 23/24.
[Button SHIM](https://github.com/pimoroni/button-shim/blob/master/library/buttonshim/__init__.py)
uses I2C bus 1 at address `0x3f`. Reserve these pins and address for Iris.

### 3. Install the system prerequisites

On Raspberry Pi OS, install Git, Python tooling, and the hardware libraries:

```sh
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git python3 python3-venv python3-dev build-essential \
  python3-rpi.gpio python3-smbus i2c-tools
sudo usermod -aG gpio,i2c "$USER"
sudo raspi-config nonint do_i2c 0
sudo reboot
```

Reconnect over SSH after reboot so the GPIO/I2C group changes apply. Check the
OS, interpreter and device permissions as the service user:

```sh
cat /etc/os-release
dpkg --print-architecture
python3 --version
id
ls -l /dev/gpiomem /dev/i2c-1
python3 -c 'import RPi.GPIO, smbus; print("Native hardware bindings imported")'
```

Python headers and `build-essential` support native dependency builds if a
wheel is unavailable (for example PubNub's cryptography dependency). Hardware
access requires `gpio` and `i2c` membership. Run Iris as the non-root service user.

### 4. Install Iris

Clone the `release` deployment branch (or copy an approved checkout that
tracks `origin/release`) into `$HOME/iris`, then create a fresh virtual
environment using the OS Python. `main` is for development; Pi installations
should follow `release`. Commands below run as the same non-root user chosen
in Imager:

```sh
git clone --branch release --single-branch \
  https://github.com/davehunt/iris.git "$HOME/iris"
cd "$HOME/iris"
git rev-parse HEAD
python3 -m venv --system-site-packages venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
```

Record the checkout SHA and `venv/bin/python -m pip freeze` for repeatability.
The requirements pin direct PyPI dependencies; native bindings follow OS
security updates.

### 5. Configure each Pi and restore data

Create the ignored device configuration from the template:

```sh
cd "$HOME/iris"
cp _config.ini config.ini
```

Edit `config.ini` so `device1.name` is the local device name and
`device2.name` is the other Pi. Set the PubNub `subscribe_key` and
`publish_key` from the Iris app. Use the same keys on both Pis and keep the file
private. Alternatively, restore the existing `config.ini` from your secure
backup instead of copying the template. Restore `presets.json` here too if
present; omitting it starts with built-in presets only. Ensure restored files
are owned by the service user and the directory is writable.

```sh
chmod 600 config.ini
chmod +x start.sh
venv/bin/python check_dependencies.py
venv/bin/python -c 'import blinkt, buttonshim, RPi.GPIO, smbus; print("Hardware drivers imported")'
venv/bin/python -B -m unittest discover -s tests -v
./start.sh
```

The manual run exercises the hardware and connects to PubNub; stop it with
Ctrl-C before starting systemd. PubNub needs working internet/DNS and a keyset
permitting publish, subscribe and presence for both devices' channels.
Preserve the existing keyset's access-control settings.

`check_dependencies.py` checks every pinned Iris requirement and its selected
transitive dependencies, including version constraints and environment markers.
It prints each missing/conflicting dependency and exits nonzero on failure.
Use this scoped check to validate Iris dependencies in the
`--system-site-packages` environment. Run the driver imports, offline tests
and hardware/PubNub checks as well.

For the web UI, copy `src/_config.js` to `src/config.js` and set both device
IDs, names, and the browser PubNub keys before publishing `src/`:

```sh
cp src/_config.js src/config.js
```

### 6. Install the service

The following creates `/etc/systemd/system/iris.service` using the checked-in
startup script, current SSH user's name and project directory. Run it as the
non-root user chosen in Imager. Paths containing spaces need appropriately
quoted systemd entries.

```sh
cd "$HOME/iris"
chmod +x start.sh
sudo tee /etc/systemd/system/iris.service >/dev/null <<EOF
[Unit]
Description=Iris Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/iris
ExecStart=$HOME/iris/start.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now iris.service
```

Enable the OS network wait-online service for `network-online.target` ordering,
and verify internet/PubNub connectivity after boot.

The working directory is intentionally the project directory: the service
reads `config.ini`, writes `iris.log`, and stores custom presets in
`presets.json` relative to it.

### 7. Verify before rebuilding the second Pi

Check the service and hardware locally:

```sh
systemctl status iris.service --no-pager
journalctl -u iris.service -n 50 --no-pager
```

Then open the published web UI, confirm both devices appear, load each
device's pixels and presets, and send a preset from one device to the other.
Only after that end-to-end test succeeds should the second Pi be rebuilt.
Check all five buttons, the Button SHIM indicator and all eight Blinkt! LEDs,
then reboot and confirm the service reconnects. Preserve the old card for
rollback; power down before swapping it back. For later updates, follow the
[automatic update and rollback guide](docs/automatic-updates.md); it explains
how to promote a tested revision and enable scheduled or manual updates.

## Automatic updates

For the Trixie Pi, follow the [automatic update setup](docs/automatic-updates.md)
to enable a nightly systemd timer and a manual update command. Updates follow
explicitly promoted, CI-tested commits on `release`, stage and check each
fast-forward revision before switching, preserve configuration and presets,
and roll back failed activations. Retention keeps the active release and two
successful rollback copies. Only a tested revision promoted by a maintainer
to `release` is installed on the Pi.

## Development notes

- `requirements-dev.txt` currently contains Ruff for Python linting.
- `presets.json` is created on first use and is intentionally untracked.
- The two devices must use distinct names and the same PubNub account/config.
- The service is hardware-specific; a local macOS run is useful for syntax
  checks but cannot exercise the LED, button, or I2C integrations.

Run the offline SDK compatibility smoke test with
`venv/bin/python -m unittest discover -s tests -v`. It exercises startup,
connection callbacks and pixel messages using the real PubNub SDK and Python
hardware drivers, with native hardware access and network requests mocked.
Use the on-Pi verification steps above to check hardware and live PubNub
delivery.

The Diwali tests in [`tests/test_diwali.py`](tests/test_diwali.py) also run
the web page's date gating and message dispatch with Node.js when `node` is on
`PATH`; they are skipped otherwise.
The Firefox tests in [`tests/test_firefox.py`](tests/test_firefox.py) cover frame
bounds, smooth motion, interruption, dispatch and deterministic browser/device
parity. The shared browser lifecycle tests cover its preview, Apply and Send
controls alongside the other special presets.
