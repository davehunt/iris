#!/usr/bin/python3
"""Root-owned coordinator; all downloaded code and builds run as the Iris user."""

import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import sys
import time
import uuid


CONTROL = Path("/var/lib/iris-update")
SERVICE = "iris.service"
DEPLOYMENT_BRANCH = "release"
TRUSTED_ORIGINS = {
    "https://github.com/davehunt/iris.git",
    "git@github.com:davehunt/iris.git",
}
RUNTIME = ("config.ini", "presets.json", "iris.log", "src/config.js")


def runtime_files(release, storage, attach=False):
    """Called without root privileges, including for runtime file migration."""
    shared = storage / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME:
        source = release / name
        target = shared / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise ValueError(f"Shared runtime file must be a regular file: {target}")
        if attach:
            if target.exists():
                if source.exists() or source.is_symlink():
                    raise ValueError(f"Candidate contains unexpected runtime data: {name}")
                source.symlink_to(target)
            continue
        if source.is_symlink():
            if source.resolve() != target.resolve():
                raise ValueError(f"Unexpected runtime symlink: {source}")
            continue
        if source.exists():
            if target.exists():
                raise ValueError(f"Both release and shared runtime data exist: {name}")
            os.rename(source, target)
        elif not target.exists():
            if name == "config.ini":
                raise ValueError("Restore config.ini before enabling updates")
            if name == "src/config.js":
                continue
            target.write_text('{"presets": []}\n' if name == "presets.json" else "")
        if name == "config.ini":
            target.chmod(0o600)
        source.symlink_to(target)


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as file:
        json.dump(data, file)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def systemd_quote_path(path):
    value = str(path).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if "\n" in value or "\r" in value:
        raise ValueError(f"Path cannot be represented in a systemd unit: {path}")
    return f'"{value}"'


def install_mount_dependencies(install, storage, systemd_dir=Path("/etc/systemd/system")):
    paths = " ".join(systemd_quote_path(path) for path in (install, storage))
    content = f"[Unit]\nRequiresMountsFor={paths}\n"
    dropins = [
        systemd_dir / f"{service}.d/90-iris-update-mounts.conf"
        for service in ("iris.service", "iris-update.service",
                        "iris-update-recover.service")
    ]
    for dropin in dropins:
        if dropin.is_symlink() or (dropin.exists() and not dropin.is_file()):
            raise ValueError(f"Invalid mount dependency drop-in: {dropin}")
        if dropin.exists() and dropin.read_text() != content:
            raise ValueError(f"Existing mount dependency drop-in differs: {dropin}")
    for dropin in dropins:
        dropin.parent.mkdir(parents=True, exist_ok=True)
        if not dropin.exists():
            dropin.write_text(content)


class Updater:
    def __init__(self, config, control=CONTROL):
        self.config = config
        self.control = control
        self.install = Path(config["install"])
        self.storage = Path(config["storage"]).resolve()
        self.account = pwd.getpwnam(config["user"])

    def run(self, *args, cwd=None, user=False):
        command = list(args)
        if user:
            command = [
                "/usr/sbin/runuser", "-u", self.account.pw_name, "--",
                "/usr/bin/env", "-i",
                f"HOME={self.account.pw_dir}",
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE=1",
                "GIT_TERMINAL_PROMPT=0",
                *command,
            ]
        with subprocess.Popen(
            command, cwd=cwd, text=True, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=1200)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                raise
            if process.returncode:
                raise subprocess.CalledProcessError(
                    process.returncode, command, output=stdout, stderr=stderr
                )
        if stderr.strip():
            logging.info("%s", stderr.strip())
        return stdout.strip()

    def git(self, path, *args):
        return self.run("/usr/bin/git", *args, cwd=path, user=True)

    def owned_directory(self, path):
        self.run("/usr/bin/install", "-d", "-m", "700", str(path), user=True)

    def state(self):
        path = self.control / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def save_state(self, state):
        write_json(self.control / "state.json", state)

    def validate_source(self, path):
        if self.config["branch"] != DEPLOYMENT_BRANCH:
            raise ValueError("Updates require the release deployment branch")
        if self.git(path, "status", "--porcelain", "--untracked-files=normal"):
            raise ValueError(f"Source has local changes: {path}")
        if self.git(path, "remote", "get-url", "origin") != self.config["origin"]:
            raise ValueError("Origin differs from the configured trusted origin")
        upstream = self.git(path, "rev-parse", "--abbrev-ref",
                            "--symbolic-full-name", "@{upstream}")
        if upstream != f"origin/{self.config['branch']}":
            raise ValueError("Tracked branch differs from the configured update branch")
        for name in RUNTIME:
            if self.git(path, "ls-files", "--", name):
                raise ValueError(f"Runtime data must be untracked: {name}")
        for name in ("start.sh", "requirements.txt", "check_dependencies.py",
                     "tests/test_compatibility.py", "src/iris.py"):
            file = path / name
            if not file.is_file() or file.is_symlink():
                raise ValueError(f"Required source file is missing or a symlink: {name}")
        return self.git(path, "rev-parse", "HEAD")

    def validate_service(self):
        user = self.run("/usr/bin/systemctl", "show", SERVICE, "-p", "User", "--value")
        directory = self.run("/usr/bin/systemctl", "show", SERVICE,
                             "-p", "WorkingDirectory", "--value")
        command = self.run("/usr/bin/systemctl", "show", SERVICE,
                           "-p", "ExecStart", "--value")
        if (user != self.config["user"] or directory != str(self.install)
                or f"path={self.install}/start.sh ;" not in command):
            raise ValueError("iris.service must use the configured user and installation path")

    def link(self, destination):
        temporary = self.install.with_name(f".iris-link-{uuid.uuid4().hex}")
        temporary.symlink_to(destination, target_is_directory=True)
        os.replace(temporary, self.install)

    def share_runtime(self, release):
        self.run("/usr/bin/python3", str(Path(__file__).resolve()),
                 "--share-runtime", str(release), "--storage", str(self.storage),
                 user=True)

    def connect_runtime(self, release):
        self.run("/usr/bin/python3", str(Path(__file__).resolve()),
                 "--connect-runtime", str(release), "--storage", str(self.storage),
                 user=True)

    def healthy_start(self):
        self.run("/usr/bin/systemctl", "reset-failed", SERVICE)
        self.run("/usr/bin/systemctl", "start", SERVICE)
        first = None
        for _ in range(15):
            status = self.run("/usr/bin/systemctl", "show", SERVICE,
                              "-p", "ActiveState", "-p", "SubState",
                              "-p", "NRestarts", "-p", "MainPID")
            values = dict(line.split("=", 1) for line in status.splitlines())
            signature = (values.get("MainPID"), values.get("NRestarts"))
            if (values.get("ActiveState") != "active"
                    or values.get("SubState") != "running"
                    or signature[0] in (None, "0") or signature[1] != "0"
                    or (first is not None and signature != first)):
                raise RuntimeError("Iris did not remain running during activation")
            first = signature
            time.sleep(1)

    def recover(self, start=True):
        state = self.state()
        transaction = state.get("transaction")
        if not transaction:
            return
        logging.warning("Recovering interrupted/failed activation")
        if start:
            self.run("/usr/bin/systemctl", "stop", SERVICE)
        previous = Path(transaction["previous"])
        # Adoption may have been interrupted before the original directory moved.
        if not previous.exists() and self.install.is_dir() and not self.install.is_symlink():
            os.rename(self.install, previous)
        self.share_runtime(previous)
        if previous != self.install:
            self.link(previous)
        if start:
            try:
                self.healthy_start()
            except BaseException:
                self.run("/usr/bin/systemctl", "stop", SERVICE)
                logging.error("Rollback source restored, but Iris failed to start; "
                              "service stopped and recovery state retained")
                raise
        state.pop("transaction")
        state["rejected"] = transaction["revision"]
        self.save_state(state)
        logging.warning("Previous release restored: %s", previous)

    def adopt(self):
        revision = self.validate_source(self.install)
        self.validate_service()
        self.run("/usr/bin/systemctl", "is-active", "--quiet", SERVICE)
        if self.install.is_symlink():
            raise ValueError("Initial installation must be a real directory")
        if (not (self.install / "config.ini").is_file()
                or (self.install / "config.ini").is_symlink()):
            raise ValueError("Restore config.ini before enabling updates")
        if (self.storage / "shared").exists():
            raise ValueError("Existing shared data needs review before initial adoption")
        for name in RUNTIME:
            if (self.install / name).is_symlink():
                raise ValueError(f"Restore a local runtime file before adoption: {name}")
        self.owned_directory(self.storage / "releases")
        if os.stat(self.install).st_dev != os.stat(self.storage / "releases").st_dev:
            raise ValueError("Installation and release storage must use the same filesystem")
        previous = self.storage / "releases" / f"initial-{revision}-{uuid.uuid4().hex}"
        write_json(self.control / "config.json", self.config)
        self.save_state({"transaction": {"previous": str(previous), "revision": revision}})
        try:
            self.run("/usr/bin/systemctl", "stop", SERVICE)
            os.rename(self.install, previous)
            self.share_runtime(previous)
            self.link(previous)
            self.healthy_start()
        except BaseException:
            self.recover()
            raise
        self.save_state({"successful": [str(previous)]})
        logging.info("Managed installation enabled at %s", self.install)

    def stage(self, current):
        self.owned_directory(self.storage / "releases")
        candidate = self.storage / "releases" / f"release-{uuid.uuid4().hex}"
        try:
            self.run("/usr/bin/git", "clone", "--single-branch", "--branch",
                     self.config["branch"], "--", self.config["origin"], str(candidate),
                     user=True)
            revision = self.validate_source(candidate)
            ancestor = self.git(current, "rev-parse", "HEAD")
            self.git(candidate, "merge-base", "--is-ancestor", ancestor, revision)
        except BaseException:
            self.discard(candidate)
            raise
        return candidate, revision

    def discard(self, candidate):
        retained = self.protected_releases()
        if candidate in retained or self.state().get("transaction"):
            return
        if (candidate.parent != self.storage / "releases"
                or not candidate.name.startswith("release-") or candidate.is_symlink()):
            raise ValueError("Refusing to discard a path outside the staging area")
        if candidate.exists():
            self.run("/usr/bin/python3", "-c",
                     "import shutil,sys; shutil.rmtree(sys.argv[1])",
                     str(candidate), user=True)

    def verified_release(self, path, scheduled=False):
        path = Path(path)
        if (path.parent != self.storage / "releases" or path.resolve() != path
                or path.is_symlink()
                or not re.fullmatch(
                    r"(release-[0-9a-f]{32}|initial-[0-9a-f]{40,64}-[0-9a-f]{32})",
                    path.name,
                )):
            raise ValueError(f"Invalid managed release path: {path}")
        if not path.exists():
            return path
        if not path.is_dir() or path.stat().st_uid != self.account.pw_uid:
            raise ValueError(f"Invalid managed release ownership/type: {path}")
        if scheduled:
            return path
        if self.git(path, "rev-parse", "--show-toplevel") != str(path):
            raise ValueError(f"Release is not an independent checkout: {path}")
        if self.git(path, "remote", "get-url", "origin") != self.config["origin"]:
            raise ValueError(f"Release has unexpected origin: {path}")
        return path

    def protected_releases(self):
        state = self.state()
        protected = {self.install.resolve()}
        for name in ("previous",):
            if state.get(name):
                protected.add(Path(state[name]))
        if state.get("transaction"):
            protected.add(Path(state["transaction"]["previous"]))
        return protected

    def prune(self):
        state = self.state()
        # A pending transaction owns all cleanup decisions until recovered.
        if state.get("transaction"):
            logging.info("Pruning deferred while recovery is pending")
            return
        active = self.install.resolve()
        history = list(dict.fromkeys(state.get("successful", [])))
        retained = [str(active)] + [name for name in history if Path(name) != active][:2]
        protected = self.protected_releases() | {Path(name) for name in retained}
        obsolete = [Path(name) for name in history if Path(name) not in protected]
        scheduled = state.get("pruning", [])
        if any(Path(name) in protected for name in scheduled):
            raise ValueError("Pending pruning includes a protected release")
        obsolete = list(dict.fromkeys([*map(Path, scheduled), *obsolete]))
        # Validate the entire deletion set before removing any release.
        for path in obsolete:
            self.verified_release(path, scheduled=str(path) in scheduled)
            if not path.exists() and str(path) not in scheduled:
                raise ValueError(f"Successful release unexpectedly missing: {path}")
        if obsolete:
            state["pruning"] = [str(path) for path in obsolete]
            self.save_state(state)
        for path in obsolete:
            logging.info("Pruning old successful release %s", path)
            if path.exists():
                self.run("/usr/bin/python3", "-c",
                         "import shutil,sys; shutil.rmtree(sys.argv[1])", str(path), user=True)
            if str(path) in history:
                history.remove(str(path))
            state["pruning"].remove(str(path))
            if not state["pruning"]:
                state.pop("pruning")
            state["successful"] = history
            self.save_state(state)

    def check_candidate(self, candidate):
        logging.info("Building and checking staged release %s", candidate)
        self.run("/usr/bin/python3", "-m", "venv", "--system-site-packages",
                 str(candidate / "venv"), user=True)
        python = str(candidate / "venv/bin/python")
        for arguments in (
            ("-m", "pip", "install", "--upgrade", "pip"),
            ("-m", "pip", "install", "-r", "requirements.txt"),
            ("check_dependencies.py",),
            ("-c", "import RPi.GPIO, smbus, blinkt, buttonshim"),
            ("-B", "-m", "unittest", "discover", "-s", "tests", "-v"),
        ):
            self.run(python, *arguments, cwd=candidate, user=True)
        self.run("/bin/sh", "-n", "start.sh", cwd=candidate, user=True)
        self.validate_source(candidate)

    def activate(self, candidate, revision, retained=False):
        previous = self.install.resolve()
        state = self.state()
        state["transaction"] = {"previous": str(previous), "revision": revision}
        self.save_state(state)
        try:
            self.run("/usr/bin/systemctl", "stop", SERVICE)
            self.share_runtime(previous)
            if retained:
                self.share_runtime(candidate)
            else:
                self.connect_runtime(candidate)
            self.link(candidate)
            self.healthy_start()
        except BaseException:
            self.recover()
            raise
        state.pop("transaction")
        state["previous"] = str(previous)
        state["successful"] = list(dict.fromkeys(
            [str(candidate), str(previous), *state.get("successful", [])]
        ))
        state.pop("rejected", None)
        self.save_state(state)
        logging.info("Activated %s; retained previous release %s", revision, previous)

    def update(self, retry=False):
        self.validate_service()
        self.recover()
        current = self.install.resolve()
        revision = self.validate_source(current)
        self.run("/usr/bin/systemctl", "is-active", "--quiet", SERVICE)
        tip = self.run("/usr/bin/git", "ls-remote", "--exit-code",
                       self.config["origin"], f"refs/heads/{self.config['branch']}",
                       user=True).split()[0]
        if tip == revision:
            logging.info("Already at %s", revision)
            self.prune()
            return
        if tip == self.state().get("rejected") and not retry:
            raise ValueError(f"Activation previously failed/was rolled back at {tip}; "
                             "use --retry after resolving the failure")
        candidate, target = self.stage(current)
        try:
            if target == revision:
                logging.info("Already at %s", revision)
                return
            if target == self.state().get("rejected") and not retry:
                raise ValueError(f"Activation previously failed/was rolled back at {target}; "
                                 "use --retry after resolving the failure")
            self.check_candidate(candidate)
            # Refuse concurrent source or installation changes during staging.
            if self.install.resolve() != current or self.validate_source(current) != revision:
                raise ValueError("Installation changed while staging")
            self.run("/usr/bin/systemctl", "is-active", "--quiet", SERVICE)
            self.activate(candidate, target)
        finally:
            self.discard(candidate)
        self.prune()

    def rollback(self):
        self.validate_service()
        self.recover()
        previous = self.state().get("previous")
        if not previous:
            raise ValueError("No previous managed release is available")
        current_revision = self.git(self.install.resolve(), "rev-parse", "HEAD")
        candidate = Path(previous)
        self.validate_source(candidate)
        self.activate(candidate, self.git(candidate, "rev-parse", "HEAD"), retained=True)
        state = self.state()
        state["rejected"] = current_revision
        self.save_state(state)
        self.prune()


def configure(install, user, control):
    if not install.is_dir() or install.is_symlink():
        raise ValueError("The Iris installation must be a real directory")
    owner = pwd.getpwuid(install.stat().st_uid)
    user = user or owner.pw_name
    account = pwd.getpwnam(user)
    if (account.pw_uid == 0 or account.pw_uid != owner.pw_uid
            or install != Path(account.pw_dir) / "iris"):
        raise ValueError("Use the non-root Iris user's ~/iris installation")
    config = {"user": user, "install": str(install),
              "storage": str(Path(account.pw_dir) / ".local/share/iris-update")}
    updater = Updater(config, control)
    origin = updater.git(install, "remote", "get-url", "origin")
    if origin not in TRUSTED_ORIGINS:
        raise ValueError("Origin must be the official davehunt/iris repository")
    upstream = updater.git(install, "rev-parse", "--abbrev-ref",
                           "--symbolic-full-name", "@{upstream}")
    if upstream != f"origin/{DEPLOYMENT_BRANCH}":
        raise ValueError("Track origin/release before configuring updates")
    branch = upstream.removeprefix("origin/")
    updater.git(install, "check-ref-format", f"refs/heads/{branch}")
    config.update(origin=origin, branch=branch)
    updater.run("/usr/bin/git", "ls-remote", "--exit-code", origin,
                f"refs/heads/{DEPLOYMENT_BRANCH}", user=True)
    logging.info("Configured source: %s branch %s", origin, branch)
    install_mount_dependencies(install, Path(config["storage"]))
    updater.run("/usr/bin/systemctl", "daemon-reload")
    updater.adopt()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--configure", type=Path, metavar="INSTALL")
    actions.add_argument("--rollback", action="store_true")
    actions.add_argument("--retry", action="store_true")
    actions.add_argument("--recover-only", action="store_true")
    actions.add_argument("--share-runtime", type=Path)
    actions.add_argument("--connect-runtime", type=Path)
    parser.add_argument("--storage", type=Path)
    parser.add_argument("--user", help="Iris account (defaults to the installation owner)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.share_runtime or args.connect_runtime:
        if os.geteuid() == 0 or args.storage is None:
            parser.error("Runtime migration requires a non-root user and --storage")
        runtime_files(args.share_runtime or args.connect_runtime, args.storage,
                      attach=bool(args.connect_runtime))
        return 0
    if os.geteuid() != 0:
        parser.error("Run through iris-update.service or as root for configuration/rollback")
    CONTROL.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Start the boot guard before taking the lock: it acquires the same lock,
    # and iris.service requires it during subsequent activation/recovery.
    if not args.configure and not args.recover_only:
        try:
            subprocess.run(
                ["/usr/bin/systemctl", "start", "iris-update-recover.service"],
                check=True, timeout=120,
            )
        except subprocess.SubprocessError as error:
            logging.error("Boot recovery service failed: %s", error)
            return 1
    with (CONTROL / "update.lock").open("a") as lock:
        logging.info("Waiting for exclusive updater lock")
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            config_path = CONTROL / "config.json"
            if args.configure:
                if config_path.exists():
                    raise ValueError("Updater is already configured")
                configure(args.configure, args.user, CONTROL)
            else:
                updater = Updater(json.loads(config_path.read_text()))
                if args.recover_only:
                    updater.recover(start=False)
                elif args.rollback:
                    updater.rollback()
                else:
                    updater.update(retry=args.retry)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            logging.error("Update failed: %s", error)
            if isinstance(error, subprocess.CalledProcessError):
                logging.error("%s", error.stderr or error.stdout)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
