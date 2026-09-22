"""Read-only four-group and landing inspection. Missing evidence stays unknown."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, Qt, Signal
from PySide6.QtWidgets import QHeaderView, QLabel, QPushButton, QTableView, QVBoxLayout, QWidget

from silverstar_flp.ui.touch_scroll import TouchScroll_Enable


class DiagnosticTableModel(QAbstractTableModel):
    def __init__(self, columns, translator, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.translator = translator
        self.rows = []

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                self.translator.Text_Get("diagnostic." + self.columns[section])
                if orientation == Qt.Orientation.Horizontal
                else section + 1
            )
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            column = self.columns[index.column()]
            value = self.rows[index.row()].get(column)
            kind = getattr(self, 'kind', '')
            prefix = ('result' if column == 'result' else
                      'landing_reason' if column == 'reason' and kind == 'landing' else
                      'reanchor_reason' if column == 'reason' and kind == 'gnss' else
                      'transition' if column == 'transition' else None)
            if value is not None and prefix:
                return self.translator.Text_Get(f'diagnostic.{prefix}.{value}')
            if column == 'quality' and value is not None:
                if value == 0:
                    return self.translator.Text_Get('diagnostic.quality_ok')
                return ' / '.join(self.translator.Text_Get(f'diagnostic.quality_bit.{bit}')
                                  for bit in range(11) if int(value) & (1 << bit))
            if column == 'failure' and value is not None:
                return self.translator.Text_Get('diagnostic.failure.' + value)
            if column == 'source' and value in ('Recorded', 'Recomputed'):
                return self.translator.Text_Get('diagnostic.source.' + value)
            if isinstance(value, bool):
                return self.translator.Text_Get('diagnostic.yes' if value else 'diagnostic.no')
            if value is None:
                return '—'
            if isinstance(value, float):
                return f'{value:.6g}'
            return str(value)
        return None

    def Rows_Set(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()


class NavigationDiagnostics(QWidget):
    recomputeRequested = Signal()
    def __init__(self, kind, translator, parent=None):
        super().__init__(parent)
        self.kind, self.translator = kind, translator
        self._rows = []
        self._origin = 0
        self._interval = (0, float('inf'))
        columns = {
            "gnss": (
                "time",
                "source",
                "group",
                "valid",
                "failure",
                "quality",
                "result",
                "innovation",
                "nis",
                "variance",
                "outage",
                "consistency",
                "inflation",
                "factor",
                "reanchor",
                "reason",
            ),
            "landing": (
                "time",
                "source",
                "transition",
                "reason",
                "elapsed",
                "coverage",
                "still",
                "bad",
                "slope",
                "span",
                "baro_coverage",
            ),
            "mechanization": (
                "time",
                "source_sequence",
                "recorded_sequence",
                "dt",
                "start_difference",
                "end_difference",
                "theta",
                "dv",
                "passed",
            ),
        }[kind]
        layout = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        if kind == "landing":
            self.recompute_button = QPushButton(translator.Text_Get("diagnostic.recompute_landing"))
            self.recompute_button.clicked.connect(self.recomputeRequested)
            layout.addWidget(self.recompute_button)
        self.table = QTableView()
        self.model = DiagnosticTableModel(columns, translator, self.table)
        self.model.kind = kind
        self.table.setModel(self.model)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        TouchScroll_Enable(self.table)
        layout.addWidget(self.table)

    def Dataset_Set(self, dataset, resolver):
        self._dataset, self._resolver = dataset, resolver
        self._origin = dataset.start_timestamp_us or 0
        self._rows = []
        entry = resolver.store.SourceEntry_Get(resolver.store.ActiveSource_Get().source_id)
        if self.kind == 'gnss':
            if entry:
                self._rows = list(entry.diagnostics.get('gnss_group_updates', ()))
            else:
                recovery = {(r.payload['replay_epoch'], r.payload['source_sequence']): r.payload
                            for r in dataset.Records_Get('GNSS_RECOVERY')}
                for record in dataset.Records_Get('GNSS_MEASUREMENT'):
                    p = record.payload
                    if 'group_update_result' not in p:
                        continue
                    evidence = recovery.get((p['replay_epoch'], p['sequence']), {})
                    for group, name in enumerate(('Pos EN', 'Pos U', 'Vel EN', 'Vel U')):
                        axes = (0, 1) if group % 2 == 0 else (2,)
                        innovation = p[
                            "position_innovation_m" if group < 2 else "velocity_innovation_mps"
                        ]
                        variance = p[
                            "position_variance_m2" if group < 2 else "velocity_variance_m2ps2"
                        ]
                        row = dict(
                            timestamp_us=p["estimator_present_timestamp_us"],
                            source="Recorded",
                            group=name,
                            valid=bool(p["valid_group_mask"] & (1 << group)),
                            result=p["group_update_result"][group],
                            nis=p["group_nis"][group],
                            innovation=tuple(innovation[a] for a in axes),
                            variance=tuple(variance[a] for a in axes),
                        )
                        for column, field in (('quality','quality_reject_mask'),('outage','outage'),
                                              ('consistency','consistency_count'),('inflation','inflation_attempt_count'),
                                              ('factor','inflation_factor'),('reanchor','reanchor_count'),('reason','reanchor_reason')):
                            row[column] = evidence[field][group] if field in evidence else None
                        self._rows.append(row)
            for row in self._rows:
                quality = row.get('quality')
                row['failure'] = ('liveness' if quality is not None and int(quality) & 257 else
                                  'quality' if quality else
                                  'estimator' if row.get('valid') and row.get('result') == 2 else
                                  'none' if row.get('valid') else 'unknown')
            self.note.setText(self.translator.Text_Get('diagnostic.gnss_note'))
        elif self.kind == 'landing':
            records = [(r.payload, 'Recorded') for r in dataset.Records_Get('LANDING_DIAGNOSTIC')]
            recomputed = getattr(self, '_recomputed', None)
            if recomputed and self._recomputed_dataset is dataset:
                records.extend((row, 'Recomputed · APPROXIMATE') for row in recomputed)
            for p, source in records:
                self._rows.append(
                    dict(
                        timestamp_us=p["evaluation_timestamp_us"],
                        source=source,
                        transition=p["transition"],
                        reason=p["reset_reason"],
                        elapsed=p["candidate_elapsed_us"] * 1e-6,
                        coverage=p["valid_coverage"],
                        still=p["still_ratio"],
                        bad=p["maximum_bad_duration_us"] * 1e-3,
                        slope=p["baro_slope_mps"],
                        span=p["baro_span_m"],
                        baro_coverage=p["baro_coverage"],
                    )
                )
            self.note.setText(self.translator.Text_Get('diagnostic.landing_note'))
        elif entry:
            report = entry.diagnostics.get('mechanization_verification', {})
            self.note.setText(self.translator.Text_Get('diagnostic.mechanization_note') + '\n' +
                             str(report.get('first_divergence', '—')))
            for p in report.get('intervals', ()):
                self._rows.append(
                    dict(
                        timestamp_us=p["timestamp_us"],
                        source_sequence=p.get("source_sequence"),
                        recorded_sequence=p["sequence"],
                        dt=p.get("dt_difference_s"),
                        start_difference=p.get("start_timestamp_difference_us"),
                        end_difference=p.get("end_timestamp_difference_us"),
                        theta=p.get("delta_theta_difference"),
                        dv=p.get("delta_velocity_difference"),
                        passed=p["passed"],
                    )
                )
        else:
            self.note.setText(self.translator.Text_Get('diagnostic.mechanization_note'))
        self.TimeRange_Set(*self._interval)

    def Recomputed_Set(self, dataset, transitions):
        self._recomputed_dataset = dataset
        self._recomputed = transitions

    def TimeRange_Set(self, start, end):
        self._interval = start, end
        self.model.Rows_Set(dict(row, time=(row['timestamp_us']-self._origin)*1e-6)
            for row in self._rows if start <= (row['timestamp_us']-self._origin)*1e-6 <= end)
