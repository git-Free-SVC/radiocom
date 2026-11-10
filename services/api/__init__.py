"""Agent E — API skeleton (Wave 1): REST + WebSocket routes over injected ports.

Importing this package performs no file IO, opens no sockets, creates no
files and requires no services (asserted by test_import_side_effect.py).
"""

from services.api.app import MAX_BODY_BYTES, create_app
from services.api.ports import (
    ClockPort,
    CorePort,
    GeodataPort,
    ScenarioPort,
    SimulationRegistryPort,
)

__all__ = [
    "MAX_BODY_BYTES",
    "ClockPort",
    "CorePort",
    "GeodataPort",
    "ScenarioPort",
    "SimulationRegistryPort",
    "create_app",
]
