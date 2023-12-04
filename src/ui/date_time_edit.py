from PyQt5.QtWidgets import QDateTimeEdit
from PyQt5.QtCore import QObject, QEvent, Qt
class NoScrollOrArrowKeyFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel or \
           (event.type() == QEvent.KeyPress and event.key() in [Qt.Key_Up, Qt.Key_Down]):
            return True  # Ignore wheel and up/down arrow key events
        return super(NoScrollOrArrowKeyFilter, self).eventFilter(obj, event)
