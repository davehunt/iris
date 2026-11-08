import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from update_iris import (
    Updater,
    install_mount_dependencies,
    runtime_files,
    write_json,
)


class LocalUpdater(Updater):
    """Real local Git/file operations, with builds and systemd kept offline."""

    def __init__(self, *args):
        super().__init__(*args)
        self.running = True
        self.fail_start = 0
        self.stops = 0
        self.build_failure = False
        self.build_hook = lambda: None
        self.commands = []

    def run(self, *args, cwd=None, user=False):
        self.commands.append((args, user, cwd))
        if args[0] == "/usr/bin/git":
            return subprocess.run(
                [shutil.which("git"), *args[1:]], cwd=cwd, check=True,
                text=True, capture_output=True,
            ).stdout.strip()
        if args[0] == "/usr/bin/systemctl":
            action = args[1]
            if action == "stop":
                self.stops += 1
                self.running = False
            elif action == "start":
                self.running = self.fail_start == 0
                self.fail_start = max(0, self.fail_start - 1)
            elif action == "is-active" and not self.running:
                raise subprocess.CalledProcessError(3, args, stderr="inactive")
            elif action == "show":
                if "User" in args:
                    return self.config["user"]
                if "WorkingDirectory" in args:
                    return str(self.install)
                if "ExecStart" in args:
                    return f"{{ path={self.install}/start.sh ; argv[]=start.sh ; }}"
                return (
                    f"ActiveState={'active' if self.running else 'failed'}\n"
                    f"SubState={'running' if self.running else 'failed'}\n"
                    f"MainPID={'123' if self.running else '0'}\nNRestarts=0"
                )
            return ""
        if not user:
            raise AssertionError(f"Downloaded code was run as root: {args}")
        if args[0] == "/usr/bin/install":
            Path(args[-1]).mkdir(parents=True, exist_ok=True)
            return ""
        if "--share-runtime" in args or "--connect-runtime" in args:
            attach = "--connect-runtime" in args
            action = "--connect-runtime" if attach else "--share-runtime"
            runtime_files(Path(args[args.index(action) + 1]),
                          Path(args[args.index("--storage") + 1]), attach=attach)
            return ""
        if args[1:3] == ("-c", "import shutil,sys; shutil.rmtree(sys.argv[1])"):
            shutil.rmtree(args[-1])
            return ""
        if self.build_failure:
            raise subprocess.CalledProcessError(1, args, stderr="build failed")
        self.build_hook()
        return ""


class UpdateTests(unittest.TestCase):
    def git(self, path, *args):
        return subprocess.run(
            [shutil.which("git"), *args], cwd=path, check=True, text=True,
            capture_output=True,
        ).stdout.strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "origin.git"
        self.git(self.root, "init", "--bare", str(self.remote))
        self.seed = self.root / "seed"
        self.git(self.root, "clone", str(self.remote), str(self.seed))
        self.git(self.seed, "checkout", "-b", "main")
        for name in ("start.sh", "requirements.txt", "check_dependencies.py",
                     "tests/test_compatibility.py", "src/iris.py"):
            path = self.seed / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# offline source fixture\n")
        (self.seed / ".gitignore").write_text(
            "config.ini\npresets.json\niris.log*\nsrc/config.js\nvenv\n"
        )
        self.commit("initial")
        self.git(self.seed, "push", "origin", "main:release")
        self.install = self.root / "iris"
        self.git(self.root, "clone", "--branch", "release", str(self.remote), str(self.install))
        (self.install / "config.ini").write_text("private config fixture")
        (self.install / "presets.json").write_text('{"presets": ["initial"]}')
        (self.install / "iris.log").write_text("old log")
        self.control = self.root / "control"
        self.control.mkdir()
        user = pwd.getpwuid(os.getuid()).pw_name
        self.updater = LocalUpdater(
            {"install": str(self.install), "storage": str(self.root / "storage"),
             "user": user, "origin": str(self.remote), "branch": "release"},
            self.control,
        )
        self.sleep = patch("update_iris.time.sleep")
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def commit(self, message):
        self.git(self.seed, "add", ".")
        self.git(self.seed, "-c", "user.name=Offline Test",
                 "-c", "user.email=offline@example.invalid", "commit", "-m", message)
        self.git(self.seed, "push", "-u", "origin", "main")

    def advance(self):
        (self.seed / "src/iris.py").write_text(f"# new revision {os.urandom(8).hex()}\n")
        self.commit("update")
        self.git(self.seed, "push", "origin", "main:release")
        return self.git(self.seed, "rev-parse", "HEAD")

    def test_adoption_update_shares_freshest_data_and_keeps_stable_venv_path(self):
        self.updater.adopt()
        previous = self.install.resolve()
        self.assertTrue(self.install.is_symlink())
        target = self.advance()

        def live_write():
            (self.install / "presets.json").write_text('{"presets": ["fresh"]}')

        self.updater.build_hook = live_write
        self.updater.update()
        active = self.install.resolve()
        self.assertNotEqual(active, previous)
        self.assertEqual(self.git(active, "rev-parse", "HEAD"), target)
        self.assertEqual((active / "presets.json").read_text(), '{"presets": ["fresh"]}')
        self.assertEqual((previous / "presets.json").resolve(),
                         (active / "presets.json").resolve())
        self.assertEqual((active / "config.ini").read_text(), "private config fixture")
        builds = [args for args, _, _ in self.updater.commands if "venv" in args]
        self.assertEqual(builds[0][-1], str(active / "venv"))
        self.assertEqual(self.updater.state()["previous"], str(previous))

    def test_no_change_never_builds_or_stops_service(self):
        self.updater.adopt()
        stops = self.updater.stops
        self.updater.build_failure = True
        self.updater.update()
        self.assertEqual(self.updater.stops, stops)

    def test_build_failure_keeps_running_release(self):
        self.updater.adopt()
        previous = self.install.resolve()
        stops = self.updater.stops
        self.advance()
        self.updater.build_failure = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.updater.update()
        self.assertEqual(self.install.resolve(), previous)
        self.assertEqual(self.updater.stops, stops)
        self.assertTrue(self.updater.running)

    def test_failed_activation_rolls_back_and_blocks_same_revision(self):
        self.updater.adopt()
        previous = self.install.resolve()
        target = self.advance()
        self.updater.fail_start = 1
        with self.assertRaisesRegex(RuntimeError, "remain running"):
            self.updater.update()
        self.assertEqual(self.install.resolve(), previous)
        self.assertTrue(self.updater.running)
        self.assertEqual(self.updater.state()["rejected"], target)
        stops = self.updater.stops
        with self.assertRaisesRegex(ValueError, "previously failed"):
            self.updater.update()
        self.assertEqual(self.updater.stops, stops)

    def test_failed_rollback_stops_restart_attempts_and_retains_recovery_state(self):
        self.updater.adopt()
        previous = self.install.resolve()
        self.advance()
        self.updater.fail_start = 2
        with self.assertRaises(RuntimeError):
            self.updater.update()
        self.assertEqual(self.install.resolve(), previous)
        self.assertFalse(self.updater.running)
        self.assertIn("transaction", self.updater.state())

    def test_dirty_source_or_changed_origin_fails_before_downtime(self):
        self.updater.adopt()
        self.advance()
        stops = self.updater.stops
        (self.install / "src/iris.py").write_text("# local edit\n")
        with self.assertRaisesRegex(ValueError, "local changes"):
            self.updater.update()
        self.assertEqual(self.updater.stops, stops)
    def test_changed_origin_or_tracking_branch_fails_before_fetch(self):
        self.updater.adopt()
        stops = self.updater.stops
        self.git(self.install, "remote", "set-url", "origin", "https://example.invalid")
        with self.assertRaisesRegex(ValueError, "Origin differs"):
            self.updater.update()
        self.git(self.install, "remote", "set-url", "origin", str(self.remote))
        self.git(self.install, "config", "branch.release.merge", "refs/heads/other")
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            self.updater.update()
        self.assertEqual(self.updater.stops, stops)

    def test_boot_recovery_repairs_pointer_without_starting_service(self):
        self.updater.adopt()
        previous = self.install.resolve()
        revision = self.advance()
        candidate, _ = self.updater.stage(previous)
        self.updater.connect_runtime(candidate)
        self.updater.link(candidate)
        write_json(self.control / "state.json",
                   {"transaction": {"previous": str(previous), "revision": revision}})
        self.updater.running = False
        stops = self.updater.stops
        self.updater.recover(start=False)
        self.assertEqual(self.install.resolve(), previous)
        self.assertFalse(self.updater.running)
        self.assertEqual(self.updater.stops, stops)

    def test_interrupted_initial_move_completes_managed_recovery(self):
        previous = self.root / "storage/releases/initial-interrupted"
        previous.parent.mkdir(parents=True)
        write_json(self.control / "state.json",
                   {"transaction": {"previous": str(previous), "revision": "initial"}})
        self.updater.recover(start=False)
        self.assertTrue(self.install.is_symlink())
        self.assertEqual(self.install.resolve(), previous.resolve())
        self.assertEqual((self.install / "config.ini").read_text(),
                         "private config fixture")

    def test_local_edits_during_staging_abort_before_switch(self):
        self.updater.adopt()
        previous = self.install.resolve()
        stops = self.updater.stops
        self.advance()
        self.updater.build_hook = lambda: (self.install / "src/iris.py").write_text(
            "# edited while staging\n"
        )
        with self.assertRaisesRegex(ValueError, "local changes"):
            self.updater.update()
        self.assertEqual(self.install.resolve(), previous)
        self.assertEqual(self.updater.stops, stops)

    def test_retry_can_activate_previously_rejected_commit(self):
        self.updater.adopt()
        target = self.advance()
        self.updater.fail_start = 1
        with self.assertRaises(RuntimeError):
            self.updater.update()
        self.updater.update(retry=True)
        self.assertEqual(self.git(self.install, "rev-parse", "HEAD"), target)
        self.assertNotIn("rejected", self.updater.state())

    def test_shared_data_conflict_is_explicit_and_preserves_both_files(self):
        shared = self.root / "shared-runtime/shared"
        shared.mkdir(parents=True)
        (shared / "config.ini").write_text("other private fixture")
        with self.assertRaisesRegex(ValueError, "Both release and shared"):
            runtime_files(self.install, shared.parent)
        self.assertEqual((self.install / "config.ini").read_text(), "private config fixture")
        self.assertEqual((shared / "config.ini").read_text(), "other private fixture")

    def test_venv_entrypoints_survive_source_pointer_changes(self):
        release = self.root / "final-release"
        release.mkdir()
        environment = release / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(environment)], check=True,
            capture_output=True, text=True,
        )
        pointer = self.root / "stable-install"
        pointer.symlink_to(release, target_is_directory=True)
        prefix = subprocess.run(
            [str(pointer / "venv/bin/python"), "-c", "import sys; print(sys.prefix)"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(Path(prefix).resolve(), environment.resolve())
        self.assertIn(str(environment), (environment / "bin/pip").read_text())

    def test_main_changes_wait_for_explicit_release_promotion(self):
        self.updater.adopt()
        previous = self.install.resolve()
        (self.seed / "src/iris.py").write_text("# only on main\n")
        self.commit("main only")
        stops = self.updater.stops
        self.updater.update()
        self.assertEqual(self.install.resolve(), previous)
        self.assertEqual(self.updater.stops, stops)
        self.git(self.seed, "push", "origin", "main:release")
        self.updater.update()
        self.assertNotEqual(self.install.resolve(), previous)

    def test_missing_release_branch_fails_without_fallback(self):
        self.updater.adopt()
        previous = self.install.resolve()
        stops = self.updater.stops
        self.git(self.seed, "push", "origin", "--delete", "release")
        with self.assertRaises(subprocess.CalledProcessError):
            self.updater.update()
        self.assertEqual(self.install.resolve(), previous)
        self.assertEqual(self.updater.stops, stops)

    def test_main_configuration_is_rejected_before_adoption(self):
        self.updater.config["branch"] = "main"
        with self.assertRaisesRegex(ValueError, "release deployment branch"):
            self.updater.adopt()
        self.assertFalse(self.install.is_symlink())
        self.assertEqual(self.updater.stops, 0)

    def test_retention_keeps_active_and_two_successful_rollback_releases(self):
        self.updater.adopt()
        initial = self.install.resolve()
        all_releases = [initial]
        for _ in range(4):
            self.advance()
            self.updater.update()
            all_releases.append(self.install.resolve())
        history = self.updater.state()["successful"]
        self.assertEqual(history, [str(path) for path in reversed(all_releases[-3:])])
        self.assertFalse(initial.exists())
        self.assertEqual(len(list((self.updater.storage / "releases").iterdir())), 3)
        self.assertTrue((self.updater.storage / "shared/config.ini").exists())
        self.updater.rollback()
        self.assertEqual(self.install.resolve(), all_releases[-2])
        self.assertTrue(all_releases[-1].exists())
        self.assertEqual(len(self.updater.state()["successful"]), 3)

    def test_pending_recovery_defers_pruning_and_discard(self):
        self.updater.adopt()
        previous = self.install.resolve()
        self.advance()
        candidate, revision = self.updater.stage(previous)
        state = self.updater.state()
        state["transaction"] = {"previous": str(previous), "revision": revision}
        self.updater.save_state(state)
        self.updater.prune()
        self.updater.discard(candidate)
        self.assertTrue(previous.exists())
        self.assertTrue(candidate.exists())
        self.assertEqual(self.updater.state(), state)

    def test_prune_refuses_paths_outside_manifest_storage_and_symlinks(self):
        self.updater.adopt()
        outsiders = self.root / "outside"
        outsiders.mkdir()
        (outsiders / "keep").write_text("preserve me")
        # Create enough valid retained releases to make the outsider obsolete.
        for _ in range(2):
            self.advance()
            self.updater.update()
        state = self.updater.state()
        history = state["successful"] + [str(outsiders)]
        state["successful"] = history
        self.updater.save_state(state)
        with self.assertRaisesRegex(ValueError, "Invalid managed release"):
            self.updater.prune()
        self.assertTrue((outsiders / "keep").exists())
        link = self.updater.storage / "releases" / ("release-" + "a" * 32)
        link.symlink_to(outsiders, target_is_directory=True)
        state["successful"] = history[:-1] + [str(link)]
        self.updater.save_state(state)
        with self.assertRaisesRegex(ValueError, "Invalid managed release"):
            self.updater.prune()
        self.assertTrue(link.is_symlink())
        self.assertTrue((outsiders / "keep").exists())

    def test_failed_activation_does_not_prune_successful_history(self):
        self.updater.adopt()
        for _ in range(2):
            self.advance()
            self.updater.update()
        history = self.updater.state()["successful"]
        self.advance()
        self.updater.fail_start = 1
        with self.assertRaises(RuntimeError):
            self.updater.update()
        self.assertEqual(self.updater.state()["successful"], history)
        self.assertTrue(all(Path(path).exists() for path in history))

    def test_interrupted_pruning_resumes_without_touching_protected_releases(self):
        self.updater.adopt()
        initial = self.install.resolve()
        for _ in range(2):
            self.advance()
            self.updater.update()
        state = self.updater.state()
        state["pruning"] = [str(initial)]
        state["successful"].remove(str(initial))
        self.updater.save_state(state)
        shutil.rmtree(initial)
        protected = self.updater.protected_releases()
        self.updater.prune()
        self.assertNotIn("pruning", self.updater.state())
        self.assertTrue(all(path.exists() for path in protected))

    def test_rewritten_remote_is_not_fast_forward(self):
        self.updater.adopt()
        previous = self.install.resolve()
        self.git(self.seed, "checkout", "--orphan", "rewritten")
        self.git(self.seed, "-c", "user.name=Offline Test",
                 "-c", "user.email=offline@example.invalid", "commit", "-m", "rewrite")
        self.git(self.seed, "push", "--force", "origin", "HEAD:release")
        stops = self.updater.stops
        with self.assertRaises(subprocess.CalledProcessError):
            self.updater.update()
        self.assertEqual(self.install.resolve(), previous)
        self.assertEqual(self.updater.stops, stops)

    def test_interrupted_activation_recovers_before_next_update(self):
        self.updater.adopt()
        previous = self.install.resolve()
        self.advance()
        candidate, revision = self.updater.stage(previous)
        self.updater.connect_runtime(candidate)
        self.updater.link(candidate)
        write_json(self.control / "state.json",
                   {"transaction": {"previous": str(previous), "revision": revision}})
        self.updater.running = False
        self.updater.recover()
        self.assertEqual(self.install.resolve(), previous)
        self.assertTrue(self.updater.running)
        self.assertNotIn("transaction", self.updater.state())

    def test_manual_rollback_keeps_newest_presets(self):
        self.updater.adopt()
        previous = self.install.resolve()
        self.advance()
        self.updater.update()
        (self.install / "presets.json").write_text('{"presets": ["latest"]}')
        self.updater.rollback()
        self.assertEqual(self.install.resolve(), previous)
        self.assertEqual(json.loads((self.install / "presets.json").read_text()),
                         {"presets": ["latest"]})

    def test_mount_dependencies_use_configured_paths_and_are_idempotent(self):
        systemd = self.root / "systemd"
        install = self.root / "home with space" / "iris"
        storage = self.root / "data with space" / "iris-update"
        install_mount_dependencies(install, storage, systemd)
        expected = (
            f'[Unit]\nRequiresMountsFor="{install}" "{storage}"\n'
        )
        for service in ("iris.service", "iris-update.service",
                        "iris-update-recover.service"):
            dropin = systemd / f"{service}.d/90-iris-update-mounts.conf"
            self.assertEqual(dropin.read_text(), expected)
        install_mount_dependencies(install, storage, systemd)

    def test_mount_dependency_conflict_is_refused_before_writing_other_dropins(self):
        systemd = self.root / "systemd"
        conflicting = (
            systemd / "iris-update.service.d/90-iris-update-mounts.conf"
        )
        conflicting.parent.mkdir(parents=True)
        conflicting.write_text("[Unit]\nRequiresMountsFor=/unexpected\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            install_mount_dependencies(self.install, self.root / "storage", systemd)
        self.assertFalse((systemd / "iris.service.d").exists())


if __name__ == "__main__":
    unittest.main()
