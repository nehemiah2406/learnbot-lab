"""start_learnbot.bat: starts LearnBot from its own folder and opens the page once it listens."""

import subprocess
import sys
from pathlib import Path

BAT = Path("start_learnbot.bat").read_text(encoding="utf-8")


def test_bat_runs_from_its_own_folder_and_opens_the_page():
    assert 'cd /d "%~dp0"' in BAT
    assert r".venv\Scripts\python scripts\run_app.py --open" in BAT


def test_bat_holds_no_key_and_no_push():
    assert "API_KEY" not in BAT and ".env" not in BAT and "git" not in BAT.lower()


def test_run_app_knows_the_open_option():
    out = subprocess.run([sys.executable, "scripts/run_app.py", "--help"], capture_output=True, text=True, timeout=120).stdout
    assert "--open" in out
