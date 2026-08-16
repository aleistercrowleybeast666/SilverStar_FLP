from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmResult,
    ReplayFidelity,
    ReplayMode,
)


class AnalysisSourceKind(StrEnum):
    RECORDED = "recorded"
    RECOMPUTED = "recomputed"
    WHAT_IF = "what_if"


@dataclass(frozen=True, slots=True)
class AnalysisSource:
    source_id: str
    kind: AnalysisSourceKind
    algorithm_id: str | None = None
    result_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecordedSolutionLayer:
    solution_id: str
    algorithm_id: str
    channel_id: str
    series: TimeSeries


@dataclass(frozen=True, slots=True)
class ReplayStoredResult:
    result_id: str
    source_id: str
    run_index: int
    algorithm_name: str
    algorithm_id: str
    algorithm_version: str
    mode: ReplayMode
    input_source: str
    parameters: Mapping[str, object]
    fidelity: ReplayFidelity
    warnings: tuple[str, ...]
    channels: Mapping[str, TimeSeries]
    diagnostics: Mapping[str, object]
    result: AlgorithmResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "channels", MappingProxyType(dict(self.channels)))
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))

    @property
    def kind(self) -> AnalysisSourceKind:
        return (
            AnalysisSourceKind.WHAT_IF
            if self.mode == ReplayMode.WHAT_IF
            else AnalysisSourceKind.RECOMPUTED
        )

    @property
    def sample_count(self) -> int:
        return max((series.count for series in self.channels.values()), default=0)

    @property
    def analysis_ready(self) -> bool:
        required = (
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
        )
        return (
            self.fidelity != ReplayFidelity.UNAVAILABLE
            and not self.result.missing_inputs
            and all(
                (series := self.channels.get(channel_id)) is not None
                and series.count > 0
                and bool(series.valid.any())
                for channel_id in required
            )
        )

    @property
    def time_coverage_us(self) -> tuple[int, int] | None:
        starts = [int(series.timestamp_us[0]) for series in self.channels.values() if series.count]
        ends = [int(series.timestamp_us[-1]) for series in self.channels.values() if series.count]
        if not starts or not ends:
            return None
        return min(starts), max(ends)

    def StableName_Get(self) -> str:
        mode = "What-if" if self.mode == ReplayMode.WHAT_IF else "Recomputed"
        return f"{self.algorithm_name} / {mode} #{self.run_index}"


class ReplayResultStore:
    RECORDED_SOURCE_ID = "recorded"

    def __init__(self) -> None:
        self._entries: list[ReplayStoredResult] = []
        self._by_result_id: dict[str, ReplayStoredResult] = {}
        self._by_source_id: dict[str, ReplayStoredResult] = {}
        self._active_source_id = self.RECORDED_SOURCE_ID

    def Clear(self) -> None:
        self._entries.clear()
        self._by_result_id.clear()
        self._by_source_id.clear()
        self._active_source_id = self.RECORDED_SOURCE_ID

    def Result_Add(
        self,
        result: AlgorithmResult,
        *,
        algorithm_name: str | None = None,
    ) -> ReplayStoredResult:
        mode = (
            ReplayMode.WHAT_IF
            if result.provenance == "What-if"
            else ReplayMode.RECORDED_CONFIGURATION
        )
        same_mode_count = sum(
            entry.algorithm_id == result.algorithm_id and entry.mode == mode
            for entry in self._entries
        )
        run_index = same_mode_count + 1
        algorithm_key = result.algorithm_id.rsplit(".", 1)[-1]
        mode_key = "what_if" if mode == ReplayMode.WHAT_IF else "recomputed"
        result_id = f"{algorithm_key}:{mode_key}:{run_index}"
        source_id = f"replay:{result_id}"
        entry = ReplayStoredResult(
            result_id=result_id,
            source_id=source_id,
            run_index=run_index,
            algorithm_name=algorithm_name or algorithm_key,
            algorithm_id=result.algorithm_id,
            algorithm_version=result.algorithm_version,
            mode=mode,
            input_source=result.input_source,
            parameters=dict(result.parameters),
            fidelity=result.fidelity,
            warnings=tuple(result.warnings),
            channels=dict(result.channels),
            diagnostics=dict(result.diagnostics),
            result=result,
        )
        self._entries.append(entry)
        self._by_result_id[result_id] = entry
        self._by_source_id[source_id] = entry
        return entry

    def Entries_Get(self) -> tuple[ReplayStoredResult, ...]:
        return tuple(self._entries)

    def Entry_Get(self, result_id: str) -> ReplayStoredResult | None:
        return self._by_result_id.get(result_id)

    def SourceEntry_Get(self, source_id: str) -> ReplayStoredResult | None:
        return self._by_source_id.get(source_id)

    def Sources_Get(self) -> tuple[AnalysisSource, ...]:
        sources = [AnalysisSource(self.RECORDED_SOURCE_ID, AnalysisSourceKind.RECORDED)]
        sources.extend(
            AnalysisSource(
                entry.source_id,
                entry.kind,
                entry.algorithm_id,
                entry.result_id,
            )
            for entry in self._entries
            if entry.analysis_ready
        )
        return tuple(sources)

    def ActiveSource_Get(self) -> AnalysisSource:
        if self._active_source_id == self.RECORDED_SOURCE_ID:
            return AnalysisSource(self.RECORDED_SOURCE_ID, AnalysisSourceKind.RECORDED)
        entry = self._by_source_id.get(self._active_source_id)
        if entry is None or not entry.analysis_ready:
            self._active_source_id = self.RECORDED_SOURCE_ID
            return AnalysisSource(self.RECORDED_SOURCE_ID, AnalysisSourceKind.RECORDED)
        return AnalysisSource(entry.source_id, entry.kind, entry.algorithm_id, entry.result_id)

    def ActiveSource_Set(self, source_id: str) -> bool:
        if source_id != self.RECORDED_SOURCE_ID:
            entry = self._by_source_id.get(source_id)
            if entry is None or not entry.analysis_ready:
                return False
        self._active_source_id = source_id
        return True


class ChannelResolver:
    _ESTIMATOR_DIAGNOSTIC_QUANTITIES = frozenset(
        {"covariance", "innovation", "nis", "update_result"}
    )
    _RECORDED_DIRECT = {
        "attitude.q_nb": "pure_ins.recorded.attitude.q_nb",
        "navigation.linear_accel_enu": "pure_ins.recorded.navigation.linear_accel_enu",
        "imu.corrected.accel_b": "imu.corrected.accel_b",
        "imu.corrected.gyro_b": "imu.corrected.gyro_b",
    }

    def __init__(self, dataset: FlightDataset, store: ReplayResultStore) -> None:
        self.dataset = dataset
        self.store = store

    def Source_Get(self, source_id: str | None = None) -> AnalysisSource:
        if source_id is None:
            return self.store.ActiveSource_Get()
        if source_id == ReplayResultStore.RECORDED_SOURCE_ID:
            return AnalysisSource(source_id, AnalysisSourceKind.RECORDED)
        entry = self.store.SourceEntry_Get(source_id)
        if entry is None:
            return AnalysisSource(
                ReplayResultStore.RECORDED_SOURCE_ID,
                AnalysisSourceKind.RECORDED,
            )
        return AnalysisSource(entry.source_id, entry.kind, entry.algorithm_id, entry.result_id)

    def Series_Get(self, channel_id: str, source_id: str | None = None) -> TimeSeries | None:
        source = self.Source_Get(source_id)
        if source.kind == AnalysisSourceKind.RECORDED:
            return self.RecordedSeries_Get(channel_id)
        entry = self.store.SourceEntry_Get(source.source_id)
        if entry is None:
            return None
        return entry.channels.get(channel_id)

    def RecordedSeries_Get(
        self,
        channel_id: str,
        *,
        solution: str | None = None,
    ) -> TimeSeries | None:
        if channel_id in ("navigation.position_enu", "navigation.velocity_enu"):
            suffix = channel_id.removeprefix("navigation.")
            prefixes = {
                "pure_ins": ("pure_ins.recorded.navigation",),
                "kf6": ("kf6.recorded.navigation",),
                "final": ("kf6.recorded.navigation",),
                None: (
                    "kf6.recorded.navigation",
                    "pure_ins.recorded.navigation",
                ),
            }.get(solution, ())
            for prefix in prefixes:
                series = self.dataset.Series_Get(f"{prefix}.{suffix}")
                if series is not None:
                    return series
            return None
        direct_series = self.dataset.Series_Get(channel_id)
        if direct_series is not None:
            return direct_series
        direct_id = self._RECORDED_DIRECT.get(channel_id)
        if direct_id is not None:
            return self.dataset.Series_Get(direct_id)
        namespace, separator, remainder = channel_id.partition(".")
        if separator:
            return self.dataset.Series_Get(f"{namespace}.recorded.{remainder}")
        return None

    def RecordedSolutionLayers_Get(
        self,
        channel_id: str,
    ) -> tuple[RecordedSolutionLayer, ...]:
        if channel_id not in ("navigation.position_enu", "navigation.velocity_enu"):
            series = self.RecordedSeries_Get(channel_id)
            if series is None:
                return ()
            return (
                RecordedSolutionLayer(
                    "recorded",
                    "silverstar.recorded",
                    channel_id,
                    series,
                ),
            )
        layers: list[RecordedSolutionLayer] = []
        for solution_id, algorithm_id in (
            ("pure_ins", "silverstar.algorithm.pure_ins"),
            ("kf6", "silverstar.algorithm.kf6"),
        ):
            series = self.RecordedSeries_Get(channel_id, solution=solution_id)
            if series is not None:
                layers.append(
                    RecordedSolutionLayer(
                        solution_id,
                        algorithm_id,
                        channel_id,
                        series,
                    )
                )
        return tuple(layers)

    def RecordedNavigationSources_Get(self) -> tuple[str, ...]:
        sources: list[str] = []
        if self.RecordedSeries_Get(
            "navigation.position_enu", solution="pure_ins"
        ) is not None:
            sources.append("Pure INS")
        if self.RecordedSeries_Get(
            "navigation.position_enu", solution="kf6"
        ) is not None:
            sources.append("KF_6")
        return tuple(sources)

    def RecordedNavigationSource_Get(self) -> str:
        if any(
            self.dataset.Series_Get(channel_id) is not None
            for channel_id in (
                "kf6.recorded.navigation.position_enu",
                "kf6.recorded.navigation.velocity_enu",
            )
        ):
            return "KF_6"
        if any(
            self.dataset.Series_Get(channel_id) is not None
            for channel_id in (
                "pure_ins.recorded.navigation.position_enu",
                "pure_ins.recorded.navigation.velocity_enu",
            )
        ):
            return "Pure INS"
        return "N/A"

    def EstimatorSources_Get(
        self,
        estimator_algorithm_ids: Iterable[str] = (),
    ) -> tuple[AnalysisSource, ...]:
        algorithm_ids = tuple(dict.fromkeys(estimator_algorithm_ids))
        if not algorithm_ids:
            replay_ids = tuple(
                entry.algorithm_id
                for entry in self.store.Entries_Get()
                if any(
                    series.quantity in self._ESTIMATOR_DIAGNOSTIC_QUANTITIES
                    for series in entry.channels.values()
                )
            )
            recorded_namespaces = tuple(
                channel_id.partition(".recorded.")[0]
                for channel_id, series in self.dataset.series.items()
                if ".recorded." in channel_id
                and series.quantity in self._ESTIMATOR_DIAGNOSTIC_QUANTITIES
            )
            algorithm_ids = tuple(
                dict.fromkeys(
                    (*replay_ids, *(f"silverstar.algorithm.{name}" for name in recorded_namespaces))
                )
            )
        sources: list[AnalysisSource] = []
        for algorithm_id in algorithm_ids:
            namespace = algorithm_id.rsplit(".", 1)[-1]
            if any(
                channel_id.startswith(f"{namespace}.recorded.")
                for channel_id in self.dataset.series
            ):
                sources.append(
                    AnalysisSource(
                        ReplayResultStore.RECORDED_SOURCE_ID,
                        AnalysisSourceKind.RECORDED,
                        algorithm_id,
                    )
                )
        for entry in self.store.Entries_Get():
            if entry.algorithm_id in algorithm_ids:
                sources.append(
                    AnalysisSource(
                        entry.source_id,
                        entry.kind,
                        entry.algorithm_id,
                        entry.result_id,
                    )
                )
        return tuple(sources)

    def ExplorerChannels_Get(self) -> dict[str, TimeSeries]:
        channels = dict(self.dataset.series)
        for entry in self.store.Entries_Get():
            prefix = entry.StableName_Get()
            for channel_id, series in entry.channels.items():
                channels[f"{prefix} / {channel_id}"] = series
        return channels
