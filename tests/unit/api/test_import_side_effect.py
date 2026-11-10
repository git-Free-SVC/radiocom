"""Import-time purity (task prompt §9): importing services.api must not bind
a socket, open any file for writing, read environment variables outside a
tiny allowlist, or leave any artefact behind — asserted from a subprocess
with an audit hook and an env trap, in a fresh working directory."""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import REPOSITORY_ROOT  # type: ignore[import-not-found]

PROBE_PROGRAM = r'''
import os
import sys

violations = []

ALLOWED_ENV = {"PATH", "SYSTEMROOT", "TEMP", "TMP", "PYTHONPATH"}
# PYTHONUSERBASE/APPDATA are read by stdlib sysconfig, PYTHONTZPATH by stdlib
# zoneinfo and PYDANTIC_DISABLE_PLUGINS by pydantic's plugin loader, all at
# import time (fastapi -> pydantic -> zoneinfo/sysconfig chain). They are part
# of third-party import machinery, not of services.api. Everything else stays
# forbidden.
ALLOWED_ENV.update({"PYTHONUSERBASE", "APPDATA", "PYTHONTZPATH", "PYDANTIC_DISABLE_PLUGINS"})


def audit_hook(event, args):
    if event.startswith("socket."):
        violations.append("socket event: %s" % event)
    elif event == "open":
        path = args[0]
        mode = args[1] if len(args) > 1 else "r"
        if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "+")):
            violations.append("write open: %s" % path)
        elif isinstance(mode, int) and mode & (
            os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT
        ):
            violations.append("write open: %s" % path)


sys.addaudithook(audit_hook)


class EnvTrap(dict):
    """os.environ: raise on any value read outside the allowlist; forbid all
    mutation. Membership checks (x in os.environ) are tolerated."""

    def __getitem__(self, key):
        if key not in ALLOWED_ENV:
            violations.append("env read: %s" % key)
            raise KeyError(key)
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            if key in ALLOWED_ENV:
                return default
            raise

    def __setitem__(self, key, value):
        violations.append("env write: %s" % key)
        raise AssertionError("os.environ must not be mutated during import")


os.environ = EnvTrap(dict(os.environ))

import services.api  # noqa: E402 - the thing under test (hooks first)
import libraries  # noqa: E402

assert services.api.create_app is not None
print("IMPORT-OK")
if violations:
    print("VIOLATIONS:")
    for entry in violations:
        print(" ", entry)
    sys.exit(2)
'''


def test_import_services_api_has_no_side_effects(tmp_path) -> None:
    script = tmp_path / "import_probe.py"
    script.write_text(PROBE_PROGRAM, encoding="utf-8")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "PYTHONPATH": str(REPOSITORY_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    process = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
        env=env,
        timeout=180,
        check=False,
    )
    assert process.returncode == 0, f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
    assert "IMPORT-OK" in process.stdout
    assert "VIOLATIONS" not in process.stdout, process.stdout

    # Nothing was created in the fresh working directory (no __pycache__, no logs).
    produced = sorted(entry.name for entry in tmp_path.iterdir())
    assert produced == ["import_probe.py"], produced
