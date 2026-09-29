# Wave 1 Briefing

`foundation-v0` is tagged. Fork from it — one branch per agent, one agent
per package. Do not touch `libraries/plugin_sdk/` or `libraries/protocols/`
(see `docs/adr/ADR-000-foundation-interfaces.md`); if you believe an
interface is wrong, stop and flag it rather than editing it.

| Agent | Package to own | Implement/consume | Contract test to pass | Fake to ship |
|---|---|---|---|---|
| A — Simulation Core | `services/simulation/` | `SimulationEngine` (`libraries/plugin_sdk/simulation.py`) | none yet (Integration Agent writes one once real) | in-memory scenario runner, no real physics |
| B — Scenario Engine | `services/scenario/` | validate/version against `libraries/protocols/scenario.schema.json` | schema round-trip test | — |
| C — World Engine | `services/world/` | WGS84↔ECEF↔ENU transforms; consumes `GeodataProvider` | `tests/contract/test_geodata_provider_contract.py` against your own fake if you extend it | can keep using `tests/contract/fakes/flat_geodata_provider.py` |
| D — Propagation Engine | `services/propagation/`, `libraries/physics/` | `PropagationModel` (`libraries/plugin_sdk/propagation.py`) | `tests/contract/test_propagation_model_contract.py --impl=services.propagation.free_space:FreeSpaceModel` | none needed — implement for real, it's self-contained |
| E — API Skeleton | `services/api/` | REST/WS routes per `libraries/protocols/openapi.yaml` | `openapi-spec-validator` clean; routes return mocked payloads matching schema | mock Scenario/Core responses |

## Rules
1. One agent, one package, one branch — never two agents editing files
   under the same `services/*` directory.
2. Read only your own Protocol's docstring + its contract test template.
   You should not need to read another agent's implementation.
3. Ship a fake of your own output if anything in Wave 2 depends on you
   (see architecture doc §36 table) — the Integration Agent swaps
   fake→real later, you never do it yourself.
4. Definition of Done: unit tests green, package importable standalone,
   passes its contract test (if one exists for your interface).
5. Do not start Wave 2 or fork the API/UI against your *implementation* —
   they fork against the *OpenAPI spec* / *Protocol*, which are already frozen.

Refer to the full architecture document for the "why" behind any of this
— §5 (principles), §8 (component responsibilities), §36 (multi-agent plan).
