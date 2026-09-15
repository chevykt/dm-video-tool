#!/usr/bin/env bash
# run.command - double-click launcher for macOS (Finder runs this in Terminal).
cd "$(dirname "$0")" || exit 1

# The app is tested on Python 3.12 to 3.14 (see constraints.txt). Every
# Python this script uses has to pass this check first.
supported() {
    "$1" -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)' \
        >/dev/null 2>&1
}

# If a virtual environment already exists, make sure it still runs and was
# built with a supported Python before trusting it: the base Python may have
# been updated or removed since it was created, or the folder moved.
if [ -e ".venv" ] && ! supported .venv/bin/python; then
    echo "The app's Python setup is broken or out of date. Rebuilding it..."
    rm -rf .venv
fi

# First run only: create the virtual environment with the newest supported
# Python. Apple's own /usr/bin/python3 is skipped: it is 3.9, and without
# the Command Line Tools running it pops up an offer to install them.
if [ ! -x ".venv/bin/python" ]; then
    PY=""
    for candidate in python3.14 python3.13 python3.12 python3; do
        found="$(command -v "$candidate")" || continue
        [ "$found" = "/usr/bin/python3" ] && continue
        if supported "$found"; then
            PY="$found"
            break
        fi
    done
    if [ -z "$PY" ]; then
        echo ""
        echo "Could not find a Python this app supports."
        echo "Install Python 3.14 (or 3.12 to 3.14) from https://www.python.org/downloads/"
        echo "and run this file again."
        read -r -p "Press Return to close this window..." _
        exit 1
    fi
    echo "First run: setting things up, this takes a few minutes..."
    if ! "$PY" -m venv .venv; then
        echo ""
        echo "Could not set up the app. Install Python 3.14 (or 3.12 to 3.14)"
        echo "from https://www.python.org/downloads/ and run this file again."
        read -r -p "Press Return to close this window..." _
        exit 1
    fi
fi

# Every launch: make sure packages are installed, so a failed first install
# heals itself on the next double-click. The constraints file pins every
# package to the versions the app was tested with.
if ! .venv/bin/python -m pip install -q --disable-pip-version-check \
        -r requirements.txt -c constraints.txt; then
    echo ""
    echo "Could not install the required packages. Check your internet"
    echo "connection and run this file again."
    read -r -p "Press Return to close this window..." _
    exit 1
fi

.venv/bin/python -m streamlit run app.py
status=$?
if [ "$status" -ne 0 ]; then
    read -r -p "Press Return to close this window..." _
fi
exit "$status"
