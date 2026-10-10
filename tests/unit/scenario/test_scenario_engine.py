"""Unit tests for services/scenario (pure: file/dict in, typed data out)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from services.scenario import (
    DEFAULT_SCENARIO_VERSION,
    Scenario,
    ScenarioFileError,
    ScenarioValidationError,
    load_scenario,
    parse_scenario_dict,
    validate_scenario_dict,
    validation,
)

FIXTURES = Path(__file__).parent / "fixtures"
YAML_FIXTURE = FIXTURES / "mountain_communication_test.yaml"
JSON_FIXTURE = FIXTURES / "mountain_communication_test.json"


@pytest.fixture
def raw() -> dict[str, Any]:
    """The representative example as a plain dict (from the JSON fixture)."""
    return json.loads(JSON_FIXTURE.read_text(encoding="utf-8"))


def _errors_for(data: dict[str, Any]) -> list[str]:
    return validate_scenario_dict(data)


class TestHappyPath:
    def test_example_validates_end_to_end(self) -> None:
        s = load_scenario(YAML_FIXTURE)
        assert isinstance(s, Scenario)
        assert s.name == "Mountain_Communication_Test"
        assert s.seed == 42
        assert [n.id for n in s.nodes] == ["BASE-01", "VEHICLE-01"]
        assert s.nodes[1].type == "mobile_radio"
        assert s.nodes[1].route == "route_01"
        assert s.nodes[0].lat == 45.0 and s.nodes[0].lon == 6.0
        assert s.nodes[0].alt_m == 1200.0
        assert s.environment.terrain is not None
        assert s.environment.terrain.layer_name == "mountain_dem_01"
        assert s.environment.terrain.style is None
        assert len(s.environment.vector_layers) == 2
        assert s.interference[0].frequency == 145.5e6
        assert s.interference[0].bandwidth == 25e3

    def test_accepts_str_path_and_path(self) -> None:
        assert load_scenario(str(YAML_FIXTURE)) == load_scenario(YAML_FIXTURE)

    def test_minimal_scenario(self) -> None:
        data = {"scenario": {"name": "x", "nodes": []}}
        assert validate_scenario_dict(data) == []
        s = parse_scenario_dict(data)
        assert s.seed == 0
        assert s.environment.terrain is None
        assert s.interference == ()

    def test_terrain_srs_defaults(self, raw: dict[str, Any]) -> None:
        del raw["scenario"]["environment"]["terrain"]["srs"]
        assert parse_scenario_dict(raw).environment.terrain.srs == "EPSG:4326"  # type: ignore[union-attr]


class TestYamlJsonParity:
    def test_yaml_and_json_produce_identical_objects(self) -> None:
        assert load_scenario(YAML_FIXTURE) == load_scenario(JSON_FIXTURE)

    def test_yaml_unsigned_exponent_floats_are_numbers(self, tmp_path: Path) -> None:
        # PyYAML (YAML 1.1) would load 145.5e6 / 25e3 as *strings*.
        f = tmp_path / "s.yaml"
        f.write_text(
            "scenario:\n  name: n\n  nodes: []\n  interference:\n"
            "    - {id: J, frequency: 145.5e6, bandwidth: 25e3, power: 1.5E+2}\n",
            encoding="utf-8",
        )
        j = load_scenario(f).interference[0]
        assert (j.frequency, j.bandwidth, j.power) == (145.5e6, 25e3, 150.0)

    def test_yaml_plain_ints_stay_ints(self, tmp_path: Path) -> None:
        f = tmp_path / "s.yml"
        f.write_text("scenario:\n  name: n\n  seed: 7\n  nodes: []\n", encoding="utf-8")
        assert load_scenario(f).seed == 7

    def test_json_with_bom_loads(self, tmp_path: Path) -> None:
        f = tmp_path / "s.json"
        f.write_bytes(b"\xef\xbb\xbf" + b'{"scenario": {"name": "n", "nodes": []}}')
        assert load_scenario(f).name == "n"


class TestRequiredFields:
    def test_missing_root_scenario(self) -> None:
        errs = _errors_for({})
        assert errs == ["(root): missing required field 'scenario'"]

    def test_missing_name(self, raw: dict[str, Any]) -> None:
        del raw["scenario"]["name"]
        assert _errors_for(raw) == ["scenario: missing required field 'name'"]

    def test_missing_nodes(self, raw: dict[str, Any]) -> None:
        del raw["scenario"]["nodes"]
        assert _errors_for(raw) == ["scenario: missing required field 'nodes'"]

    @pytest.mark.parametrize("field", ["id", "type", "position", "radio"])
    def test_missing_node_field(self, raw: dict[str, Any], field: str) -> None:
        del raw["scenario"]["nodes"][0][field]
        assert _errors_for(raw) == [f"scenario.nodes[0]: missing required field '{field}'"]

    def test_missing_terrain_fields(self, raw: dict[str, Any]) -> None:
        del raw["scenario"]["environment"]["terrain"]["source"]
        assert _errors_for(raw) == ["scenario.environment.terrain: missing required field 'source'"]

    def test_all_errors_are_reported_not_just_first(self, raw: dict[str, Any]) -> None:
        del raw["scenario"]["name"]
        del raw["scenario"]["nodes"][0]["radio"]
        raw["scenario"]["nodes"][1]["position"] = [1, 2, 3, 4]
        assert len(_errors_for(raw)) == 3


class TestPosition:
    @pytest.mark.parametrize("pos", [[], [1.0], [1, 2, 3, 4], [1, 2, 3, 4, 5]])
    def test_wrong_length_rejected(self, raw: dict[str, Any], pos: list[float]) -> None:
        raw["scenario"]["nodes"][1]["position"] = pos
        errs = _errors_for(raw)
        assert len(errs) == 1
        assert errs[0].startswith("scenario.nodes[1].position: array has ")

    def test_error_message_format(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["nodes"][1]["position"] = [1, 2, 3, 4]
        assert _errors_for(raw) == ["scenario.nodes[1].position: array has 4 items, maximum 3"]
        raw["scenario"]["nodes"][1]["position"] = [1]
        assert _errors_for(raw) == ["scenario.nodes[1].position: array has 1 item, minimum 2"]

    @pytest.mark.parametrize("pos", [[45.0, 6.0], [45.0, 6.0, 100.0]])
    def test_two_and_three_elements_accepted(self, raw: dict[str, Any], pos: list[float]) -> None:
        raw["scenario"]["nodes"][0]["position"] = pos
        assert _errors_for(raw) == []
        node = parse_scenario_dict(raw).nodes[0]
        assert node.position == tuple(pos)
        assert node.alt_m == (pos[2] if len(pos) == 3 else None)

    def test_non_numeric_element_rejected(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["nodes"][0]["position"] = [45.0, "six"]
        assert _errors_for(raw) == ["scenario.nodes[0].position[1]: expected number, got string"]


class TestMobileRadioPositionRequired:
    """position is unconditionally required (frozen schema), even with a route."""

    def test_mobile_radio_without_position_rejected(self, raw: dict[str, Any]) -> None:
        mobile = raw["scenario"]["nodes"][1]
        assert mobile["type"] == "mobile_radio" and "route" in mobile
        del mobile["position"]
        assert _errors_for(raw) == ["scenario.nodes[1]: missing required field 'position'"]

    def test_fixed_radio_without_position_rejected_identically(self, raw: dict[str, Any]) -> None:
        del raw["scenario"]["nodes"][0]["position"]
        assert _errors_for(raw) == ["scenario.nodes[0]: missing required field 'position'"]

    def test_mobile_radio_without_route_but_with_position_ok(self, raw: dict[str, Any]) -> None:
        del raw["scenario"]["nodes"][1]["route"]
        assert _errors_for(raw) == []
        assert parse_scenario_dict(raw).nodes[1].route is None

    def test_load_scenario_raises_for_mobile_without_position(
        self, raw: dict[str, Any], tmp_path: Path
    ) -> None:
        del raw["scenario"]["nodes"][1]["position"]
        f = tmp_path / "bad.json"
        f.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(ScenarioValidationError, match="nodes\\[1\\].*'position'"):
            load_scenario(f)


class TestNodeType:
    @pytest.mark.parametrize("bad", ["satellite", "FIXED_RADIO", "", 3, None])
    def test_invalid_type_rejected_and_names_allowed_values(
        self, raw: dict[str, Any], bad: object
    ) -> None:
        raw["scenario"]["nodes"][0]["type"] = bad
        errs = _errors_for(raw)
        assert len(errs) == 1
        assert errs[0].startswith("scenario.nodes[0].type: ")
        assert "'fixed_radio'" in errs[0] and "'mobile_radio'" in errs[0]


class TestInterference:
    @pytest.mark.parametrize("field", ["frequency", "bandwidth", "power", "id"])
    def test_each_missing_field_rejected_individually(
        self, raw: dict[str, Any], field: str
    ) -> None:
        del raw["scenario"]["interference"][0][field]
        assert _errors_for(raw) == [f"scenario.interference[0]: missing required field '{field}'"]

    def test_non_numeric_frequency_rejected(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["interference"][0]["frequency"] = "145.5 MHz"
        assert _errors_for(raw) == [
            "scenario.interference[0].frequency: expected number, got string"
        ]

    def test_boolean_is_not_a_number(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["interference"][0]["power"] = True
        assert len(_errors_for(raw)) == 1


class TestVersioning:
    def test_absent_defaults_to_1(self, raw: dict[str, Any]) -> None:
        assert "scenario_version" not in raw["scenario"]
        assert DEFAULT_SCENARIO_VERSION == 1
        assert parse_scenario_dict(raw).scenario_version == 1

    def test_explicit_value_round_trips(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["scenario_version"] = 3
        assert parse_scenario_dict(raw).scenario_version == 3

    @pytest.mark.parametrize("bad", [0, -1, "1", 1.5, True, None])
    def test_invalid_version_rejected(self, raw: dict[str, Any], bad: object) -> None:
        raw["scenario"]["scenario_version"] = bad
        errs = _errors_for(raw)
        assert len(errs) == 1 and errs[0].startswith("scenario.scenario_version: ")


class TestRadioCatalog:
    def test_no_catalog_means_opaque_reference(self, raw: dict[str, Any]) -> None:
        assert "radios" not in raw["scenario"]
        assert _errors_for(raw) == []
        s = parse_scenario_dict(raw)
        assert s.radios is None
        assert s.nodes[0].radio == "radio_vhf_01"
        assert s.radio_for(s.nodes[0]) is None

    def test_resolving_catalog_ok_and_params_carried(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["radios"] = {
            "radio_vhf_01": {"power_watt": 10, "freq_hz": 145.5e6},
            "radio_vhf_02": {},
        }
        assert _errors_for(raw) == []
        s = parse_scenario_dict(raw)
        defn = s.radio_for(s.nodes[0])
        assert defn is not None and defn.params == {
            "power_watt": 10,
            "freq_hz": 145.5e6,
        }

    def test_unknown_radio_names_radio_and_node(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["radios"] = {"radio_vhf_01": {}}
        errs = _errors_for(raw)
        assert len(errs) == 1
        assert errs[0].startswith("scenario.nodes[1].radio: ")
        assert "'VEHICLE-01'" in errs[0]
        assert "'radio_vhf_02'" in errs[0]
        assert "'radio_vhf_01'" in errs[0]  # lists what is defined

    def test_empty_catalog_rejects_every_reference(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["radios"] = {}
        assert len(_errors_for(raw)) == 2

    def test_catalog_with_wrong_shape(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["radios"] = ["radio_vhf_01"]
        assert _errors_for(raw) == ["scenario.radios: expected object, got array"]
        raw["scenario"]["radios"] = {"radio_vhf_01": 5, "radio_vhf_02": {}}
        assert _errors_for(raw) == ["scenario.radios.radio_vhf_01: expected object, got integer"]

    def test_unresolved_reference_raises_on_parse(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["radios"] = {"other": {}}
        with pytest.raises(ScenarioValidationError) as exc:
            parse_scenario_dict(raw)
        assert len(exc.value.errors) == 2

    def test_malformed_node_does_not_crash_reference_check(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["radios"] = {"radio_vhf_01": {}}
        raw["scenario"]["nodes"][1] = "not-a-node"
        errs = _errors_for(raw)
        assert errs == ["scenario.nodes[1]: expected object, got string"]


class TestLoadingErrors:
    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "s.txt"
        f.write_text("{}", encoding="utf-8")
        with pytest.raises(ScenarioFileError, match="unsupported file extension"):
            load_scenario(f)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ScenarioFileError, match="cannot read"):
            load_scenario(tmp_path / "nope.yaml")

    def test_malformed_yaml_and_json(self, tmp_path: Path) -> None:
        y = tmp_path / "bad.yaml"
        y.write_text("scenario: [unclosed", encoding="utf-8")
        with pytest.raises(ScenarioFileError, match="malformed YAML"):
            load_scenario(y)
        j = tmp_path / "bad.json"
        j.write_text("{not json", encoding="utf-8")
        with pytest.raises(ScenarioFileError, match="malformed JSON"):
            load_scenario(j)

    def test_non_object_document(self, tmp_path: Path) -> None:
        f = tmp_path / "list.yaml"
        f.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ScenarioValidationError, match="expected object, got array"):
            load_scenario(f)

    def test_validation_error_lists_all_errors_in_message(self, raw: dict[str, Any]) -> None:
        bad = copy.deepcopy(raw)
        del bad["scenario"]["name"]
        bad["scenario"]["nodes"][0]["type"] = "x"
        with pytest.raises(ScenarioValidationError) as exc:
            parse_scenario_dict(bad)
        msg = str(exc.value)
        assert "2 errors" in msg and "'name'" in msg and "nodes[0].type" in msg


class TestModels:
    def test_models_are_immutable(self) -> None:
        s = load_scenario(YAML_FIXTURE)
        with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
            s.name = "other"  # type: ignore[misc]

    def test_unknown_keys_are_tolerated(self, raw: dict[str, Any]) -> None:
        raw["scenario"]["nodes"][0]["notes"] = "extra"
        raw["extra_top_level"] = 1
        assert _errors_for(raw) == []
        assert not hasattr(parse_scenario_dict(raw).nodes[0], "notes")


class TestHardening:
    """Regressions found by stress testing."""

    def test_invalid_utf8_is_a_file_error(self, tmp_path: Path) -> None:
        f = tmp_path / "u.json"
        f.write_bytes(b'{"scenario":\xff}')
        with pytest.raises(ScenarioFileError, match="not valid UTF-8"):
            load_scenario(f)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_numbers_rejected(self, raw: dict[str, Any], bad: float) -> None:
        raw["scenario"]["interference"][0]["power"] = bad
        errs = _errors_for(raw)
        assert len(errs) == 1
        assert errs[0].startswith("scenario.interference[0].power: number must be finite")

    def test_overflowing_literal_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "s.json"
        f.write_text(
            '{"scenario":{"name":"n","nodes":[{"id":"a","type":"fixed_radio",'
            '"position":[1e999,0],"radio":"r"}]}}',
            encoding="utf-8",
        )
        with pytest.raises(ScenarioValidationError, match="position\\[0\\].*finite"):
            load_scenario(f)

    def test_yaml_nan_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "s.yaml"
        f.write_text(
            "scenario: {name: n, nodes: [{id: a, type: fixed_radio, "
            "position: [.nan, 0], radio: r}]}\n",
            encoding="utf-8",
        )
        with pytest.raises(ScenarioValidationError, match="finite"):
            load_scenario(f)

    def test_duplicate_yaml_key_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "d.yaml"
        f.write_text("scenario:\n  name: a\n  name: b\n  nodes: []\n", encoding="utf-8")
        with pytest.raises(ScenarioFileError, match="duplicate key 'name'"):
            load_scenario(f)

    def test_duplicate_json_key_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "d.json"
        f.write_text('{"scenario": {"name": "a", "name": "b", "nodes": []}}', encoding="utf-8")
        with pytest.raises(ScenarioFileError, match="duplicate key 'name'"):
            load_scenario(f)

    def test_yaml_merge_keys_still_work(self, tmp_path: Path) -> None:
        f = tmp_path / "m.yaml"
        f.write_text(
            "defs: &d {type: fixed_radio, radio: r}\n"
            "scenario:\n  name: n\n  nodes:\n"
            "    - {<<: *d, id: a, position: [0, 0]}\n",
            encoding="utf-8",
        )
        assert load_scenario(f).nodes[0].radio == "r"

    def test_deeply_nested_input_is_rejected_before_jsonschema(
        self, raw: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # jsonschema/repr() can raise RecursionError on deep input (seen on
        # Python 3.13), so the depth guard must stop it *before* jsonschema.
        def _must_not_run() -> None:
            raise AssertionError("jsonschema must not see pathologically deep input")

        monkeypatch.setattr(validation, "_validator", _must_not_run)
        deep: Any = []
        for _ in range(5000):
            deep = [deep]
        raw["scenario"]["nodes"][0]["position"] = deep
        errs = _errors_for(raw)
        assert len(errs) == 1
        assert "nesting deeper than 64 levels" in errs[0]
        assert errs[0].startswith("scenario.nodes[0].position")

    def test_reasonable_nesting_is_accepted(self, raw: dict[str, Any]) -> None:
        nested: Any = {}
        for _ in range(20):
            nested = {"k": nested}
        raw["scenario"]["radios"] = {"radio_vhf_01": nested, "radio_vhf_02": {}}
        assert _errors_for(raw) == []

    @pytest.mark.parametrize(
        ("suffix", "text"),
        [
            pytest.param(".json", '{"scenario":' + "[" * 100000 + "]" * 100000 + "}", id="json"),
            pytest.param(".yaml", "scenario: " + "[" * 5000 + "]" * 5000, id="yaml"),
        ],
    )
    def test_deeply_nested_file_is_a_clean_error(
        self, tmp_path: Path, suffix: str, text: str
    ) -> None:
        f = tmp_path / f"deep{suffix}"
        f.write_text(text, encoding="utf-8")
        with pytest.raises((ScenarioFileError, ScenarioValidationError)):
            load_scenario(f)
