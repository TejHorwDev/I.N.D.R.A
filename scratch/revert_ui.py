lines = open('ui.py', encoding='utf-8').read().split('\n')

new_lines = []
skip = False
for line in lines:
    if line.startswith('class InsightPanel(QWidget):'):
        skip = True
        continue
    
    if skip:
        # Check if we reached the end of InsightPanel. 
        # InsightPanel ends right before \n\nclass MainWindow or class MainWindow
        if 'class MainWindow' in line:
            skip = False
        else:
            continue

    if not skip:
        # Revert the corrupted string replacements
        if '\\n\\nclass MainWindow(QMainWindow):' in line:
            line = line.replace('\\n\\nclass MainWindow(QMainWindow):', 'class MainWindow(QMainWindow):')
        if '_phone_sig = pyqtSignal()\\n    _insight_sig = pyqtSignal(str, str, str)' in line:
            line = line.replace('_phone_sig = pyqtSignal()\\n    _insight_sig = pyqtSignal(str, str, str)', '_phone_sig = pyqtSignal()')
        if 'self._phone_sig.connect(self._handle_phone_conn, Qt.ConnectionType.QueuedConnection)\\n        self._insight_sig.connect(self._insight_panel.show_content, Qt.ConnectionType.QueuedConnection)' in line:
            line = line.replace('self._phone_sig.connect(self._handle_phone_conn, Qt.ConnectionType.QueuedConnection)\\n        self._insight_sig.connect(self._insight_panel.show_content, Qt.ConnectionType.QueuedConnection)', 'self._phone_sig.connect(self._handle_phone_conn, Qt.ConnectionType.QueuedConnection)')
        if "if p: p.update_geometry(pw, ph)\\n        if hasattr(self, '_insight_panel'):\\n            self._insight_panel.update_size(pw, ph)" in line:
            line = line.replace("if p: p.update_geometry(pw, ph)\\n        if hasattr(self, '_insight_panel'):\\n            self._insight_panel.update_size(pw, ph)", "if p: p.update_geometry(pw, ph)")
        if 'elif cmd == "show_from_tray":\\n            self.showFullScreen()\\n        elif cmd == "close_insight":\\n            self._insight_panel.close_panel()\\n        elif cmd == "toggle_insight":\\n            self._insight_panel.toggle()' in line:
            line = line.replace('elif cmd == "show_from_tray":\\n            self.showFullScreen()\\n        elif cmd == "close_insight":\\n            self._insight_panel.close_panel()\\n        elif cmd == "toggle_insight":\\n            self._insight_panel.toggle()', 'elif cmd == "show_from_tray":\n            self.showFullScreen()')
        
        # Remove the show_insight methods if they exist
        if 'def show_insight(self, title: str, meta: str, html_body: str):' in line:
            # We need to skip this and the next few lines
            continue
        if 'self._win._insight_sig.emit(title, meta, html_body)' in line:
            continue
        if 'def close_insight(self):' in line:
            continue
        if 'self._win._ui_cmd_sig.emit("close_insight")' in line:
            continue
            
        # Also remove self._insight_panel = InsightPanel(central)
        if 'self._insight_panel = InsightPanel(central)' in line:
            continue

        new_lines.append(line)

open('ui.py', 'w', encoding='utf-8').write('\n'.join(new_lines))
