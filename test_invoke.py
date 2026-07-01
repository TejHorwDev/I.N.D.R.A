import sys
from PyQt6.QtCore import QMetaObject, Qt, pyqtSlot, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
import threading

app = QApplication(sys.argv)

class TestWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.label = QLabel("Not called yet", self)
        self.resize(300, 100)
        self.show()

    @pyqtSlot(str)
    def my_slot(self, text: str):
        print(f"[Qt Thread] my_slot called with: {text}")
        self.label.setText(text)

win = TestWin()

def thread_func():
    import time
    time.sleep(1)
    print("[BG Thread] Calling invokeMethod...")
                                   
    from PyQt6.QtCore import Q_ARG
    QMetaObject.invokeMethod(win, "my_slot", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "Hello from thread!"))
    print("[BG Thread] invokeMethod done")

t = threading.Thread(target=thread_func, daemon=True)
t.start()

QTimer.singleShot(3000, app.quit)
app.exec()
