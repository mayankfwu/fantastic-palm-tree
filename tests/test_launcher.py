"""Exercise the reviewer launcher without downloading packages or opening a browser."""

import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """Load the launcher from a separate checkout with spaces in its path."""
    root = tmp_path / "Reviewer checkout"
    root.mkdir()
    script = root / "run_demo.py"
    shutil.copyfile(Path(__file__).resolve().parents[1] / script.name, script)
    (root / "requirements.txt").touch()
    (root / "app.py").touch()
    monkeypatch.chdir(tmp_path)
    scripts = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    pip = scripts / ("pip.exe" if os.name == "nt" else "pip")
    return root, python, pip, runpy.run_path(str(script))["main"]


@pytest.mark.parametrize("interrupted_setup", [False, True], ids=["fresh", "missing-pip"])
def test_launcher_creates_then_reuses_project_environment(checkout, monkeypatch, interrupted_setup):
    """Run twice from outside the project and check which environment starts the app."""
    root, python, pip, main = checkout
    commands = []
    if interrupted_setup:
        python.parent.mkdir(parents=True)
        python.touch()

    def run(args, *, cwd, **kwargs):
        """Record each subprocess and simulate creation of the environment."""
        assert Path(cwd) == root
        args = list(map(str, args))
        commands.append(args)
        if args[1:3] == ["-m", "venv"]:
            assert args[0] == sys.executable
            assert Path(cwd, args[-1]) == root / "venv"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.touch()
            pip.touch()
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert main() == 0
    assert main() == 0
    assert [args[2] for args in commands] == ["venv", "pip", "streamlit", "pip", "streamlit"]
    for args in commands[1:]:
        assert Path(args[0]) == python
        if args[2] == "pip":
            assert "install" in args and Path(root, args[args.index("-r") + 1]) == root / "requirements.txt"
        else:
            assert Path(root, args[args.index("run") + 1]) == root / "app.py"


def test_launcher_stops_when_requirements_installation_fails(checkout, monkeypatch):
    """An interrupted dependency install should never start a partial dashboard."""
    _, python, pip, main = checkout
    python.parent.mkdir(parents=True)
    python.touch()
    pip.touch()

    def refuse_install(args, *, check=False, **kwargs):
        """Report a nonzero exit status as subprocess would with either check setting."""
        assert list(args)[1:3] == ["-m", "pip"]
        if check:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 1)

    run = Mock(side_effect=refuse_install)
    monkeypatch.setattr(subprocess, "run", run)
    assert main() != 0
    run.assert_called_once()
