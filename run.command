#!/usr/bin/env bash
# run.command - double-click launcher for macOS (Finder runs this in Terminal).
cd "$(dirname "$0")" || exit 1

# First run only: create the virtual environment if it does not exist yet.
if [ ! -x ".venv/bin/python" ]; then
    echo "First run: setting things up, this takes a few minutes..."
    if ! python3 -m venv .venv; then
        echo ""
        echo "Could not set up the app. Please install Python 3.11 or newer"
        echo "from https://www.python.org/downloads/ and run this file again."
        read -p "Press Return to close this window..." _
        exit 1
    fi
fi

# Every launch: make sure packages are installed, so a failed first install
# heals itself on the next double-click.
if ! .venv/bin/python -m pip install -q -r requirements.txt; then
    echo ""
    echo "Could not install the required packages. Check your internet"
    echo "connection and run this file again. Also make sure FFmpeg is"
    echo "installed: run 'brew install ffmpeg' in Terminal, then try again."
    read -p "Press Return to close this window..." _
    exit 1
fi

.venv/bin/python -m streamlit run app.py
