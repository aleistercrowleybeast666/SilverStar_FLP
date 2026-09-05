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
    OFFLINE = "offline"
    WHAT_IF = "what_if"


@dataclass(frozen=True, slots=True)
class StateGroupSpec:
    """One semantically coherent estimator-state group shown by the GUI."""

    group_id: str
    label_key: str
    component_names: tuple[str, ...]
    unit: str
    covariance_channel: str
    covariance_diagonal_indices: tuple[int, ...]
    file_stem: str = ""

    def __post_init__(self) -> None:
        if not self.group_id or not self.label_key or not self.covariance_channel:
            raise ValueError("state_group_identity_required")
        if not self.component_names:
            raise ValueError("state_group_components_required")
        if len(self.component_names) != len(self.covariance_diagonal_indices):
            raise ValueError("state_group_covariance_indices_mismatch")
        if any(index < 0 for index in self.covariance_diagonal_indices):
            raise ValueError("state_group_covariance_index_invalid")


@dataclass(frozen=True, slots=True)
class MeasurementGroupSpec:
    """Estimator measurement/update diagnostics for one semantic sensor group."""

    measurement_group_id: str
    label_key: str
    dimension: int
    component_names: tuple[str, ...]
    innovation_channel: str
    nis_channel: str
    update_result_channel: str
    r_scale_channel: str
    measurement_age_channel: str = ""
    measurement_uncertainty_channel: str = ""
    effective_r_channel: str = ""
    update_result_index: int = 0
    r_scale_index: int = 0
    attempt_mask_channel: str = ""
    attempt_mask_bit: int = 0
    dimension_channel: str = ""
    soft_threshold_parameter_id: str = ""
    hard_threshold_parameter_id: str = ""
    unit: str = "1"
    file_stem: str = ""
    configuration_fields: tuple[str, ...] = ()
    configuration_provider_indices: tuple[int, ...] = ()
    measurement_record_names: tuple[str, ...] = ()
    measurement_validity_channel: str = ""

    def __post_init__(self) -> None:
        if not self.measurement_group_id or not self.label_key:
            raise ValueError("measurement_group_identity_required")
        if self.dimension <= 0:
            raise ValueError("measurement_group_dimension_invalid")
        if len(self.component_names) != self.dimension:
            raise ValueError("measurement_group_components_mismatch")
        if self.update_result_index < 0 or self.r_scale_index < 0:
            raise ValueError("measurement_group_channel_index_invalid")
        if self.attempt_mask_bit < 0:
            raise ValueError("measurement_group_attempt_mask_invalid")
        if any(index < 0 for index in self.configuration_provider_indices):
            raise ValueError("measurement_group_provider_index_invalid")


@dataclass(frozen=True, slots=True)
class FullCovarianceSpec:
    """Metadata required to reconstruct and export one estimator's full P."""

    channel_id: str
    file_stem: str
    state_symbols: tuple[str, ...]
    state_units: tuple[str, ...]
    storage: str = "upper_triangle"
    initial_record_name: str = ""
    initial_diagonal_field: str = ""

    def __post_init__(self) -> None:
        if not self.channel_id or not self.file_stem:
            raise ValueError("full_covariance_identity_required")
        if not self.state_symbols:
            raise ValueError("full_covariance_states_required")
        if len(self.state_symbols) != len(self.state_units):
            raise ValueError("full_covariance_state_units_mismatch")
        if self.storage not in ("upper_triangle", "full_matrix"):
            raise ValueError("full_covariance_storage_invalid")


@dataclass(frozen=True, slots=True)
class EstimatorVisualizationSpec:
    """Metadata that lets State Estimation adapt without algorithm-specific code."""

    state_groups: tuple[StateGroupSpec, ...]
    measurement_groups: tuple[MeasurementGroupSpec, ...]
    full_covariance: FullCovarianceSpec | None = None

    def __post_init__(self) -> None:
        state_ids = tuple(group.group_id for group in self.state_groups)
        measurement_ids = tuple(
            group.measurement_group_id for group in self.measurement_groups
        )
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("duplicate_state_group")
        if len(measurement_ids) != len(set(measurement_ids)):
            raise ValueError("duplicate_measurement_group")


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
    label_key: str = ""
    group_key: str = ""
    tooltip_key: str = ""
    step: float | None = None


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
    estimator_visualization: EstimatorVisualizationSpec | None = None
    firmware_component_ids: tuple[str, ...] = ()
    recorded_output_roles: tuple[str, ...] = ()
    required_semantic_roles: tuple[str, ...] = ()
    offline_default_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "offline_default_parameters",
            MappingProxyType(dict(self.offline_default_parameters)),
        )


@dataclass(frozen=True, slots=True)
class AlgorithmAvailability:
    available: bool
    fidelity: ReplayFidelity
    missing_inputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    supported_input_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlgorithmConfigurationAvailability:
    recorded_available: bool
    offline_available: bool
    firmware_member: bool
    recorded_output_available: bool
    recorded_parameters: Mapping[str, Any] = field(default_factory=dict)
    offline_parameters: Mapping[str, Any] = field(default_factory=dict)
    missing_recorded_parameters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "recorded_parameters",
            MappingProxyType(dict(self.recorded_parameters)),
        )
        object.__setattr__(
            self,
            "offline_parameters",
            MappingProxyType(dict(self.offline_parameters)),
        )


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    mode: ReplayMode = ReplayMode.RECORDED_CONFIGURATION
    input_source: str = "corrected_imu"
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

    def recorded_parameters(self, dataset: FlightDataset) -> Mapping[str, Any]:
        """Return the parameter values represented by this particular recorded log."""

        del dataset
        return MappingProxyType({})

    def FirmwareMember_Is(self, dataset: FlightDataset) -> bool:
        semantic_context = dataset.semantic_context
        if semantic_context is None:
            return False
        return any(
            semantic_context.FirmwareAlgorithm_IsMember(component_id)
            for component_id in self.metadata.firmware_component_ids
        )

    def RecordedOutput_IsAvailable(self, dataset: FlightDataset) -> bool:
        return bool(self.metadata.recorded_output_roles) and any(
            dataset.Series_Get(role_id) is not None
            for role_id in self.metadata.recorded_output_roles
        )

    def OfflineParameters_Get(self) -> Mapping[str, Any]:
        declared = dict(self.metadata.offline_default_parameters)
        for parameter in self.metadata.parameter_schema:
            declared.setdefault(parameter.parameter_id, parameter.default)
        return MappingProxyType(declared)

    def ConfigurationAvailability_Get(
        self,
        dataset: FlightDataset,
        *,
        input_available: bool = True,
    ) -> AlgorithmConfigurationAvailability:
        recorded = dict(self.recorded_parameters(dataset))
        required_parameter_ids = tuple(
            parameter.parameter_id
            for parameter in self.metadata.parameter_schema
        )
        missing = tuple(
            parameter_id
            for parameter_id in required_parameter_ids
            if parameter_id not in recorded
        )
        firmware_member = self.FirmwareMember_Is(dataset)
        recorded_output = self.RecordedOutput_IsAvailable(dataset)
        return AlgorithmConfigurationAvailability(
            recorded_available=(
                input_available
                and firmware_member
                and not missing
            ),
            offline_available=input_available,
            firmware_member=firmware_member,
            recorded_output_available=recorded_output,
            recorded_parameters=recorded,
            offline_parameters=self.OfflineParameters_Get(),
            missing_recorded_parameters=missing,
        )

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
