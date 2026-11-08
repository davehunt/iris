#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
exec ./venv/bin/python -u src/iris.py
