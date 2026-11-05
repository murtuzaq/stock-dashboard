"""Small layout helpers shared by the widgets."""
from PySide6.QtWidgets import QLayout


def clear_layout(layout: QLayout) -> None:
    """Remove everything from a layout at once.

    deleteLater() alone leaves the old widgets on screen until Qt gets round to deleting them (they overlap the new
    ones meanwhile), so each is hidden and detached first. Spacers (addStretch) have no widget and are just dropped.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
