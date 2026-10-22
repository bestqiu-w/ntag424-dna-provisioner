#!/usr/bin/env bash
# Quick launcher for NTAG 424 DNA Provisioning Tool
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

PYTHONPATH="$DIR" .venv/bin/python app.py
