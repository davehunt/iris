from importlib import metadata
from types import SimpleNamespace
import unittest

from check_dependencies import check


class DependencyTests(unittest.TestCase):
    def lookup(self, packages):
        def find(name):
            if name not in packages:
                raise metadata.PackageNotFoundError(name)
            version, requires = packages[name]
            return SimpleNamespace(version=version, requires=requires)

        return find

    def test_unrelated_system_failure_is_not_checked(self):
        errors, checked = check(
            ["iris-test==1"],
            self.lookup(
                {
                    "iris-test": ("1", ["child>=2"]),
                    "child": ("2", []),
                    "apt-listchanges": ("1", ["missing-system-package"]),
                }
            ),
        )
        self.assertEqual(errors, [])
        self.assertEqual({name for name, _ in checked}, {"iris-test", "child"})

    def test_missing_and_conflicting_dependencies_fail(self):
        errors, _ = check(
            ["iris-test==1"],
            self.lookup(
                {"iris-test": ("1", ["child>=2", "missing"]), "child": ("1", [])}
            ),
        )
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("child>=2" in error for error in errors))
        self.assertTrue(any("missing" in error for error in errors))

    def test_markers_extras_and_cycles(self):
        errors, checked = check(
            ["iris-test[feature]==1"],
            self.lookup(
                {
                    "iris-test": (
                        "1",
                        [
                            "child; extra == 'feature'",
                            "unselected; extra == 'other'",
                            "not-on-this-python; python_version < '3.0'",
                        ],
                    ),
                    "child": ("1", ["iris-test"]),
                }
            ),
        )
        self.assertEqual(errors, [])
        self.assertEqual({name for name, _ in checked}, {"iris-test", "child"})


if __name__ == "__main__":
    unittest.main()
