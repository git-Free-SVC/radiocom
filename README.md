# RadioCom W0-5 — Plugin SDK contracts

Run everything (from the repo root, `./radiocom`):

    pytest tests\ -v                      # Windows: works from cmd/PowerShell too

Test a real implementation against a contract (options replace the old single `--impl`):

    pytest tests\contract\test_propagation_model_contract.py --propagation-impl=services.propagation.free_space:FreeSpaceModel
    pytest tests\contract\test_geodata_provider_contract.py  --geodata-impl=services.geodata_api:GeoServerProvider
    pytest tests\contract\test_waveform_codec_contract.py    --waveform-impl=services.dsp.bpsk:Bpsk
    pytest tests\contract\test_event_bus_contract.py         --eventbus-impl=...:NatsEventBus
    pytest tests\contract\test_simulation_contract.py        --engine-impl=...:Engine --scheduler-impl=...:Scheduler

Rules
* Contract test files must pass UNMODIFIED for any implementation.
* `test_sdk_frozen.py` fails on any signature change. To change the SDK on purpose: ADR,
  bump `SDK_VERSION`, then `python -m tests.contract._snapshot --write`.
* Requires Python >= 3.10, numpy, pytest.
