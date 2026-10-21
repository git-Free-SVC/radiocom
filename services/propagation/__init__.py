"""Propagation model implementations.

Currently one model is available: :class:`FreeSpaceModel`, the MVP
free-space path-loss model built on :mod:`libraries.physics`. Later phases
add terrain-aware models (TwoRay, Hata, ITM, ray tracing) next to it, each
implementing the same frozen ``PropagationModel`` Protocol.
"""

from __future__ import annotations

from .free_space import FreeSpaceModel, FreeSpaceValidityDomain

__all__ = ["FreeSpaceModel", "FreeSpaceValidityDomain"]
