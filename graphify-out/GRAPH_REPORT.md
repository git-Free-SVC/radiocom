# Graph Report - radiocom (2026-11-13)

## Corpus Check

- cluster-only mode — file stats not available

## Summary

- 1666 nodes · 4134 edges · 75 communities (47 shown, 28 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 409 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness

- Built from commit: `438c5755`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)

- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 68

## God Nodes (most connected - your core abstractions)

1. `GeoPosition` - 97 edges
2. `create_app()` - 56 edges
3. `CoreSimulationEngine` - 54 edges
4. `Radio` - 50 edges
5. `PhysicsInputError` - 47 edges
6. `StubScenario` - 38 edges
7. `line_of_sight()` - 31 edges
8. `_errors_for()` - 31 edges
9. `ApiError` - 29 edges
10. `FlatGeodataProvider` - 29 edges

## Surprising Connections (you probably didn't know these)

- `test_engine_is_abc_impl()` --uses--> `SimulationEngine`  [INFERRED]
  tests/contract/test_simulation_contract.py → libraries/plugin_sdk/simulation.py
- `test_scheduler_is_abc_impl()` --uses--> `SimulationScheduler`  [INFERRED]
  tests/contract/test_simulation_contract.py → libraries/plugin_sdk/simulation.py
- `test_result_fields_exact()` --uses--> `PropagationResult`  [INFERRED]
  tests/unit/propagation/test_propagation_free_space.py → libraries/domain/rf_results.py
- `test_conforms_to_protocol()` --uses--> `PropagationModel`  [INFERRED]
  tests/contract/test_propagation_model_contract.py → libraries/plugin_sdk/propagation.py
- `test_conforms_to_protocol_and_name()` --uses--> `PropagationModel`  [INFERRED]
  tests/unit/propagation/test_propagation_free_space.py → libraries/plugin_sdk/propagation.py

## Import Cycles

- None detected.

## Communities (75 total, 28 thin omitted)

### Community 0 - "Community 0"

Cohesion: 0.06
Nodes (41): Frequency, Antenna, Receiver, Transmitter, PropagationResult, PropagationModel, ValidityDomain, build_radio
() (+33 more)

### Community 1 - "Community 1"

Cohesion: 0.07
Nodes (37): LinkBudgetInput, LinkQuality, LinkState, compute_link_budget (), dbm_to_watts (), eb_n0_db (),
link_margin_db (), LinkBudgetResult (+29 more)

### Community 2 - "Community 2"

Cohesion: 0.07
Nodes (28): build (), _describe_class (), test_public_surface_matches_frozen_snapshot (),
test_import_services_api_has_no_side_effects (), check_git_immutability (), _git (), main (), run () (+20 more)

### Community 3 - "Community 3"

Cohesion: 0.04
Nodes (3): test_get_elevation_is_deterministic_and_schema_valid (), test_get_elevation_profile_exact_sample_count (),
test_patch_radio_updates_position_and_publishes_map_delta ()

### Community 4 - "Community 4"

Cohesion: 0.08
Nodes (29): big_scenario (), fuzz (), hostile_inputs (), main (), _paths (), scale_tests (), timed (), _walk () (+21
more)

### Community 5 - "Community 5"

Cohesion: 0.08
Nodes (32): load_frozen_schema (), test_post_scenarios_scenario_validates_against_frozen_schema (),
app_declared_statuses (), app_operations (), app_ws_paths (), compare_routes (), compare_statuses (), load_yaml_contract
() (+24 more)

### Community 6 - "Community 6"

Cohesion: 0.12
Nodes (30): Radio, _finite (), free_space_path_loss_db (), make_radio (), pair (), test_bad_gain_and_cable (),
test_bad_position (), test_bad_power () (+22 more)

### Community 7 - "Community 7"

Cohesion: 0.08
Nodes (13): BBox, Feature, GeodataProvider, LayerRef, PostGISTable, MockGeodataProvider, test_conforms_to_protocol (),
test_elevation_profile_endpoints_match_point_queries () (+5 more)

### Community 8 - "Community 8"

Cohesion: 0.09
Nodes (10): GeoJSONFile, ClockPort, CorePort, GeodataPort, ScenarioPort, SimulationRegistryPort, spectrum_snapshot (), _
registry () (+2 more)

### Community 9 - "Community 9"

Cohesion: 0.09
Nodes (9): GeoPosition, ecef_to_geo (), geo_to_ecef (), TestGeoPosition, _assert_same (), TestForwardTransform,
TestNearPole, TestInverseTransformGuards (+1 more)

### Community 10 - "Community 10"

Cohesion: 0.11
Nodes (8): parse_scenario_dict (), _errors_for (), TestInterference, TestMobileRadioPositionRequired, TestPosition,
TestRadioCatalog, TestRequiredFields, TestVersioning

### Community 11 - "Community 11"

Cohesion: 0.05
Nodes (41): properties, type, items, type, properties, required, type, type (+33 more)

### Community 12 - "Community 12"

Cohesion: 0.11
Nodes (9): ENUPosition, ENUFrame, _frame_for (), ecef_to_geodetic_rad (), geodetic_rad_to_ecef (), _to_geo_position (),
TestENUPosition, _random_positions () (+1 more)

### Community 13 - "Community 13"

Cohesion: 0.08
Nodes (5): SimulationClock, WallClock, derive_entity_seed (), InMemorySimulationState, TestCheckpointRestore

### Community 14 - "Community 14"

Cohesion: 0.15
Nodes (26): _HasGeoPosition, haversine_distance_m (), _lat_lon (), slant_range_m (), P (), _rand_point (), raw (),
test_antimeridian_crossing () (+18 more)

### Community 15 - "Community 15"

Cohesion: 0.13
Nodes (25): create_app (), add_radio_route (), create_scenario_route (), create_simulation_route (),
elevation_profile_route (), elevation_route (), get_link_route (), get_scenario_route () (+17 more)

### Community 16 - "Community 16"

Cohesion: 0.13
Nodes (30): telemetry_topic (), app (), assert_envelope (), assert_no_leaked_tasks (),
test_disconnect_unsubscribes_and_records_stats (), main (), test_disconnect_with_queued_messages_cleans_up (), main ()
(+22 more)

### Community 17 - "Community 17"

Cohesion: 0.14
Nodes (5): line_of_sight (), FlatGeodataProvider, TestLineOfSight, WallGeodataProvider, TestLineOfSightSafety

### Community 18 - "Community 18"

Cohesion: 0.11
Nodes (7): enu_to_geo (), geo_to_enu (), LOSResult, _require_finite (), _nearby_origin (), TestENUSanityCases,
TestRoundTrip

### Community 19 - "Community 19"

Cohesion: 0.10
Nodes (8): Environment, InterferenceSource, Node, RadioDefinition, Scenario, _ScenarioModel, TerrainConfig,
VectorLayerConfig

### Community 20 - "Community 20"

Cohesion: 0.08
Nodes (4): WaveformCodec, BpskCodec, test_conforms_to_protocol (), test_noiseless_roundtrip ()

### Community 21 - "Community 21"

Cohesion: 0.12
Nodes (5): InMemoryScenarioStore, InMemorySimulationRegistry, link_to_payload (), radio_to_payload (),
test_scenario_port_behaviours ()

### Community 23 - "Community 23"

Cohesion: 0.15
Nodes (14): asgi_request (), assert_error (), assert_error_detail_list (), create_radio (), create_scenario (),
create_simulation (), deps (), get () (+6 more)

### Community 24 - "Community 24"

Cohesion: 0.14
Nodes (14): free_space_path_loss_db (), test_6db_per_distance_doubling_and_20db_per_decade (), test_bad_distance_raises
(), test_bad_frequency_raises (), test_consistent_with_exact_friis (), test_extreme_finite_distances_stay_finite (),
test_extreme_finite_frequencies_stay_finite (), test_golden_values () (+6 more)

### Community 25 - "Community 25"

Cohesion: 0.11
Nodes (8): ScenarioError, ScenarioFileError, ScenarioValidationError, _construct_unique_mapping (), _
DuplicateKeyError, _json_unique_object (), _read_data (), _ScenarioYamlLoader

### Community 26 - "Community 26"

Cohesion: 0.15
Nodes (5): _MockSimulationClock, MockSimulationEngine, MockSimulationState,
test_engine_call_log_records_exactly_one_entry_per_attempt (), test_engine_lifecycle_matches_frozen_state_machine ()

### Community 27 - "Community 27"

Cohesion: 0.08
Nodes (24): terrain, vector_layers, bandwidth, frequency, id, power, id, position (+16 more)

### Community 28 - "Community 28"

Cohesion: 0.10
Nodes (23): BASE_REF, jobs, lint-and-test, sdk-freeze, runs-on, steps, name, on (+15 more)

### Community 29 - "Community 29"

Cohesion: 0.14
Nodes (6): WsConnection, WsConnectionStats, test_backpressure_drops_oldest_and_counts (), main (),
test_publisher_never_blocks_when_client_is_slow (), main ()

### Community 30 - "Community 30"

Cohesion: 0.18
Nodes (11): _depth_errors (), _describe (), _extension_errors (), format_path (), _json_type_name (), _non_finite_errors
(), _quoted (), _schema_errors () (+3 more)

### Community 31 - "Community 31"

Cohesion: 0.19
Nodes (4): load_scenario (), TestHardening, TestLoadingErrors, TestYamlJsonParity

### Community 32 - "Community 32"

Cohesion: 0.16
Nodes (7): SimulationEvent, HeapScheduler, HeapScheduler, test_scheduler_orders_by_time_then_seq (),
TestSchedulerConcurrency, pusher (), TestHeapScheduler

### Community 33 - "Community 33"

Cohesion: 0.14
Nodes (17): RecordingEntity, _run_and_checkpoint (), _running (), Scenario, test_checkpoint_roundtrip (),
test_engine_is_abc_impl (), test_entity_ticks_are_ordered_and_bounded (), test_illegal_transitions_raise () (+9 more)

### Community 34 - "Community 34"

Cohesion: 0.16
Nodes (7): PhysicsInputError, link_quality (), in_range (), positive (), test_bad_inputs (), test_boundaries (),
test_monotonic_and_exhaustive ()

### Community 35 - "Community 35"

Cohesion: 0.10
Nodes (4): EventBus, test_conforms_to_protocol (), test_failing_handler_does_not_break_publisher_or_others (),
test_unsubscribe_during_publish_is_safe ()

### Community 36 - "Community 36"

Cohesion: 0.10
Nodes (9): telemetry_websocket (), build_telemetry_snapshot (), make_message (), _sequence (),
test_created_at_comes_only_from_the_injected_fake_clock (), test_identical_sequence_on_two_fresh_apps_is_byte_identical
(), test_parallel_control_requests_produce_exactly_n_engine_entries (),
test_parallel_radio_creations_yield_unique_counter_ids () (+1 more)

### Community 37 - "Community 37"

Cohesion: 0.18
Nodes (7): enforce_body_limit (), api_error_handler (), error_response (), install_exception_handlers (),
internal_error_handler (), request_validation_handler (), value_error_handler ()

### Community 38 - "Community 38"

Cohesion: 0.11
Nodes (17): type, properties, margin_db, quality, rx_id, snr_db, time_s, tx_id (+9 more)

### Community 39 - "Community 39"

Cohesion: 0.15
Nodes (6): list_layers_route (), ResponseContractError, datetime_to_iso (), iter_non_finite (), position_payload (),
to_payload ()

### Community 40 - "Community 40"

Cohesion: 0.17
Nodes (3): SimulationEntity, SimpleClock, SimpleState

### Community 42 - "Community 42"

Cohesion: 0.21
Nodes (4): CountingEntity, StubScenario, TestPacing, TestTickPrecision

### Community 43 - "Community 43"

Cohesion: 0.16
Nodes (5): spectrum_websocket (), _pump (), stream_events (), _watch (), WsStreamState

### Community 44 - "Community 44"

Cohesion: 0.12
Nodes (15): test_body_with_accurate_length_under_limit_accepted (), test_patch_radio_immutable_id_field_422 (),
test_patch_radio_unknown_field_422 (), test_post_geodata_layers_missing_field_422 (),
test_post_radios_missing_subfield_422 (), test_post_radios_nan_frequency_rejected_before_domain (),
test_post_radios_unknown_field_422 (), test_post_scenarios_empty_body_422 () (+7 more)

### Community 45 - "Community 45"

Cohesion: 0.23
Nodes (5): InMemoryEventBus, test_event_bus_changes_during_publish_affect_later_publishes_only (),
test_event_bus_double_subscribe_is_idempotent_and_unknown_unsubscribe_noop (),
test_event_bus_handler_errors_never_propagate_and_do_not_stop_delivery (),
test_event_bus_handlers_run_in_subscription_order_on_publisher_thread ()

### Community 49 - "Community 49"

Cohesion: 0.15
Nodes (4): raw (), TestHappyPath, TestModels, TestNodeType

### Community 52 - "Community 52"

Cohesion: 0.17
Nodes (11): args, entry, id, language, name, pass_filenames, stages, repos (+3 more)

### Community 55 - "Community 55"

Cohesion: 0.24
Nodes (3): _FlakyEntity, _NormalEntity, TestEntityFailureIsolation

## Knowledge Gaps

- **1 isolated node (s):** `radiocom`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 571 node (s) total have ≤1 connection when
  file, concept and rationale nodes are included.)
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions

_Questions this graph is uniquely positioned to answer:_

- **Why does `GeoPosition` connect `Community 9` to `Community 0`, `Community 4`, `Community 6`, `Community 7`,
  `Community 8`, `Community 12`, `Community 14`, `Community 15`, `Community 17`, `Community 18`?**
  _High betweenness centrality (0.086) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `GeoPosition` (e.g. with `Radio` and `GeodataProvider`) actually
  correct?**
  _`GeoPosition` has 25 INFERRED edges - model-reasoned connections that need verification._
- **What connects `radiocom` to the rest of the system?**
  _1 weakly-connected nodes found - possible missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.059097127222982215 - nodes in this community are weakly interconnected._
- **Why does `CoreSimulationEngine` connect `Community 22` to `Community 32`, `Community 42`, `Community 13`,
  `Community 46`, `Community 48`, `Community 50`, `Community 51`, `Community 54`, `Community 55`, `Community 57`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `create_app()` (e.g. with `EventBus` and `.seed_default_scenarios()`)
  actually correct?**
  _`create_app()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07132867132867132 - nodes in this community are weakly interconnected._