from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries


class ReplayFidelity(StrEnum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    UNAVAILABLE = "UNAVAILABLE"


class ReplayMode(StrEnum):
    RECORDED_CONFIGURATION = "recorded_configuration"
    WHAT_IF = "what_if"


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    parameter_id: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""
    description_code: str = ""
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlgorithmMetadata:
    plugin_id: str
    version: str
    display_name: str
    description: str
    required_records: tuple[str, ...]
    optional_records: tuple[str, ...]
    required_channels: tuple[str, ...]
    optional_channels: tuple[str, ...]
    parameter_schema: tuple[ParameterSpec, ...]
    standard_outputs: tuple[str, ...]
    diagnostic_outputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlgorithmAvailability:
    available: bool
    fidelity: ReplayFidelity
    missing_inputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    supported_input_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    mode: ReplayMode = ReplayMode.RECORDED_CONFIGURATION
    input_source: str = "recorded_inertial_increment"
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class AlgorithmResult:
    algorithm_id: str
    algorithm_version: str
    input_source: str
    parameters: Mapping[str, Any]
    fidelity: ReplayFidelity
    missing_inputs: tuple[str, ...]
    warnings: tuple[str, ...]
    channels: Mapping[str, TimeSeries]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    provenance: str = "Recomputed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "channels", MappingProxyType(dict(self.channels)))
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


class AlgorithmPlugin(ABC):
    metadata: AlgorithmMetadata

    @abstractmethod
    def availability(
        self,
        dataset: FlightDataset,
        input_source: str | None = None,
    ) -> AlgorithmAvailability:
        raise NotImplementedError

    @abstractmethod
    def run(
        self,
        dataset: FlightDataset,
        request: ReplayRequest,
        context: TaskContext | None = None,
    ) -> AlgorithmResult:
        raise NotImplementedError
