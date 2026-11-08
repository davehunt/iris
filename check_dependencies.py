"""Validate only Iris's installed dependency graph, not unrelated apt packages."""

from importlib import metadata
from pathlib import Path
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def check(requirements, lookup=metadata.distribution):
    errors = []
    checked = set()
    pending = [(Requirement(line), "requirements.txt") for line in requirements]
    while pending:
        requirement, parent = pending.pop()
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        try:
            distribution = lookup(requirement.name)
        except metadata.PackageNotFoundError:
            errors.append(f"{parent} requires {requirement}, but it is not installed")
            continue
        if not requirement.specifier.contains(distribution.version, prereleases=True):
            errors.append(
                f"{parent} requires {requirement}, but {distribution.version} is installed"
            )
        extras = requirement.extras | {""}
        for extra in extras:
            key = (canonicalize_name(requirement.name), extra)
            if key in checked:
                continue
            checked.add(key)
            for dependency in distribution.requires or []:
                child = Requirement(dependency)
                if child.marker and not child.marker.evaluate({"extra": extra}):
                    continue
                # The parent's extras have already selected this dependency.
                child.marker = None
                pending.append((child, f"{requirement.name}=={distribution.version}"))
    return errors, checked


def main():
    path = Path(__file__).resolve().with_name("requirements.txt")
    requirements = [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    errors, checked = check(requirements)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"Iris dependency graph OK ({len({name for name, _ in checked})} distributions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
