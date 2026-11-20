# Graph Report - radiocom (2026-11-20)

## Corpus Check

- 132 files · ~59,229 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file (s) not represented in the graph (top: (none) 1, .lock 1)

## Summary

- 1873 nodes · 4800 edges · 81 communities (60 shown, 21 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 457 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness

- Built from commit: `68c5e2df`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)

- test_propagation_model_contract.py
- test_physics_link_budget.py
- check_sdk_freeze.py
- test_api.py
- stress_scenario.py
- test_contract_conformance.py
- test_propagation_free_space.py
- LayerRef
- app.py
- GeoPosition
- Any
- properties
- ENUPosition
- WallClock
- pytest
- create_app
- test_ws.py
- line_of_sight
- geo_to_enu
- scenario/ __init__.py
- test_waveform_codec_contract.py
- InMemorySimulationRegistry
- CoreSimulationEngine
- api/conftest.py
- math
- loader.py
- MockSimulationEngine
- scenario
- steps
- WsConnection
- validation.py
- load_scenario
- SimulationEvent
- test_simulation_contract.py
- PhysicsInputError
- test_event_bus_contract.py
- api/test_determinism.py
- api/errors.py
- properties
- serialization.py
- simple_engine.py
- CorePort
- numpy
- ws_connection.py
- json
- InMemoryEventBus
- SimulationEngine
- WebSocketTestClient
- SimpleEngine
- test_scenario_engine.py
- test_gnuradio_adapter.py
- simulation.py
- hooks
- InProcessEventBus
- test_world_frame_and_safety.py
- mocks.py
- test_port_contract.py
- link_budget.py
- test_free_space.py
- pathlib
- parametrize
- contract/conftest.py
- sdk_freeze.py
- _assert_imports_resolve_inside_repository
- test_unexpected_exception_returns_500_envelope_without_traceback
- radiocom
- test_freeze_rules.py
- _snapshot.py
- Frequency
- BpskCodec
- time
- EventBus

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

- `test_conforms_to_protocol()` --uses--> `EventBus`  [INFERRED]
  tests/contract/test_event_bus_contract.py → libraries/plugin_sdk/event_bus.py
- `test_engine_is_abc_impl()` --uses--> `SimulationEngine`  [INFERRED]
  tests/contract/test_simulation_contract.py → libraries/plugin_sdk/simulation.py
- `test_scheduler_is_abc_impl()` --uses--> `SimulationScheduler`  [INFERRED]
  tests/contract/test_simulation_contract.py → libraries/plugin_sdk/simulation.py
- `_positive_rate()` --uses--> `DSPInputError`  [INFERRED]
  integrations/gnu_radio/protocol.py → services/dsp/_validation.py
- `_encode_payload()` --uses--> `DSPInputError`  [INFERRED]
  integrations/gnu_radio/protocol.py → services/dsp/_validation.py

## Import Cycles
- None detected.

## Communities (81 total, 21 thin omitted)

### Community 0 - "test_propagation_model_contract.py"

Cohesion: 0.11
Nodes (12): PropagationResult, PropagationModel, ValidityDomain, _distance_m (), _Domain, FreeSpaceReferenceModel, _
FlatValidityDomain, NullPropagationModel (+4 more)

### Community 1 - "test_physics_link_budget.py"

Cohesion: 0.09
Nodes (33): LinkBudgetInput, compute_link_budget (), dbm_to_watts (), eb_n0_db (), link_margin_db (), noise_floor_dbm
(), received_power_dbm (), snr_db () (+25 more)

### Community 2 - "check_sdk_freeze.py"

Cohesion: 0.17
Nodes (17): check_git_immutability (), _git (), main (), run (), build_snapshot (), bump_ok (), check_history (),
classify () (+9 more)

### Community 3 - "test_api.py"
Cohesion: 0.04
Nodes (3): test_get_elevation_is_deterministic_and_schema_valid (), test_get_elevation_profile_exact_sample_count (),
test_patch_radio_updates_position_and_publishes_map_delta ()

### Community 4 - "stress_scenario.py"

Cohesion: 0.29
Nodes (9): big_scenario (), fuzz (), hostile_inputs (), main (), _paths (), scale_tests (), timed (), _walk () (+1 more)

### Community 5 - "test_contract_conformance.py"
Cohesion: 0.08
Nodes (32): load_frozen_schema (), test_post_scenarios_scenario_validates_against_frozen_schema (),
app_declared_statuses (), app_operations (), app_ws_paths (), compare_routes (), compare_statuses (), load_yaml_contract
() (+24 more)

### Community 6 - "test_propagation_free_space.py"

Cohesion: 0.14
Nodes (27): Radio, make_radio (), pair (), test_bad_gain_and_cable (), test_bad_position (), test_bad_power (),
test_cable_loss_and_gain_flow_through (), test_clamp_boundary_continuous_and_monotonic () (+19 more)

### Community 7 - "LayerRef"

Cohesion: 0.10
Nodes (14): BBox, Feature, GeodataProvider, GeoJSONFile, LayerRef, PostGISTable, MockGeodataProvider,
test_conforms_to_protocol () (+6 more)

### Community 8 - "app.py"

Cohesion: 0.10
Nodes (3): ClockPort, GeodataPort, SimulationRegistryPort

### Community 9 - "GeoPosition"

Cohesion: 0.10
Nodes (6): GeoPosition, geo_to_ecef (), TestGeoPosition, TestForwardTransform, TestNearPole, TestRandomizedAccuracy

### Community 10 - "Any"
Cohesion: 0.12
Nodes (6): _errors_for (), TestInterference, TestMobileRadioPositionRequired, TestPosition, TestRadioCatalog,
TestRequiredFields

### Community 11 - "properties"
Cohesion: 0.05
Nodes (41): properties, type, items, type, properties, required, type, type (+33 more)

### Community 12 - "ENUPosition"

Cohesion: 0.16
Nodes (6): ENUPosition, ENUFrame, geodetic_rad_to_ecef (), TestENUPosition, _random_positions (), TestENUFrame

### Community 13 - "WallClock"

Cohesion: 0.12
Nodes (3): SimulationClock, WallClock, InMemorySimulationState

### Community 14 - "pytest"
Cohesion: 0.15
Nodes (26): _HasGeoPosition, haversine_distance_m (), _lat_lon (), slant_range_m (), P (), _rand_point (), raw (),
test_antimeridian_crossing () (+18 more)

### Community 15 - "create_app"
Cohesion: 0.13
Nodes (26): create_app (), add_radio_route (), create_scenario_route (), create_simulation_route (),
elevation_profile_route (), elevation_route (), get_link_route (), get_scenario_route () (+18 more)

### Community 16 - "test_ws.py"
Cohesion: 0.13
Nodes (30): telemetry_topic (), app (), assert_envelope (), assert_no_leaked_tasks (),
test_disconnect_unsubscribes_and_records_stats (), main (), test_disconnect_with_queued_messages_cleans_up (), main ()
(+22 more)

### Community 17 - "line_of_sight"

Cohesion: 0.11
Nodes (5): line_of_sight (), FlatGeodataProvider, TestLineOfSight, WallGeodataProvider, TestLineOfSightSafety

### Community 18 - "geo_to_enu"
Cohesion: 0.14
Nodes (7): enu_to_geo (), _frame_for (), geo_to_enu (), _assert_same (), _nearby_origin (), TestENUSanityCases,
TestRoundTrip

### Community 19 - "scenario/ __init__.py"

Cohesion: 0.11
Nodes (8): Environment, InterferenceSource, Node, RadioDefinition, Scenario, _ScenarioModel, TerrainConfig,
VectorLayerConfig

### Community 20 - "test_waveform_codec_contract.py"
Cohesion: 0.11
Nodes (3): WaveformCodec, test_conforms_to_protocol (), test_noiseless_roundtrip ()

### Community 21 - "InMemorySimulationRegistry"
Cohesion: 0.12
Nodes (4): InMemoryScenarioStore, InMemorySimulationRegistry, link_to_payload (), test_scenario_port_behaviours ()

### Community 22 - "CoreSimulationEngine"

Cohesion: 0.06
Nodes (18): derive_entity_seed (), CoreSimulationEngine, CountingEntity, RngEntity, StubScenario,
TestCheckpointRestore, _run (), TestDeterminism (+10 more)

### Community 23 - "api/conftest.py"
Cohesion: 0.15
Nodes (14): asgi_request (), assert_error (), assert_error_detail_list (), create_radio (), create_scenario (),
create_simulation (), deps (), get () (+6 more)

### Community 24 - "math"

Cohesion: 0.17
Nodes (14): free_space_path_loss_db (), test_6db_per_distance_doubling_and_20db_per_decade (), test_bad_distance_raises
(), test_bad_frequency_raises (), test_consistent_with_exact_friis (), test_extreme_finite_distances_stay_finite (),
test_extreme_finite_frequencies_stay_finite (), test_golden_values () (+6 more)

### Community 25 - "loader.py"
Cohesion: 0.11
Nodes (8): ScenarioError, ScenarioFileError, ScenarioValidationError, _construct_unique_mapping (), _
DuplicateKeyError, _json_unique_object (), _read_data (), _ScenarioYamlLoader

### Community 26 - "MockSimulationEngine"
Cohesion: 0.15
Nodes (5): _MockSimulationClock, MockSimulationEngine, MockSimulationState,
test_engine_call_log_records_exactly_one_entry_per_attempt (), test_engine_lifecycle_matches_frozen_state_machine ()

### Community 27 - "scenario"
Cohesion: 0.08
Nodes (24): terrain, vector_layers, bandwidth, frequency, id, power, id, position (+16 more)

### Community 28 - "steps"
Cohesion: 0.10
Nodes (23): BASE_REF, jobs, lint-and-test, sdk-freeze, runs-on, steps, name, on (+15 more)

### Community 29 - "WsConnection"
Cohesion: 0.14
Nodes (6): WsConnection, WsConnectionStats, test_backpressure_drops_oldest_and_counts (), main (),
test_publisher_never_blocks_when_client_is_slow (), main ()

### Community 30 - "validation.py"
Cohesion: 0.18
Nodes (11): _depth_errors (), _describe (), _extension_errors (), format_path (), _json_type_name (), _non_finite_errors
(), _quoted (), _schema_errors () (+3 more)

### Community 31 - "load_scenario"

Cohesion: 0.17
Nodes (4): load_scenario (), TestHardening, TestLoadingErrors, TestYamlJsonParity

### Community 32 - "SimulationEvent"

Cohesion: 0.13
Nodes (7): SimulationEvent, SimulationScheduler, HeapScheduler, HeapScheduler, TestSchedulerConcurrency, pusher (),
TestHeapScheduler

### Community 33 - "test_simulation_contract.py"

Cohesion: 0.13
Nodes (18): RecordingEntity, _run_and_checkpoint (), _running (), Scenario, test_checkpoint_roundtrip (),
test_engine_is_abc_impl (), test_entity_ticks_are_ordered_and_bounded (), test_illegal_transitions_raise () (+10 more)

### Community 34 - "PhysicsInputError"

Cohesion: 0.19
Nodes (5): PhysicsInputError, _finite (), finite (), in_range (), positive ()

### Community 35 - "test_event_bus_contract.py"
Cohesion: 0.14
Nodes (3): test_conforms_to_protocol (), test_failing_handler_does_not_break_publisher_or_others (),
test_unsubscribe_during_publish_is_safe ()

### Community 36 - "api/test_determinism.py"

Cohesion: 0.14
Nodes (6): _sequence (), test_created_at_comes_only_from_the_injected_fake_clock (),
test_identical_sequence_on_two_fresh_apps_is_byte_identical (),
test_parallel_control_requests_produce_exactly_n_engine_entries (),
test_parallel_radio_creations_yield_unique_counter_ids (), test_parallel_scenario_creations_yield_unique_counter_ids ()

### Community 37 - "api/errors.py"

Cohesion: 0.15
Nodes (7): enforce_body_limit (), api_error_handler (), error_response (), install_exception_handlers (),
internal_error_handler (), request_validation_handler (), value_error_handler ()

### Community 38 - "properties"
Cohesion: 0.11
Nodes (17): type, properties, margin_db, quality, rx_id, snr_db, time_s, tx_id (+9 more)

### Community 39 - "serialization.py"
Cohesion: 0.17
Nodes (6): ResponseContractError, datetime_to_iso (), iter_non_finite (), position_payload (), radio_to_payload (),
to_payload ()

### Community 40 - "simple_engine.py"

Cohesion: 0.18
Nodes (3): SimulationEntity, SimpleClock, SimpleState

### Community 42 - "numpy"

Cohesion: 0.06
Nodes (42): AMCodec, ber_bpsk (), ber_coherent_orthogonal (), check_ber_model (), _gamma_from_db (), scaled_bandwidth
(), BPSKCodec, FMCodec (+34 more)

### Community 43 - "ws_connection.py"

Cohesion: 0.11
Nodes (9): spectrum_websocket (), telemetry_websocket (), _pump (), stream_events (), _watch (), WsStreamState,
build_telemetry_snapshot (), make_message () (+1 more)

### Community 44 - "json"
Cohesion: 0.12
Nodes (15): test_body_with_accurate_length_under_limit_accepted (), test_patch_radio_immutable_id_field_422 (),
test_patch_radio_unknown_field_422 (), test_post_geodata_layers_missing_field_422 (),
test_post_radios_missing_subfield_422 (), test_post_radios_nan_frequency_rejected_before_domain (),
test_post_radios_unknown_field_422 (), test_post_scenarios_empty_body_422 () (+7 more)

### Community 45 - "InMemoryEventBus"
Cohesion: 0.23
Nodes (5): InMemoryEventBus, test_event_bus_changes_during_publish_affect_later_publishes_only (),
test_event_bus_double_subscribe_is_idempotent_and_unknown_unsubscribe_noop (),
test_event_bus_handler_errors_never_propagate_and_do_not_stop_delivery (),
test_event_bus_handlers_run_in_subscription_order_on_publisher_thread ()

### Community 48 - "SimpleEngine"

Cohesion: 0.16
Nodes (3): SimulationScenario, SimulationState, SimpleEngine

### Community 49 - "test_scenario_engine.py"

Cohesion: 0.13
Nodes (6): parse_scenario_dict (), raw (), TestHappyPath, TestModels, TestNodeType, TestVersioning

### Community 50 - "test_gnuradio_adapter.py"

Cohesion: 0.05
Nodes (36): GnuRadioCodecAdapter, _request_id (), WorkerTransport, WorkerExecutionError, WorkerProtocolError,
WorkerTimeoutError, WorkerUnavailableError, _decode_parts () (+28 more)

### Community 52 - "hooks"
Cohesion: 0.17
Nodes (11): args, entry, id, language, name, pass_filenames, stages, repos (+3 more)

### Community 54 - "test_world_frame_and_safety.py"

Cohesion: 0.13
Nodes (6): ecef_to_geo (), ecef_to_geodetic_rad (), _to_geo_position (), LOSResult, _require_finite (),
TestInverseTransformGuards

### Community 55 - "mocks.py"

Cohesion: 0.18
Nodes (14): Antenna, Receiver, Transmitter, build_radio (), _radio (), test_more_tx_power_more_rx_power (),
test_path_loss_grows_with_distance (), test_path_loss_grows_with_frequency () (+6 more)

### Community 56 - "test_port_contract.py"

Cohesion: 0.16
Nodes (6): FakeClock, _registry (), test_clock_port_is_injected_and_deterministic (), test_core_port_behaviours (),
test_mock_satisfies_its_protocol (), test_registry_port_behaviours ()

### Community 57 - "link_budget.py"

Cohesion: 0.14
Nodes (7): LinkQuality, LinkState, LinkBudgetResult, link_quality (), test_bad_inputs (), test_boundaries (),
test_monotonic_and_exhaustive ()

### Community 58 - "test_free_space.py"

Cohesion: 0.21
Nodes (15): free_space_path_loss_db (), FreeSpaceModel, FreeSpaceValidityDomain, _radio (),
test_coincident_positions_use_one_meter_clamp_without_domain_error (), test_evaluate_does_not_mutate_frozen_radio_inputs
(), test_free_space_model_implements_frozen_protocol_and_result_shape (),
test_invalid_transmit_power_and_frequency_raise_physics_input_error () (+7 more)

### Community 59 - "pathlib"

Cohesion: 0.18
Nodes (4): content_audit (), main (), run (), test_import_services_api_has_no_side_effects ()

### Community 61 - "contract/conftest.py"

Cohesion: 0.26
Nodes (9): bus (), codec (), engine (), load_impl (), model (), provider (), pytest_addoption (), scheduler () (+1 more)

### Community 62 - "sdk_freeze.py"

Cohesion: 0.20
Nodes (7): build_surface (), _callable_name (), _describe_class (), _extends_contract (), _field_default (), _flatten
(), _module_constants ()

### Community 75 - "test_freeze_rules.py"

Cohesion: 0.22
Nodes (9): _surf (), test_bump_ok (), test_history_check_flags_hand_edited_snapshots (), test_identical_is_none (),
test_new_function_is_minor (), test_new_method_on_plain_class_is_minor (), test_new_protocol_method_is_major (),
test_removed_or_changed_is_major () (+1 more)

### Community 76 - "_snapshot.py"
Cohesion: 0.24
Nodes (3): build (), _describe_class (), test_public_surface_matches_frozen_snapshot ()

### Community 79 - "time"

Cohesion: 0.38
Nodes (3): best_us_per_op (), main (), test_100000_symbol_and_200000_analytic_call_performance_budget ()

## Knowledge Gaps

- **1 isolated node (s):** `radiocom`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 624 node (s) total have ≤1 connection when
  file, concept and rationale nodes are included.)
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GeoPosition` connect `GeoPosition` to `test_propagation_model_contract.py`,
  `test_propagation_free_space.py`, `LayerRef`, `app.py`, `ENUPosition`, `pytest`, `create_app`, `time`,
  `line_of_sight`, `geo_to_enu`, `test_world_frame_and_safety.py`, `mocks.py`, `test_port_contract.py`,
  `test_free_space.py`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `GeoPosition` (e.g. with `Radio` and `GeodataProvider`) actually
  correct?**
  _`GeoPosition` has 25 INFERRED edges - model-reasoned connections that need verification._
- **What connects `radiocom` to the rest of the system?**
  _1 weakly-connected nodes found - possible missing edges._
- **Should `test_propagation_model_contract.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10606060606060606 - nodes in this community are weakly interconnected._
- **Why does `CoreSimulationEngine` connect `CoreSimulationEngine` to `SimulationEvent`, `WallClock`,
  `SimulationEngine`, `SimpleEngine`, `simulation.py`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `create_app()` (e.g. with `EventBus` and `.seed_default_scenarios()`)
  actually correct?**
  _`create_app()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_physics_link_budget.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08653061224489796 - nodes in this community are weakly interconnected._