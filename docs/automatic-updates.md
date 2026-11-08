# Updating Iris on a Raspberry Pi

This guide is for an existing Iris installation on Raspberry Pi OS Trixie.
The updater follows the `release` branch. It does not install changes from
`main` automatically: a maintainer first promotes a tested revision to
`release`.

## Set up updates once

Before starting, make sure Iris is running from a clean Git checkout at
`$HOME/iris` and uses the official Iris repository. The updater preserves the
required `config.ini` and any existing `presets.json` outside versioned
releases, so you will not need to restore them during future updates. As with
any one-time migration, keep a separate backup of important settings and
presets before proceeding.

First check the checkout and Iris service:

```sh
cd "$HOME/iris"
git status --short --branch
git branch --show-current
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git remote get-url origin
systemctl show iris.service -p User -p WorkingDirectory -p ExecStart
sudo systemctl is-active iris.service
```

The working tree must be clean, the remote must be
`https://github.com/davehunt/iris.git` or `git@github.com:davehunt/iris.git`,
and the service must run as the owner of `$HOME/iris` from that directory.
Keep the current `iris.service` configuration and its existing drop-ins. The
setup below adds updater-specific drop-ins; it does not replace your service
configuration.

Fetch the deployment branch and check that the installed revision can safely
fast-forward to it. Do this before stopping Iris:

```sh
git fetch origin
git show-ref --verify refs/remotes/origin/release
git merge-base --is-ancestor HEAD origin/release
```

The fetch must succeed, `release` must exist, and the ancestry check must pass.
If the checkout already tracks `origin/release`, it is ready for setup. If it
tracks another branch, switch to `release` and update dependencies while Iris
is stopped:

```sh
sudo systemctl stop iris.service &&
(
  if git show-ref --quiet --verify refs/heads/release; then
    git switch release &&
    git branch --set-upstream-to=origin/release release &&
    git merge --ff-only origin/release
  else
    git switch --track -c release origin/release
  fi
) &&
venv/bin/python -m pip install -r requirements.txt &&
venv/bin/python check_dependencies.py &&
venv/bin/python -c 'import RPi.GPIO, smbus, blinkt, buttonshim' &&
venv/bin/python -B -m unittest discover -s tests -v &&
sudo systemctl start iris.service &&
systemctl status iris.service --no-pager
```

The `&&` chain stops at the first error. If it stops before the final
`systemctl start`, start Iris yourself before investigating:
`sudo systemctl start iris.service`. A failed fetch or check above happens
before the service is stopped, so Iris remains running.

Install the updater and its systemd services from the checkout. Run these
commands as the installation owner:

```sh
cd "$HOME/iris"
sudo install -d -m 755 /usr/local/libexec
sudo install -o root -g root -m 644 update_iris.py /usr/local/libexec/iris-update.py
sudo install -o root -g root -m 644 \
  systemd/iris-update.service systemd/iris-update.timer \
  systemd/iris-update-recover.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo /usr/bin/python3 /usr/local/libexec/iris-update.py \
  --configure "$HOME/iris"
```

The setup command adopts the existing checkout and makes `$HOME/iris` the
stable path to the active release. It briefly stops and restarts Iris; if
activation fails, it restores the original checkout. It moves `config.ini`
and any existing presets into persistent storage outside versioned releases,
then keeps them available at the same `$HOME/iris/...` paths. The directory
must have a valid `config.ini`, and the Iris systemd service must run as the
owner of `$HOME/iris` with that directory as its working directory.

Enable boot recovery and connect it to the Iris service:

```sh
sudo systemctl enable --now iris-update-recover.service
sudo install -d -m 755 /etc/systemd/system/iris.service.d
sudo install -o root -g root -m 644 systemd/95-managed-updates.conf \
  /etc/systemd/system/iris.service.d/95-managed-updates.conf
sudo systemctl daemon-reload
sudo systemctl restart iris.service
```

## Run an update manually

You can check for updates at any time:

```sh
sudo systemctl start iris-update.service
sudo journalctl -u iris-update.service -n 100 --no-pager
```

The journal reports whether Iris was already current, an update succeeded, or
why an update failed. The updater downloads the latest `release` revision,
builds and tests it while Iris is still running, then switches releases. If
the new version does not stay running, it restores the previous version.

## Enable or pause nightly updates

After confirming a manual update works, enable the nightly check:

```sh
sudo systemctl enable --now iris-update.timer
systemctl list-timers iris-update.timer --no-pager
```

It checks around 03:00 local time, with up to 30 minutes of random delay. If
the Pi is off at that time, the missed check runs after the next boot. To pause
nightly checks:

```sh
sudo systemctl disable --now iris-update.timer
```

Manual checks continue to work while the timer is disabled.

## Roll back a successful update

To switch back to the previous successful release:

```sh
sudo /usr/bin/python3 /usr/local/libexec/iris-update.py --rollback
```

The updater keeps the active release and two recent successful releases.
Configuration, presets and logs are kept separately from release code, so
they remain available after an update or rollback. If an update failed to
activate, it will not retry that same revision automatically. Resolve the
problem first, then explicitly retry it with:

```sh
sudo /usr/bin/python3 /usr/local/libexec/iris-update.py --retry
```

## Where updates come from

Pull requests and pushes to `main` run the `Iris checks` workflow. A
maintainer promotes a reviewed revision to `release` after its checks pass;
only then can Pis install it. New changes on `main` are not sent to Pis
automatically.

The updater checks Iris's local service and tests before switching code, but
it cannot check the LEDs, buttons or live PubNub connection. Verify those
after the first update and after changes that affect the hardware or messaging.
