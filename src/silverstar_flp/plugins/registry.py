from __future__ import annotations

from dataclasses import dataclass, field

from silverstar_flp.plugins.api.algorithm import AlgorithmPlugin
from silverstar_flp.plugins.api.log_parser import LogParserPlugin


@dataclass(slots=True)
class PluginRegistry:
    _log_parsers: dict[str, LogParserPlugin] = field(default_factory=dict)
    _algorithms: dict[str, AlgorithmPlugin] = field(default_factory=dict)

    def LogParser_Register(self, plugin: LogParserPlugin) -> None:
        plugin_id = plugin.metadata.plugin_id
        if plugin_id in self._log_parsers:
            raise ValueError(f"duplicate_log_parser:{plugin_id}")
        self._log_parsers[plugin_id] = plugin

    def Algorithm_Register(self, plugin: AlgorithmPlugin) -> None:
        plugin_id = plugin.metadata.plugin_id
        if plugin_id in self._algorithms:
            raise ValueError(f"duplicate_algorithm:{plugin_id}")
        self._algorithms[plugin_id] = plugin

    @property
    def log_parsers(self) -> tuple[LogParserPlugin, ...]:
        return tuple(self._log_parsers.values())

    @property
    def algorithms(self) -> tuple[AlgorithmPlugin, ...]:
        return tuple(self._algorithms.values())

    def LogParser_Get(self, plugin_id: str) -> LogParserPlugin:
        return self._log_parsers[plugin_id]

    def Algorithm_Get(self, plugin_id: str) -> AlgorithmPlugin:
        return self._algorithms[plugin_id]

    def LogParser_Probe(self, path) -> LogParserPlugin | None:
        ranked = sorted(
            ((plugin.probe(path), plugin) for plugin in self.log_parsers),
            key=lambda item: item[0],
            reverse=True,
        )
        return ranked[0][1] if ranked and ranked[0][0] > 0.0 else None


def builtin_registry() -> PluginRegistry:
    from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
    from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
    from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin

    registry = PluginRegistry()
    registry.LogParser_Register(Sslog0ParserPlugin())
    registry.Algorithm_Register(PureInsAlgorithmPlugin())
    registry.Algorithm_Register(Kf6AlgorithmPlugin())
    return registry
