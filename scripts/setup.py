"""
First-time setup. Run: python scripts/setup.py
"""
import os
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent


def check_python():
    import sys
    assert sys.version_info >= (3, 10), "Python 3.10+ required"
    print(f"Python {sys.version} — OK")


def install_dependencies():
    print("Installing dependencies...")
    subprocess.check_call(["pip", "install", "-r", str(ROOT / "requirements.txt")])
    print("Dependencies installed.")


def check_talib():
    try:
        import talib
        print("TA-Lib — OK")
    except ImportError:
        print("WARNING: TA-Lib not installed. Install the C library first:")
        print("  macOS:  brew install ta-lib && pip install TA-Lib")
        print("  Ubuntu: sudo apt-get install libta-lib-dev && pip install TA-Lib")
        print("Falling back to pandas indicators (less accurate)")


def create_env():
    env_file = ROOT / ".env"
    example_file = ROOT / ".env.example"
    if env_file.exists():
        print(".env already exists — skipping")
        return
    shutil.copy(example_file, env_file)
    print(".env created from .env.example — fill in your API keys")


def create_log_dirs():
    (ROOT / "logs" / "daily").mkdir(parents=True, exist_ok=True)
    pnl = ROOT / "logs" / "pnl_tracker.csv"
    if not pnl.exists():
        pnl.touch()
    print("Log directories ready")


if __name__ == "__main__":
    check_python()
    create_env()
    create_log_dirs()
    install_dependencies()
    check_talib()
    print("\nSetup complete. Edit .env with your API keys, then run: python main.py")
