from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QDoubleSpinBox, QGridLayout, QLabel, QVBoxLayout, QWidget

from silverstar_flp.core.time_range import PRESET_SECONDS, TimeRangeController
from silverstar_flp.ui.widgets import StandardComboBox


class RangeSlider(QWidget):
    rangeChanged = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start, self._end, self._limit = 0.0, 0.0, 0.0
        self._handle = 0
        self.setMinimumHeight(36)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Time range")

    def Range_Set(self, start, end, limit):
        self._start, self._end, self._limit = start, end, limit
        self.update()

    def _Position_Get(self, value):
        return 14 + (self.width() - 28) * value / max(self._limit, 1e-12)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = self.height() // 2
        painter.setPen(QPen(self.palette().mid().color(), 4))
        painter.drawLine(14, y, self.width() - 14, y)
        left, right = round(self._Position_Get(self._start)), round(self._Position_Get(self._end))
        painter.setPen(QPen(self.palette().highlight().color(), 5))
        painter.drawLine(left, y, right, y)
        painter.setBrush(self.palette().highlight())
        for index, x in enumerate((left, right)):
            painter.setPen(
                QPen(
                    self.palette().text().color(),
                    2 if self.hasFocus() and index == self._handle else 1,
                )
            )
            painter.drawEllipse(x - 9, y - 12, 18, 24)

    def mousePressEvent(self, event):
        self.setFocus()
        x = event.position().x()
        self._handle = (
            0
            if abs(x - self._Position_Get(self._start)) < abs(x - self._Position_Get(self._end))
            else 1
        )
        self._Move(x)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._Move(event.position().x())

    def _Move(self, x):
        value = max(0.0, min(self._limit, (x - 14) * self._limit / max(1, self.width() - 28)))
        self.rangeChanged.emit(min(value, self._end) if self._handle == 0 else self._start,
                               max(value, self._start) if self._handle == 1 else self._end)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._handle = 1 - self._handle
            self.update()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = (-1 if event.key() == Qt.Key.Key_Left else 1) * max(.01, self._limit / 1000)
            value = (self._start if self._handle == 0 else self._end) + delta
            self._Move(self._Position_Get(value))
        else:
            super().keyPressEvent(event)


class TimeRangeBar(QWidget):
    rangeChanged = Signal(object)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self.controller = TimeRangeController()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        self.preset = StandardComboBox()
        for value in (*map(str, PRESET_SECONDS), "Full", "Custom"):
            self.preset.addItem(value, value)
        self.start, self.end, self.duration = (QDoubleSpinBox() for _ in range(3))
        self._labels = []
        for index, (key, control) in enumerate(
            zip(
                ("preset", "start", "end", "duration"),
                (self.preset, self.start, self.end, self.duration),
                strict=True,
            )
        ):
            label = QLabel()
            label.setBuddy(control)
            self._labels.append((key, label))
            grid.addWidget(label, 0, index)
            grid.addWidget(control, 1, index)
            if isinstance(control, QDoubleSpinBox):
                control.setDecimals(3)
                control.setSuffix(" s")
                control.setKeyboardTracking(False)
                control.setMinimumWidth(85)
        layout.addLayout(grid)
        self.slider = RangeSlider()
        layout.addWidget(self.slider)
        self.slider.rangeChanged.connect(
            lambda start, end: self._Changed(self.controller.Range_Set(start, end))
        )
        self.preset.currentIndexChanged.connect(
            lambda: self._Changed(self.controller.Preset_Set(self.preset.currentData()))
        )
        self.start.valueChanged.connect(
            lambda value: self._Changed(self.controller.Range_Set(value, self.controller.model.end))
        )
        self.end.valueChanged.connect(
            lambda value: self._Changed(
                self.controller.Range_Set(self.controller.model.start, value)
            )
        )
        self.duration.valueChanged.connect(
            lambda value: self._Changed(self.controller.Duration_Set(value))
        )
        self.Language_Apply()
        self._Changed(self.controller.model)

    def Language_Apply(self):
        for key, label in self._labels:
            label.setText(self._translator.Text_Get("range." + key))
        for key in ("Full", "Custom"):
            self.preset.setItemText(
                self.preset.findData(key), self._translator.Text_Get("range." + key.lower())
            )
        self.slider.setAccessibleName(self._translator.Text_Get("range.preset"))

    def Mission_Set(self, duration):
        self._Changed(self.controller.Mission_Set(duration))

    def State_Restore(self, state):
        self._Changed(self.controller.State_Restore(state))

    def _Changed(self, model):
        blockers = [
            QSignalBlocker(control)
            for control in (self.preset, self.start, self.end, self.duration)
        ]
        for control, value in (
            (self.start, model.start),
            (self.end, model.end),
            (self.duration, model.duration),
        ):
            control.setRange(0, model.mission_duration)
            control.setValue(value)
        self.preset.setCurrentIndex(self.preset.findData(model.preset))
        self.slider.Range_Set(model.start, model.end, model.mission_duration)
        del blockers
        self.rangeChanged.emit(model)
