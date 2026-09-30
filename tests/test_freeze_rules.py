"""Unit tests for the freeze tooling itself (rules, not the SDK)."""

from __future__ import annotations

import copy

import pytest

from tools import sdk_freeze as F


def _surf(**cls_over):
    proto = {"bases": ["Protocol"], "annotations": {}, "methods": {"go": "method (self) -> None"}}
    proto.update(cls_over)
    return {
        "modules": {
            "m": {
                "classes": {"P": proto},
                "functions": {"f": "(x: int) -> int"},
                "constants": {"K": "1"},
            }
        }
    }


def test_identical_is_none():
    assert F.classify(_surf(), _surf())[0] == "none"


def test_removed_or_changed_is_major():
    new = _surf()
    del new["modules"]["m"]["functions"]["f"]
    assert F.classify(_surf(), new)[0] == "major"
    new = _surf()
    new["modules"]["m"]["functions"]["f"] = "(x: str) -> int"
    assert F.classify(_surf(), new)[0] == "major"
    new = _surf()
    new["modules"]["m"]["constants"]["K"] = "2"
    assert F.classify(_surf(), new)[0] == "major"


def test_new_function_is_minor():
    new = _surf()
    new["modules"]["m"]["functions"]["g"] = "() -> None"
    assert F.classify(_surf(), new)[0] == "minor"


def test_new_protocol_method_is_major():
    new = _surf()
    new["modules"]["m"]["classes"]["P"]["methods"]["extra"] = "method (self) -> None"
    level, reasons = F.classify(_surf(), new)
    assert level == "major" and "breaks implementers" in reasons[0]


def test_new_method_on_plain_class_is_minor():
    old = _surf()
    old["modules"]["m"]["classes"]["C"] = {"bases": ["object"], "methods": {"a": "method (self)"}}
    new = copy.deepcopy(old)
    new["modules"]["m"]["classes"]["C"]["methods"]["b"] = "method (self)"
    assert F.classify(old, new)[0] == "minor"


@pytest.mark.parametrize(
    "old,new,level,ok",
    [
        ("1.0.0", "1.0.1", "none", True),
        ("1.0.0", "1.0.0", "none", False),
        ("1.2.0", "1.1.0", "none", False),
        ("1.0.0", "1.1.0", "minor", True),
        ("1.0.0", "1.0.1", "minor", False),
        ("1.4.0", "2.0.0", "minor", True),
        ("1.0.0", "2.0.0", "major", True),
        ("1.0.0", "1.9.0", "major", False),
    ],
)
def test_bump_ok(old, new, level, ok):
    assert F.bump_ok(old, new, level) is ok


def test_adr_rule(tmp_path):
    (tmp_path / "a.md").write_text("Status: Proposed\nSDK-Version: 1.1.0\n")
    assert F.find_accepted_adr("1.1.0", tmp_path) is None
    (tmp_path / "a.md").write_text("Status: Accepted\nSDK-Version: 1.1.0\n")
    assert F.find_accepted_adr("1.1.0", tmp_path)
    assert F.find_accepted_adr("1.2.0", tmp_path) is None


def test_write_enforces_all_rules(tmp_path):
    snaps, adrs = tmp_path / "s", tmp_path / "adr"
    adrs.mkdir()
    kw = dict(snap_dir=snaps, adr_dir=adrs)
    base = _surf()["modules"]
    F.write_snapshot("1.0.0", surface=base, require_adr=False, **kw)

    with pytest.raises(F.FreezeError, match="immutable"):
        F.write_snapshot("1.0.0", surface=base, require_adr=False, **kw)  # never overwrite

    added = copy.deepcopy(base)
    added["m"]["functions"]["g"] = "() -> None"
    with pytest.raises(F.FreezeError, match="accepted ADR"):
        F.write_snapshot("1.1.0", surface=added, **kw)  # ADR rule
    (adrs / "x.md").write_text("Status: Accepted\nSDK-Version: 1.0.1\n")
    with pytest.raises(F.FreezeError, match="'minor'"):
        F.write_snapshot("1.0.1", surface=added, **kw)  # bump too small
    (adrs / "x.md").write_text("Status: Accepted\nSDK-Version: 1.1.0\n")
    assert F.write_snapshot("1.1.0", surface=added, **kw).exists()  # OK

    broken = copy.deepcopy(added)
    del broken["m"]["functions"]["f"]
    (adrs / "y.md").write_text("Status: Accepted\nSDK-Version: 1.2.0\n")
    with pytest.raises(F.FreezeError, match="'major'"):
        F.write_snapshot("1.2.0", surface=broken, **kw)  # removal needs MAJOR


def test_history_check_flags_hand_edited_snapshots(tmp_path):
    a = {"sdk_version": "1.0.0", **_surf()}
    b = {"sdk_version": "1.0.1", **_surf()}
    del b["modules"]["m"]["functions"]["f"]
    assert F.check_history({"1.0.0": a, "1.0.1": b})
