"""CI gate for the frozen plugin SDK. Exit code 0 = OK, 1 = violation.

    python -m tools.check_sdk_freeze --base origin/main
    python -m tools.check_sdk_freeze --no-git          # skip the git-history checks

Checks
  1. Current code surface == snapshot of SDK_VERSION, and SDK_VERSION is the newest snapshot.
  2. Semver rule holds across the whole snapshot history.
  3. Every snapshot version has an accepted ADR (docs/adr: 'Status: Accepted' + 'SDK-Version: X.Y.Z').
  4. Git: snapshots that exist on --base are byte-identical here (released = immutable, not deleted).

CI note: step 4 needs the base ref to exist locally -> use full history (fetch-depth: 0 / GIT_DEPTH: 0).
Add this script as a REQUIRED status check so it cannot be skipped by editing tests.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from tools.sdk_freeze import (
    ROOT,
    SNAP_DIR,
    FreezeError,
    build_snapshot,
    check_history,
    classify,
    current_version,
    find_accepted_adr,
    load_snapshots,
    parse_version,
    required_bump,
)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def check_git_immutability(base: str) -> list[str]:
    if _git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode != 0:
        return [
            f"git ref {base!r} not found. Fetch full history (fetch-depth: 0) or pass --base <ref>."
        ]
    rel = SNAP_DIR.relative_to(ROOT).as_posix()
    ls = _git("ls-tree", "-r", "--name-only", base, "--", rel)
    errors = []
    for name in filter(None, ls.stdout.decode().splitlines()):
        old = _git("show", f"{base}:{name}").stdout
        path = ROOT / name
        if not path.exists():
            errors.append(f"{name}: released snapshot was DELETED (exists on {base})")
        elif path.read_bytes() != old:
            errors.append(
                f"{name}: released snapshot was MODIFIED (differs from {base}). "
                f"Snapshots are immutable; bump SDK_VERSION and add a new one."
            )
    return errors


def run(base: str | None) -> list[str]:
    errors: list[str] = []
    if base:  # first: must still report deleted snapshots even if none are left
        errors += check_git_immutability(base)
    try:
        snaps = load_snapshots()
    except FreezeError as e:
        return errors + [str(e)]
    if not snaps:
        return errors + [f"no snapshots in {SNAP_DIR}"]
    version = current_version()
    try:
        parse_version(version)
    except FreezeError as e:
        return errors + [str(e)]

    latest = list(snaps)[-1]
    if version not in snaps:
        level, reasons = classify(snaps[latest], build_snapshot())
        errors.append(
            f"SDK_VERSION {version} has no snapshot (latest is {latest}; surface change: {level}, "
            f"needs {required_bump(level)}). Bump/record via `python -m tools.sdk_freeze write`."
        )
    else:
        if version != latest:
            errors.append(f"SDK_VERSION {version} is older than newest snapshot {latest}")
        level, reasons = classify(snaps[version], build_snapshot())
        if level != "none":
            errors.append(
                f"Public surface differs from frozen snapshot {version} ({level}):\n    "
                + "\n    ".join(reasons[:15])
            )

    errors += check_history(snaps)
    for v in snaps:
        if not find_accepted_adr(v):
            errors.append(
                f"SDK {v}: no accepted ADR in docs/adr (needs 'Status: Accepted' and 'SDK-Version: {v}')"
            )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base", default="origin/main", help="git ref holding the released snapshots")
    ap.add_argument("--no-git", action="store_true", help="skip git immutability check")
    a = ap.parse_args()
    errors = run(None if a.no_git else a.base)
    if errors:
        print("SDK FREEZE CHECK FAILED", file=sys.stderr)
        for e in errors:
            print(f"  x {e}", file=sys.stderr)
        return 1
    print(f"SDK freeze check OK (SDK_VERSION {current_version()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
