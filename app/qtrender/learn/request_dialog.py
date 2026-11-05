"""Asking the user which term they want explained (core.learn.controller.InfoDialogs), and remembered settings."""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
                               QWidget)

from core.learn.controller import RequestForm


class RequestDialog(QDialog):
    def __init__(self, parent: QWidget, text: str, where: str) -> None:
        super().__init__(parent)
        self.setWindowTitle('Request info')
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        intro = QLabel('Which term would you like explained? Your request is saved so a topic can be added.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.term = QLineEdit(text)
        self.term.setPlaceholderText('e.g. Sharpe ratio')
        self.note = QLineEdit()
        self.note.setPlaceholderText('Anything that helps (optional)')
        form.addRow('Term', self.term)
        form.addRow('Note', self.note)
        layout.addLayout(form)
        if where:
            context = QLabel(f'Seen in: {where}')
            context.setObjectName('summary')
            layout.addWidget(context)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText('Send request')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.term.textChanged.connect(self._update)
        self._update()
        self.term.setFocus()

    def _update(self) -> None:
        self.ok_button.setEnabled(bool(self.term.text().strip()))

    def form(self) -> RequestForm:
        return RequestForm(self.term.text().strip(), self.note.text().strip())


class QtInfoDialogs:
    def __init__(self, window: QWidget) -> None:
        self.window = window

    def ask_request(self, text: str, where: str) -> RequestForm | None:
        dialog = RequestDialog(self.window, text, where)
        return dialog.form() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def notify(self, text: str) -> None:
        QMessageBox.information(self.window, 'Info Wizard', text)


class QtPreferences:
    """core.learn.preferences.Preferences, stored with QSettings (the registry on Windows)."""

    def __init__(self) -> None:
        self.settings = QSettings('StockDashboard', 'Dashboard')

    def get_bool(self, key: str, default: bool = False) -> bool:
        return bool(self.settings.value(key, default, type=bool))

    def set_bool(self, key: str, value: bool) -> None:
        self.settings.setValue(key, value)
