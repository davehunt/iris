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

## Configuration

Runtime configuration is deliberately untracked:

- Copy [`_config.ini`](_config.ini) to `config.ini` on each Pi and set the
  device names and PubNub keys.
- Copy [`src/_config.js`](src/_config.js) to `src/config.js` for the web page
  and set the matching device IDs and browser PubNub keys.

The device names are also the PubNub user IDs and form the channel names. For
example, a device named `lokipizero2w` uses `lokipizero2w_control` and
`lokipizero2w_status`.

Never commit either generated configuration file: both are ignored by
[`.gitignore`](.gitignore).

## Raspberry Pi deployment

The recovered deployment uses Raspberry Pi OS/Debian 11, Python 3.9, and a
virtual environment at `/home/dave/iris/venv`. Install the pinned runtime
dependencies from [`requirements.txt`](requirements.txt) in that environment.
The hardware dependencies (`blinkt`, `buttonshim`, `RPi.GPIO`, and `smbus`)
must be installed on a Raspberry Pi rather than macOS.

The current service is started by `/etc/systemd/system/iris.service`:

```ini
[Service]
Type=simple
User=dave
WorkingDirectory=/home/dave
ExecStart=/home/dave/iris/start.sh
Restart=on-failure
```

The deployed `start.sh` waits for networking, changes to `/home/dave/iris`,
pulls the latest `origin` branch, and starts the virtual-environment Python
service. Useful operational commands are:

```sh
sudo systemctl status iris.service --no-pager
sudo systemctl restart iris.service
journalctl -u iris.service -f
```

Run the service from its project directory when testing manually, because it
reads `config.ini`, writes `iris.log`, and stores custom presets in
`presets.json` relative to the working directory.

## Web deployment

There is no frontend build step. Publish the contents of `src/` as static
files, including the generated `src/config.js`. The deployment address is
intentionally not documented here.

The page loads Bootstrap, Bootstrap Icons, and the PubNub JavaScript SDK from
CDNs, so browser access requires those network requests to succeed.

## Clean rebuild

Rebuild one Pi at a time and keep the existing installation available until
the replacement has been tested. The two Pis use the same source and PubNub
keys, but each must have its own device name.

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
cp -a presets.json "presets.json.backup.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
```

Keep the existing `/home/dave/iris` directory until the new installation has
been verified. If the rebuild uses the same directory, stop the service before
changing files:

```sh
sudo systemctl stop iris.service
```

### 2. Install the system prerequisites

On Raspberry Pi OS, install Git, Python tooling, and the hardware libraries:

```sh
sudo apt update
sudo apt install -y git python3 python3-venv python3-dev build-essential \
  i2c-tools
```

Ensure I2C is enabled for the Blinkt! and Button SHIM hardware, then reboot if
the setting was changed:

```sh
sudo raspi-config
sudo reboot
```

### 3. Install Iris

Clone this repository (or copy the approved checkout) into `/home/dave/iris`,
then create a fresh virtual environment and install the pinned dependencies:

```sh
git clone https://github.com/davehunt/iris.git /home/dave/iris
cd /home/dave/iris
python3 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
```

The `blinkt`, `buttonshim`, `RPi.GPIO`, and `smbus` packages are
hardware-specific and should be installed and tested on the Pi, not on the
development Mac.

### 4. Configure each Pi

Create the ignored device configuration from the template:

```sh
cd /home/dave/iris
cp _config.ini config.ini
```

Edit `config.ini` so `device1.name` is the local device name and
`device2.name` is the other Pi. Set the PubNub `subscribe_key` and
`publish_key` from the Iris app. Use the same keys on both Pis. Do not commit
this file.

For the web UI, copy `src/_config.js` to `src/config.js` and set both device
IDs, names, and the browser PubNub keys before publishing `src/`:

```sh
cp src/_config.js src/config.js
```

### 5. Install the service

Create `/home/dave/iris/start.sh` with the following contents, replacing
`/home/dave` if the service user or home directory differs:

```sh
#!/bin/bash
set -e
sleep 10
cd /home/dave/iris
exec /home/dave/iris/venv/bin/python /home/dave/iris/src/iris.py
```

Make it executable:

```sh
chmod +x /home/dave/iris/start.sh
```

Create `/etc/systemd/system/iris.service`:

```ini
[Unit]
Description=Iris Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=dave
WorkingDirectory=/home/dave/iris
ExecStart=/home/dave/iris/start.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start it:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now iris.service
```

The working directory is intentionally the project directory: the service
reads `config.ini`, writes `iris.log`, and stores custom presets in
`presets.json` relative to it.

### 6. Verify before rebuilding the second Pi

Check the service and hardware locally:

```sh
systemctl status iris.service --no-pager
journalctl -u iris.service -n 50 --no-pager
```

Then open the published web UI, confirm both devices appear, load each
device's pixels and presets, and send a preset from one device to the other.
Only after that end-to-end test succeeds should the second Pi be rebuilt.

## Development notes

- `requirements-dev.txt` currently contains Ruff for Python linting.
- `presets.json` is created on first use and is intentionally untracked.
- The two devices must use distinct names and the same PubNub account/config.
- The service is hardware-specific; a local macOS run is useful for syntax
  checks but cannot exercise the LED, button, or I2C integrations.
