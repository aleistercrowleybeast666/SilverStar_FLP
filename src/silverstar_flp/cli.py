from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.export.service import (
    ExportLanguage,
    ExportOptions,
    ExportTheme,
    FlightExporter,
)
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry


def _Json_Default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.hex(" ")
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(type(value).__name__)


def _Dataset_Parse(path: Path):
    registry = builtin_registry()
    parser = registry.LogParser_Probe(path)
    if parser is None:
        raise ValueError("unsupported_log_container")
    return registry, parser.parse(path)


def _Command_Inspect(options: argparse.Namespace) -> int:
    _, dataset = _Dataset_Parse(options.path)
    payload = {
        "source_path": dataset.source_path,
        "file_size": dataset.file_size,
        "header": dict(dataset.header),
        "diagnostics": dataset.diagnostics.to_dict(),
        "record_counts": {name: len(records) for name, records in dataset.records.items()},
        "channels": {
            name: {
                "samples": series.count,
                "unit": series.unit,
                "quantity": series.quantity,
                "source": series.source,
            }
            for name, series in dataset.series.items()
        },
        "overview": FlightSummary_Build(dataset),
    }
    print(json.dumps(payload, default=_Json_Default, ensure_ascii=False, indent=2))
    return 0


def _Command_Replay(options: argparse.Namespace) -> int:
    registry, dataset = _Dataset_Parse(options.path)
    algorithm_id = (
        "silverstar.algorithm.pure_ins"
        if options.algorithm == "pure_ins"
        else "silverstar.algorithm.kf6"
    )
    plugin = registry.Algorithm_Get(algorithm_id)
    parameters: dict[str, float] = {}
    for assignment in options.parameter:
        key, separator, value = assignment.partition("=")
        if not separator:
            raise ValueError(f"invalid_parameter_assignment:{assignment}")
        parameters[key] = float(value)
    mode = ReplayMode.WHAT_IF if parameters else ReplayMode.RECORDED_CONFIGURATION
    result = plugin.run(
        dataset,
        ReplayRequest(mode=mode, input_source=options.source, parameters=parameters),
    )
    payload = {
        "algorithm_id": result.algorithm_id,
        "algorithm_version": result.algorithm_version,
        "provenance": result.provenance,
        "fidelity": result.fidelity,
        "warnings": result.warnings,
        "parameters": dict(result.parameters),
        "diagnostics": dict(result.diagnostics),
        "channels": {name: series.count for name, series in result.channels.items()},
    }
    print(json.dumps(payload, default=_Json_Default, ensure_ascii=False, indent=2))
    if options.output is not None:
        manifest = FlightExporter().export(
            dataset,
            options.output,
            options=ExportOptions(
                language=ExportLanguage(options.language),
                theme=ExportTheme(options.theme),
            ),
            algorithm_results={options.algorithm: result},
        )
        print(f"exported={len(manifest.files)} directory={manifest.output_directory}")
    return 0


def _Command_Export(options: argparse.Namespace) -> int:
    _, dataset = _Dataset_Parse(options.path)
    manifest = FlightExporter().export(
        dataset,
        options.output,
        options=ExportOptions(
            language=ExportLanguage(options.language),
            theme=ExportTheme(options.theme),
            include_attitude_gif=not options.no_gif,
        ),
    )
    print(f"exported={len(manifest.files)} directory={manifest.output_directory}")
    return 0


def _Command_Gui(options: argparse.Namespace) -> int:
    from silverstar_flp.app.application import main as gui_main

    arguments = [str(options.path)] if options.path is not None else []
    return gui_main(arguments)


def _Parser_Create() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sslog", description="SilverStar SSLOG0 tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="parse and print log metadata")
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.set_defaults(handler=_Command_Inspect)

    replay_parser = subparsers.add_parser("replay", help="run a navigation replay")
    replay_parser.add_argument("path", type=Path)
    replay_parser.add_argument("--algorithm", choices=("pure_ins", "kf6"), default="pure_ins")
    replay_parser.add_argument(
        "--source",
        choices=("recorded_inertial_increment", "corrected_imu"),
        default="recorded_inertial_increment",
    )
    replay_parser.add_argument("--parameter", action="append", default=[], metavar="KEY=VALUE")
    replay_parser.add_argument("--output", type=Path)
    replay_parser.add_argument("--language", choices=("zh_CN", "en_US"), default="zh_CN")
    replay_parser.add_argument("--theme", choices=("light", "dark"), default="light")
    replay_parser.set_defaults(handler=_Command_Replay)

    export_parser = subparsers.add_parser("export", help="export all available channels")
    export_parser.add_argument("path", type=Path)
    export_parser.add_argument("output", type=Path)
    export_parser.add_argument("--language", choices=("zh_CN", "en_US"), default="zh_CN")
    export_parser.add_argument("--theme", choices=("light", "dark"), default="light")
    export_parser.add_argument("--no-gif", action="store_true")
    export_parser.set_defaults(handler=_Command_Export)

    gui_parser = subparsers.add_parser("gui", help="open the desktop application")
    gui_parser.add_argument("path", nargs="?", type=Path)
    gui_parser.set_defaults(handler=_Command_Gui)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _Parser_Create()
    try:
        options = parser.parse_args(arguments)
        return int(options.handler(options))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
