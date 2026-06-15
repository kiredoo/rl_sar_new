"""Helpers for invoking repo-local Python entrypoints with a predictable interpreter."""
import os
import shutil
import sys
from typing import Iterable, List, Optional


def resolve_python_bin(explicit: Optional[str] = None) -> str:
    """Return the Python interpreter that should be used for child Python processes.

    Resolution order:
    1) explicit argument
    2) WCET_PYTHON_BIN env var
    3) current interpreter (sys.executable)
    4) python3 from PATH
    5) /usr/bin/python3 fallback
    """
    if explicit:
        return explicit

    env_python = os.environ.get("WCET_PYTHON_BIN")
    if env_python:
        return env_python

    if sys.executable:
        return sys.executable

    return shutil.which("python3") or "/usr/bin/python3"


def repo_script_path(script_name: str) -> str:
    """Return the absolute path to a repo-local Python entrypoint."""
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), script_name)


def build_python_cmd(script_name: str,
                     args: Optional[Iterable[object]] = None,
                     *,
                     use_sudo: bool = False,
                     python_bin: Optional[str] = None,
                     sudo_preserve_env: bool = False) -> List[str]:
    """Build an argv list for invoking a repo-local Python script.

    The command is always returned as an argv list so callers can pass it directly
    to subprocess.Popen without shell parsing.
    """
    cmd = [resolve_python_bin(python_bin), repo_script_path(script_name)]
    if args:
        cmd.extend(str(arg) for arg in args)

    if use_sudo:
        sudo_prefix = ["sudo"]
        if sudo_preserve_env:
            sudo_prefix.append("-E")
        cmd = sudo_prefix + cmd

    return cmd
