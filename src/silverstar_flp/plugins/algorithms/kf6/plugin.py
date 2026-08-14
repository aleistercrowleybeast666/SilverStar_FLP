from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Any

import numpy as np

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
from silverstar_flp.core.math import (
    Quaternion_Normalize,
    Quaternion_PropagateBodyIncrement,
    Quaternion_RotateVector,
)
from silverstar_flp.plugins.algorithms.kf6.filter import (
    Kf6Filter,
    Kf6GnssEpoch,
    Kf6GnssGroup,
    Kf6UpdateResult,
)
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement,
    InertialIncrement_BuildFromCorrectedImu,
    InertialIncrement_ReadRecorded,
    Mechanization_ConfigurationGet,
)
from silverstar_flp.plugins.algorithms.pure_ins.plugin import (
    CURRENT_BUILD_ID,
    SOURCE_CORRECTED_IMU,
    SOURCE_RECORDED_INCREMENT,
)
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmAvailability,
    AlgorithmMetadata,
    AlgorithmPlugin,
    AlgorithmResult,
    ParameterSpec,
    ReplayFidelity,
    ReplayMode,
    ReplayRequest,
)


@dataclass(frozen=True, slots=True)
class _ScheduledMeasurement:
    application_timestamp_us: int
    source_order: int
    kind: str
    record: DecodedRecord
    inferred: bool


@dataclass(frozen=True, slots=True)
class _ReplaySnapshot:
    timestamp_us: int
    q_nb: np.ndarray
    state: np.ndarray
    covariance: np.ndarray
    position_innovation: np.ndarray
    velocity_innovation: np.ndarray
    baro_innovation: float
    position_nis: float
    velocity_nis: float
    baro_nis: float
    position_result: int
    velocity_result: int
    baro_result: int
    attempt_mask: int
    r_scale: np.ndarray


def _Series_Create(
    timestamps: np.ndarray,
    values: np.ndarray,
    *,
    unit: str,
    quantity: str,
    columns: tuple[str, ...] = (),
) -> TimeSeries:
    return TimeSeries(
        timestamp_us=np.asarray(timestamps, dtype=np.uint64),
        values=np.asarray(values, dtype=np.float64),
        unit=unit,
        quantity=quantity,
        source="silverstar.algorithm.kf6",
        valid=np.ones(len(timestamps), dtype=np.bool_),
        columns=columns,
        metadata={"provenance": "Recomputed"},
    )


def _Result_Aggregate(first: Kf6UpdateResult, second: Kf6UpdateResult) -> int:
    for preferred in (
        Kf6UpdateResult.ACCEPTED,
        Kf6UpdateResult.SOFT_WEIGHTED,
        Kf6UpdateResult.REJECTED_NIS,
        Kf6UpdateResult.REJECTED_INVALID,
        Kf6UpdateResult.NUMERIC_ERROR,
    ):
        if preferred in (first, second):
            return int(preferred)
    return int(Kf6UpdateResult.NUMERIC_ERROR)


class Kf6AlgorithmPlugin(AlgorithmPlugin):
    metadata = AlgorithmMetadata(
        plugin_id="silverstar.algorithm.kf6",
        version="0.1.0-firmware-SILV0008",
        display_name="KF6",
        description="Firmware-order 6-state [pE,pN,pU,vE,vN,vU] navigation filter",
        required_records=("INITIAL_STATE", "SYSTEM_CONFIG"),
        optional_records=(
            "GNSS_MEASUREMENT",
            "BARO_MEASUREMENT",
            "KF6_STATE",
            "KF6_DIAGNOSTIC",
            "KF6_FULL_P",
        ),
        required_channels=(),
        optional_channels=("kf6.recorded.navigation.position_enu",),
        parameter_schema=(
            ParameterSpec("gravity_mps2", "float", 9.78, 1.0, 20.0, "m/s^2"),
            ParameterSpec("process_accel_std_e", "float", 1.5, 0.001, 100.0, "m/s^2"),
            ParameterSpec("process_accel_std_n", "float", 1.5, 0.001, 100.0, "m/s^2"),
            ParameterSpec("process_accel_std_u", "float", 2.0, 0.001, 100.0, "m/s^2"),
            ParameterSpec("p0_scale", "float", 1.0, 0.001, 1000.0, "1"),
            ParameterSpec("gnss_position_r_scale", "float", 1.0, 0.001, 1000.0, "1"),
            ParameterSpec("gnss_velocity_r_scale", "float", 1.0, 0.001, 1000.0, "1"),
            ParameterSpec("baro_r_scale", "float", 1.0, 0.001, 1000.0, "1"),
            ParameterSpec("nis_1d_soft", "float", 6.635, 0.001, 10000.0, "1"),
            ParameterSpec("nis_1d_hard", "float", 10.828, 0.001, 10000.0, "1"),
            ParameterSpec("nis_2d_soft", "float", 9.210, 0.001, 10000.0, "1"),
            ParameterSpec("nis_2d_hard", "float", 13.816, 0.001, 10000.0, "1"),
            ParameterSpec("nis_3d_soft", "float", 11.345, 0.001, 10000.0, "1"),
            ParameterSpec("nis_3d_hard", "float", 16.266, 0.001, 10000.0, "1"),
            ParameterSpec("nis_max_r_scale", "float", 10.0, 1.0, 1000.0, "1"),
        ),
        standard_outputs=(
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
        ),
        diagnostic_outputs=(
            "kf6.state",
            "kf6.covariance.diagonal",
            "kf6.covariance.upper_triangle",
            "kf6.innovation.position",
            "kf6.innovation.velocity",
            "kf6.innovation.baro",
            "kf6.nis.position",
            "kf6.nis.velocity",
            "kf6.nis.baro",
            "kf6.update_result",
        ),
    )

    def availability(
        self, dataset: FlightDataset, input_source: str | None = None
    ) -> AlgorithmAvailability:
        source = input_source or SOURCE_RECORDED_INCREMENT
        missing: list[str] = []
        warnings: list[str] = []
        supported: list[str] = []
        config = Mechanization_ConfigurationGet(dataset)
        if dataset.Records_Get("INERTIAL_INCREMENT"):
            supported.append(SOURCE_RECORDED_INCREMENT)
        if dataset.Records_Get("IMU_CORRECTED"):
            supported.append(SOURCE_CORRECTED_IMU)
        if not dataset.Records_Get("INITIAL_STATE"):
            missing.append("INITIAL_STATE")
        if not dataset.Records_Get("SYSTEM_CONFIG"):
            missing.append("SYSTEM_CONFIG")
        if source == SOURCE_RECORDED_INCREMENT:
            if not dataset.Records_Get("INERTIAL_INCREMENT"):
                missing.append("INERTIAL_INCREMENT")
            if config["inertial_increment_decimation"] not in (None, 1):
                missing.append("INERTIAL_INCREMENT(decimation=1)")
        elif source == SOURCE_CORRECTED_IMU:
            if not dataset.Records_Get("IMU_CORRECTED"):
                missing.append("IMU_CORRECTED")
            if config["imu_corrected_decimation"] not in (None, 1):
                missing.append("IMU_CORRECTED(decimation=1)")
        else:
            missing.append(f"unsupported_input_source:{source}")
        if config["subsample_count"] != 2:
            missing.append("mechanization_subsample_count=2")
        if missing:
            return AlgorithmAvailability(
                False,
                ReplayFidelity.UNAVAILABLE,
                tuple(missing),
                tuple(warnings),
                tuple(supported),
            )
        fidelity = ReplayFidelity.EXACT
        if str(dataset.header.get("build_id", "")) != CURRENT_BUILD_ID:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("firmware_build_differs_from_reimplementation")
        if dataset.diagnostics.record_crc_failures or dataset.diagnostics.sequence_gap_count:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("source_log_has_integrity_or_sequence_gaps")
        return AlgorithmAvailability(True, fidelity, (), tuple(warnings), tuple(supported))

    def run(
        self,
        dataset: FlightDataset,
        request: ReplayRequest,
        context: TaskContext | None = None,
    ) -> AlgorithmResult:
        task_context = context or TaskContext()
        availability = self.availability(dataset, request.input_source)
        if not availability.available:
            raise ValueError("replay_unavailable:" + ",".join(availability.missing_inputs))
        initial = dataset.Records_Get("INITIAL_STATE")[0]
        system_config = dataset.Records_Get("SYSTEM_CONFIG")[0]
        start_timestamp = dataset.start_timestamp_us or initial.timestamp_us
        mechanism_config = Mechanization_ConfigurationGet(dataset)
        if request.input_source == SOURCE_CORRECTED_IMU:
            increments, build_diagnostics = InertialIncrement_BuildFromCorrectedImu(
                dataset.Records_Get("IMU_CORRECTED"),
                start_timestamp_us=start_timestamp,
                minimum_sample_rate_hz=mechanism_config["minimum_sample_rate_hz"],
                maximum_sample_rate_hz=mechanism_config["maximum_sample_rate_hz"],
            )
            source_diagnostics: dict[str, Any] = {
                "invalid_sample_count": build_diagnostics.invalid_sample_count,
                "sample_gap_count": build_diagnostics.sample_gap_count,
            }
        else:
            increments = InertialIncrement_ReadRecorded(
                dataset.Records_Get("INERTIAL_INCREMENT"),
                start_timestamp_us=start_timestamp,
            )
            source_diagnostics = {}
        if not increments:
            raise ValueError("replay_no_valid_inertial_increment")
        parameters = self._Parameters_Resolve(dataset, request)
        filter_instance = Kf6Filter.Kf6_Create(
            process_accel_std_mps2=np.asarray(
                (
                    parameters["process_accel_std_e"],
                    parameters["process_accel_std_n"],
                    parameters["process_accel_std_u"],
                ),
                dtype=np.float32,
            ),
            p0_diagonal=np.asarray(initial.payload["p0_diagonal"], dtype=np.float32)
            * np.float32(parameters["p0_scale"]),
            initial_velocity_enu_mps=np.asarray(
                initial.payload["initial_velocity_enu_mps"], dtype=np.float32
            ),
            nis_soft_threshold=np.asarray(
                (
                    parameters["nis_1d_soft"],
                    parameters["nis_2d_soft"],
                    parameters["nis_3d_soft"],
                ),
                dtype=np.float32,
            ),
            nis_hard_threshold=np.asarray(
                (
                    parameters["nis_1d_hard"],
                    parameters["nis_2d_hard"],
                    parameters["nis_3d_hard"],
                ),
                dtype=np.float32,
            ),
            nis_max_r_scale=parameters["nis_max_r_scale"],
        )
        q_nb = Quaternion_Normalize(np.asarray(initial.payload["q_nb"], dtype=np.float32))
        schedule, schedule_inferred = self._MeasurementSchedule_Build(dataset, increments)
        task_context.Progress_Report(0.08, "replay.inputs")
        snapshots = self._Replay_Run(
            filter_instance,
            q_nb,
            increments,
            schedule,
            parameters,
            task_context,
        )
        if not snapshots:
            raise ValueError("replay_no_valid_kf6_output")
        warnings = list(availability.warnings)
        fidelity = availability.fidelity
        state_decimation = tuple(system_config.payload.get("log_decimation", ()))
        if schedule_inferred:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("measurement_application_time_inferred")
        elif len(state_decimation) > 7 and int(state_decimation[7]) != 1 and schedule:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("kf6_state_timing_reference_is_decimated")
        channels = self._Channels_Build(snapshots)
        task_context.Progress_Report(1.0, "replay.complete")
        return AlgorithmResult(
            algorithm_id=self.metadata.plugin_id,
            algorithm_version=self.metadata.version,
            input_source=request.input_source,
            parameters=parameters,
            fidelity=fidelity,
            missing_inputs=(),
            warnings=tuple(dict.fromkeys(warnings)),
            channels=channels,
            diagnostics={
                "state_order": ("pE", "pN", "pU", "vE", "vN", "vU"),
                "input_increment_count": len(increments),
                "measurement_count": len(schedule),
                "output_count": len(snapshots),
                "predict_count": filter_instance.predict_count,
                "health_flags": filter_instance.health_flags,
                "reacquire_count": filter_instance.reacquire_count,
                "reacquire_active_mask": filter_instance.reacquire_active_mask,
                "last_inflation_group": filter_instance.last_inflation_group,
                "last_inflation_factor": filter_instance.last_inflation_factor,
                **filter_instance.counters,
                **source_diagnostics,
            },
            provenance=("What-if" if request.mode == ReplayMode.WHAT_IF else "Recomputed"),
        )

    @staticmethod
    def _Parameters_Resolve(dataset: FlightDataset, request: ReplayRequest) -> dict[str, float]:
        config = dataset.Records_Get("SYSTEM_CONFIG")[0].payload
        process = tuple(float(value) for value in config["process_accel_std_mps2"])
        nis = tuple(float(value) for value in config["nis_profile"])
        parameters = {
            "gravity_mps2": float(dataset.header["gravity_mps2"]),
            "process_accel_std_e": process[0],
            "process_accel_std_n": process[1],
            "process_accel_std_u": process[2],
            "p0_scale": 1.0,
            "gnss_position_r_scale": 1.0,
            "gnss_velocity_r_scale": 1.0,
            "baro_r_scale": 1.0,
            "nis_1d_soft": nis[0],
            "nis_1d_hard": nis[1],
            "nis_2d_soft": nis[2],
            "nis_2d_hard": nis[3],
            "nis_3d_soft": nis[4],
            "nis_3d_hard": nis[5],
            "nis_max_r_scale": nis[6],
        }
        if request.mode == ReplayMode.WHAT_IF:
            for key, value in request.parameters.items():
                if key in parameters:
                    parameters[key] = float(value)
        positive = (
            "gravity_mps2",
            "process_accel_std_e",
            "process_accel_std_n",
            "process_accel_std_u",
            "p0_scale",
            "gnss_position_r_scale",
            "gnss_velocity_r_scale",
            "baro_r_scale",
            "nis_1d_soft",
            "nis_1d_hard",
            "nis_2d_soft",
            "nis_2d_hard",
            "nis_3d_soft",
            "nis_3d_hard",
            "nis_max_r_scale",
        )
        if any(not np.isfinite(parameters[key]) or parameters[key] <= 0.0 for key in positive):
            raise ValueError("what_if_parameter_invalid")
        for dimension in ("1d", "2d", "3d"):
            if parameters[f"nis_{dimension}_hard"] <= parameters[f"nis_{dimension}_soft"]:
                raise ValueError("nis_threshold_order_invalid")
        if parameters["nis_max_r_scale"] < 1.0:
            raise ValueError("nis_max_r_scale_invalid")
        return parameters

    @staticmethod
    def _MeasurementSchedule_Build(
        dataset: FlightDataset, increments: tuple[InertialIncrement, ...]
    ) -> tuple[tuple[_ScheduledMeasurement, ...], bool]:
        increment_timestamps = [item.interval_end_timestamp_us for item in increments]
        states = dataset.Records_Get("KF6_STATE")
        gnss_application: dict[int, int] = {}
        baro_application: dict[int, int] = {}
        for state in sorted(states, key=lambda item: item.record_sequence):
            payload = state.payload
            gnss_sequence = int(payload.get("gnss_sequence", 0))
            baro_sequence = int(payload.get("baro_sequence", 0))
            if gnss_sequence and gnss_sequence not in gnss_application:
                gnss_application[gnss_sequence] = state.timestamp_us
            if baro_sequence and baro_sequence not in baro_application:
                baro_application[baro_sequence] = state.timestamp_us
        scheduled: list[_ScheduledMeasurement] = []
        inferred_any = False
        for kind, records, applications in (
            ("gnss", dataset.Records_Get("GNSS_MEASUREMENT"), gnss_application),
            ("baro", dataset.Records_Get("BARO_MEASUREMENT"), baro_application),
        ):
            for record in records:
                sequence = int(record.payload["sequence"])
                application_timestamp = applications.get(sequence)
                inferred = application_timestamp is None
                if application_timestamp is None:
                    sample_timestamp = int(record.payload["sample_timestamp_us"])
                    index = bisect_left(increment_timestamps, sample_timestamp)
                    if index >= len(increment_timestamps):
                        continue
                    application_timestamp = increment_timestamps[index]
                    inferred_any = True
                scheduled.append(
                    _ScheduledMeasurement(
                        application_timestamp_us=int(application_timestamp),
                        source_order=record.record_sequence,
                        kind=kind,
                        record=record,
                        inferred=inferred,
                    )
                )
        scheduled.sort(
            key=lambda item: (
                item.application_timestamp_us,
                0 if item.kind == "gnss" else 1,
                item.source_order,
            )
        )
        return tuple(scheduled), inferred_any

    def _Replay_Run(
        self,
        filter_instance: Kf6Filter,
        initial_q_nb: np.ndarray,
        increments: tuple[InertialIncrement, ...],
        schedule: tuple[_ScheduledMeasurement, ...],
        parameters: dict[str, float],
        context: TaskContext,
    ) -> tuple[_ReplaySnapshot, ...]:
        q_nb = initial_q_nb.copy()
        measurement_index = 0
        snapshots: list[_ReplaySnapshot] = []
        for increment_index, increment in enumerate(increments):
            context.Cancel_RaiseIfRequested()
            dt = np.float32(increment.dt_s)
            rotated = Quaternion_RotateVector(q_nb, increment.delta_velocity_b)
            delta_velocity_enu = rotated.copy()
            delta_velocity_enu[2] -= np.float32(parameters["gravity_mps2"]) * dt
            q_nb = Quaternion_PropagateBodyIncrement(q_nb, increment.delta_theta_b)
            if not filter_instance.Kf6_Predict(delta_velocity_enu, float(dt)):
                continue
            position_result = int(Kf6UpdateResult.REJECTED_INVALID)
            velocity_result = int(Kf6UpdateResult.REJECTED_INVALID)
            baro_result = int(Kf6UpdateResult.REJECTED_INVALID)
            attempt_mask = 0
            r_scale = np.ones(3, dtype=np.float32)
            while (
                measurement_index < len(schedule)
                and schedule[measurement_index].application_timestamp_us
                <= increment.interval_end_timestamp_us
            ):
                measurement = schedule[measurement_index]
                measurement_index += 1
                if measurement.kind == "gnss":
                    result = self._Gnss_Apply(
                        filter_instance,
                        measurement.record,
                        parameters["gnss_position_r_scale"],
                        parameters["gnss_velocity_r_scale"],
                    )
                    position_result, velocity_result, mask, scales = result
                    attempt_mask |= mask
                    r_scale[0:2] = scales
                else:
                    result, scale, mask = self._Baro_Apply(
                        filter_instance,
                        measurement.record,
                        parameters["baro_r_scale"],
                    )
                    baro_result = result
                    r_scale[2] = scale
                    attempt_mask |= mask
            snapshots.append(
                _ReplaySnapshot(
                    timestamp_us=increment.interval_end_timestamp_us,
                    q_nb=q_nb.copy(),
                    state=filter_instance.state.copy(),
                    covariance=filter_instance.covariance.copy(),
                    position_innovation=filter_instance.last_position_innovation.copy(),
                    velocity_innovation=filter_instance.last_velocity_innovation.copy(),
                    baro_innovation=float(filter_instance.last_baro_innovation),
                    position_nis=float(filter_instance.last_position_nis),
                    velocity_nis=float(filter_instance.last_velocity_nis),
                    baro_nis=float(filter_instance.last_baro_nis),
                    position_result=position_result,
                    velocity_result=velocity_result,
                    baro_result=baro_result,
                    attempt_mask=attempt_mask,
                    r_scale=r_scale,
                )
            )
            if increment_index % 256 == 0:
                context.Progress_Report(
                    0.1 + 0.82 * increment_index / max(len(increments), 1),
                    "replay.kf6",
                )
        return tuple(snapshots)

    @staticmethod
    def _Gnss_Apply(
        filter_instance: Kf6Filter,
        record: DecodedRecord,
        position_r_scale: float,
        velocity_r_scale: float,
    ) -> tuple[int, int, int, np.ndarray]:
        payload = record.payload
        mask = int(record.valid_flags) & 0x03
        if not bool(payload.get("fusion_allowed", 0)):
            return 3, 3, 0, np.ones(2, dtype=np.float32)
        position = np.asarray(payload["position_enu_m"], dtype=np.float32)
        velocity = np.asarray(payload["velocity_enu_mps"], dtype=np.float32)
        position_variance = np.asarray(payload["position_variance_m2"], dtype=np.float32)
        velocity_variance = np.asarray(payload["velocity_variance_m2ps2"], dtype=np.float32)
        velocity_mask = int(payload["velocity_valid_mask"])
        epoch_mask = 0
        if mask & 0x01:
            epoch_mask |= (1 << int(Kf6GnssGroup.POSITION_HORIZONTAL)) | (
                1 << int(Kf6GnssGroup.POSITION_VERTICAL)
            )
        if mask & 0x02 and (velocity_mask & 0x03) == 0x03:
            epoch_mask |= 1 << int(Kf6GnssGroup.VELOCITY_HORIZONTAL)
            if velocity_mask & 0x04:
                epoch_mask |= 1 << int(Kf6GnssGroup.VELOCITY_VERTICAL)
        if epoch_mask:
            filter_instance.Kf6_GnssEpochTrack(
                Kf6GnssEpoch(
                    timestamp_us=int(payload["sample_timestamp_us"]),
                    position_enu_m=position,
                    velocity_enu_mps=velocity,
                    position_std_m=np.sqrt(np.maximum(position_variance, 0.0)).astype(np.float32),
                    velocity_std_mps=np.sqrt(np.maximum(velocity_variance, 0.0)).astype(np.float32),
                    valid_group_mask=epoch_mask,
                )
            )
        position_result = int(Kf6UpdateResult.REJECTED_INVALID)
        velocity_result = int(Kf6UpdateResult.REJECTED_INVALID)
        position_scale_applied = np.float32(1.0)
        velocity_scale_applied = np.float32(1.0)
        if mask & 0x01:
            base = position_variance * np.float32(position_r_scale)
            separated = filter_instance.Kf6_UpdateGnssPosition(position, base)
            position_result = _Result_Aggregate(
                separated.horizontal_result, separated.vertical_result
            )
            filter_instance.Kf6_GnssGroupResultProcess(
                Kf6GnssGroup.POSITION_HORIZONTAL, separated.horizontal_result
            )
            filter_instance.Kf6_GnssGroupResultProcess(
                Kf6GnssGroup.POSITION_VERTICAL, separated.vertical_result
            )
            ratios = np.divide(
                filter_instance.last_position_effective_variance,
                base,
                out=np.ones(3, dtype=np.float32),
                where=base > 0.0,
            )
            position_scale_applied = np.max(ratios)
        if mask & 0x02 and (velocity_mask & 0x03) == 0x03:
            base = velocity_variance * np.float32(velocity_r_scale)
            separated = filter_instance.Kf6_UpdateGnssVelocity(
                velocity, base, vertical_valid=bool(velocity_mask & 0x04)
            )
            velocity_result = (
                _Result_Aggregate(separated.horizontal_result, separated.vertical_result)
                if separated.vertical_attempted
                else int(separated.horizontal_result)
            )
            filter_instance.Kf6_GnssGroupResultProcess(
                Kf6GnssGroup.VELOCITY_HORIZONTAL, separated.horizontal_result
            )
            if separated.vertical_attempted:
                filter_instance.Kf6_GnssGroupResultProcess(
                    Kf6GnssGroup.VELOCITY_VERTICAL, separated.vertical_result
                )
            ratios = np.divide(
                filter_instance.last_velocity_effective_variance,
                base,
                out=np.ones(3, dtype=np.float32),
                where=base > 0.0,
            )
            velocity_scale_applied = np.max(ratios[: 3 if velocity_mask & 0x04 else 2])
        return (
            position_result,
            velocity_result,
            mask,
            np.asarray((position_scale_applied, velocity_scale_applied), dtype=np.float32),
        )

    @staticmethod
    def _Baro_Apply(
        filter_instance: Kf6Filter, record: DecodedRecord, r_scale: float
    ) -> tuple[int, float, int]:
        if (int(record.valid_flags) & 0x04) == 0 or not int(record.payload.get("valid_mask", 0)):
            return int(Kf6UpdateResult.REJECTED_INVALID), 1.0, 0
        base_variance = float(record.payload["variance_m2"]) * r_scale
        result = filter_instance.Kf6_UpdateBaro(
            float(record.payload["relative_altitude_m"]), base_variance
        )
        scale = (
            float(filter_instance.last_baro_effective_variance) / base_variance
            if base_variance > 0.0
            else 1.0
        )
        return int(result), scale, 0x04

    @staticmethod
    def _Channels_Build(snapshots: tuple[_ReplaySnapshot, ...]) -> dict[str, TimeSeries]:
        timestamps = np.asarray([item.timestamp_us for item in snapshots], dtype=np.uint64)
        state = np.asarray([item.state for item in snapshots])
        covariance = np.asarray([item.covariance for item in snapshots])
        diagonal = np.asarray([np.diag(item) for item in covariance])
        upper = np.asarray(
            [
                [matrix[row, column] for row in range(6) for column in range(row, 6)]
                for matrix in covariance
            ]
        )
        channels = {
            "attitude.q_nb": _Series_Create(
                timestamps,
                np.asarray([item.q_nb for item in snapshots]),
                unit="1",
                quantity="quaternion",
                columns=("W", "X", "Y", "Z"),
            ),
            "navigation.position_enu": _Series_Create(
                timestamps, state[:, 0:3], unit="m", quantity="position", columns=("E", "N", "U")
            ),
            "navigation.velocity_enu": _Series_Create(
                timestamps, state[:, 3:6], unit="m/s", quantity="velocity", columns=("E", "N", "U")
            ),
            "kf6.state": _Series_Create(
                timestamps,
                state,
                unit="mixed",
                quantity="state",
                columns=("pE", "pN", "pU", "vE", "vN", "vU"),
            ),
            "kf6.covariance.diagonal": _Series_Create(
                timestamps,
                diagonal,
                unit="mixed",
                quantity="covariance",
                columns=("PpE", "PpN", "PpU", "PvE", "PvN", "PvU"),
            ),
            "kf6.covariance.upper_triangle": _Series_Create(
                timestamps,
                upper,
                unit="mixed",
                quantity="covariance",
                columns=tuple(f"P{row}{column}" for row in range(6) for column in range(row, 6)),
            ),
            "kf6.innovation.position": _Series_Create(
                timestamps,
                np.asarray([item.position_innovation for item in snapshots]),
                unit="m",
                quantity="innovation",
                columns=("E", "N", "U"),
            ),
            "kf6.innovation.velocity": _Series_Create(
                timestamps,
                np.asarray([item.velocity_innovation for item in snapshots]),
                unit="m/s",
                quantity="innovation",
                columns=("E", "N", "U"),
            ),
            "kf6.innovation.baro": _Series_Create(
                timestamps,
                np.asarray([item.baro_innovation for item in snapshots]),
                unit="m",
                quantity="innovation",
            ),
            "kf6.nis.position": _Series_Create(
                timestamps,
                np.asarray([item.position_nis for item in snapshots]),
                unit="1",
                quantity="nis",
            ),
            "kf6.nis.velocity": _Series_Create(
                timestamps,
                np.asarray([item.velocity_nis for item in snapshots]),
                unit="1",
                quantity="nis",
            ),
            "kf6.nis.baro": _Series_Create(
                timestamps,
                np.asarray([item.baro_nis for item in snapshots]),
                unit="1",
                quantity="nis",
            ),
            "kf6.update_result": _Series_Create(
                timestamps,
                np.asarray(
                    [
                        (item.position_result, item.velocity_result, item.baro_result)
                        for item in snapshots
                    ]
                ),
                unit="enum",
                quantity="update_result",
                columns=("GNSS position", "GNSS velocity", "Barometer"),
            ),
            "kf6.measurement_attempt_mask": _Series_Create(
                timestamps,
                np.asarray([item.attempt_mask for item in snapshots]),
                unit="bitmask",
                quantity="status",
            ),
            "kf6.measurement_r_scale": _Series_Create(
                timestamps,
                np.asarray([item.r_scale for item in snapshots]),
                unit="1",
                quantity="scale",
                columns=("GNSS position", "GNSS velocity", "Barometer"),
            ),
        }
        return channels
