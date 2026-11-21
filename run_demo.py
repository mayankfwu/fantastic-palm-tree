"""Start the ORBITGUARD reviewer demo using only Python's standard library for setup."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Prepare the local environment and return the setup or server exit status."""
    if sys.version_info[:2] != (3, 12):
        print("ORBITGUARD requires Python 3.12. See the reviewer quick start in README.md.", file=sys.stderr)
        return 1

    environment = ROOT / "venv"
    if os.name == "nt":
        python = environment / "Scripts" / "python.exe"
        pip = environment / "Scripts" / "pip.exe"
    else:
        python = environment / "bin" / "python"
        pip = environment / "bin" / "pip"

    try:
        if not (python.is_file() and pip.is_file()):
            print("Preparing the project's Python environment…", flush=True)
            subprocess.run([sys.executable, "-m", "venv", environment], cwd=ROOT, check=True)

        print("Checking demo dependencies…", flush=True)
        subprocess.run(
            [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--quiet",
             "-r", "requirements.txt"],
            cwd=ROOT, check=True,
        )
        print("Starting ORBITGUARD. Use the local URL below. Press Ctrl+C to stop.", flush=True)
        return subprocess.run(
            [python, "-m", "streamlit", "run", "app.py", "--server.address=127.0.0.1",
             "--server.showEmailPrompt=false"],
            cwd=ROOT,
        ).returncode
    except subprocess.CalledProcessError as error:
        print("Setup stopped. Resolve the error above and run the same command again.", file=sys.stderr)
        return error.returncode
    except OSError as error:
        print(f"Could not start ORBITGUARD: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
