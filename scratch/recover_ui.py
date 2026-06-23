import re

with open('ui.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Remove FloatWidget class
code = re.sub(r'class FloatWidget\(QFrame\):.*?(?=\n\nclass MainWindow\(QMainWindow\):)', '', code, flags=re.DOTALL)

# 2. Revert MainWindow.__init__
old_init_match = re.search(r'        central = QWidget\(\)\n.*?        self\._build_cmd_only\(self\._cmd_panel\.inner\)', code, flags=re.DOTALL)
if old_init_match:
    old_init = old_init_match.group(0)
    new_init = '''        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        self.hud = WebHudCanvas()
        body.addWidget(self.hud, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())'''
    code = code.replace(old_init, new_init)

# 3. Revert resizeEvent
old_resize = re.search(r'        for p in \[getattr\(self, k, None\) for k in \(\'_left_panel\',.*?\n.*?p\.update_geometry\(pw, ph\)', code, flags=re.DOTALL)
if old_resize:
    code = code.replace(old_resize.group(0), '')

# 4. Fix BootOverlay toggle
code = code.replace('[self.hud.show(), self._time_panel.toggle(), self._sys_panel.toggle(), self._right_panel.toggle()]', 'self.hud.show')
code = code.replace('lambda: self.hud.show', 'self.hud.show')

# 5. Restore _build_header
header_parts = re.search(r'    def _build_status_panel\(self, w: QWidget\):(.*?)    def _build_title_panel\(self, w: QWidget\):(.*?)    def _build_time_panel\(self, w: QWidget\):(.*?)    def _tick_clock\(self\):', code, flags=re.DOTALL)
if header_parts:
    status_code = header_parts.group(1).replace('lay = QVBoxLayout(w)', 'lay = QVBoxLayout()').replace('lay.setContentsMargins(10, 10, 10, 10)\n', '')
    title_code = header_parts.group(2).replace('lay = QVBoxLayout(w)', 'lay = QVBoxLayout()').replace('lay.setContentsMargins(10, 10, 10, 10)\n', '')
    time_code = header_parts.group(3).replace('lay = QVBoxLayout(w)', 'lay = QVBoxLayout()').replace('lay.setContentsMargins(10, 10, 10, 10)\n', '')
    
    new_header = f'''    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(90)
        w.setStyleSheet(f"background: {{C.DARK}}; border-bottom: 1px solid {{C.BORDER}};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 5, 10, 5)

        left = QWidget()
{status_code}        left.setLayout(lay)
        lay.addWidget(left)

        mid = QWidget()
{title_code}        mid.setLayout(lay)
        lay.addWidget(mid, stretch=1)

        right = QWidget()
{time_code}        right.setLayout(lay)
        lay.addWidget(right)

        return w

    def _tick_clock(self):'''
    
    # We must fix the indentation inside status_code, title_code, time_code
    new_header = new_header.replace('        lay = QVBoxLayout()', '        lay2 = QVBoxLayout()').replace('lay.', 'lay2.')
    new_header = new_header.replace('lay2.addWidget(left)', 'lay.addWidget(left)')
    new_header = new_header.replace('lay2.addWidget(mid, stretch=1)', 'lay.addWidget(mid, stretch=1)')
    new_header = new_header.replace('lay2.addWidget(right)', 'lay.addWidget(right)')

    code = code.replace(header_parts.group(0), new_header)

# 6. Restore _build_left_panel
left_parts = re.search(r'    def _build_sys_monitor\(self, w: QWidget\):(.*?)    def _build_vision_monitor\(self, w: QWidget\):(.*?)    def _build_webcam_monitor', code, flags=re.DOTALL)
if left_parts:
    sys_code = left_parts.group(1).replace('lay = QVBoxLayout(w)', 'lay.addSpacing(10)')
    vis_code = left_parts.group(2).replace('lay = QVBoxLayout(w)', 'lay.addSpacing(10)')
    
    new_left = f'''    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {{C.DARK}}; border-right: 1px solid {{C.BORDER}};")
        lay = QVBoxLayout(w)
{sys_code}{vis_code}        lay.addStretch(1)
        return w

    def _build_webcam_monitor'''
    code = code.replace(left_parts.group(0), new_left)

# 7. Restore _build_right_panel
right_parts = re.search(r'    def _build_log_only\(self, w: QWidget\):(.*?)    def _build_upload_only\(self, w: QWidget\):(.*?)    def _build_cmd_only', code, flags=re.DOTALL)
if right_parts:
    log_code = right_parts.group(1).replace('lay = QVBoxLayout(w)', 'lay.addSpacing(10)')
    up_code = right_parts.group(2).replace('lay = QVBoxLayout(w)', 'lay.addSpacing(10)')
    
    new_right = f'''    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {{C.DARK}}; border-left: 1px solid {{C.BORDER}};")
        lay = QVBoxLayout(w)
{log_code}{up_code}        return w

    def _build_cmd_only'''
    code = code.replace(right_parts.group(0), new_right)

# 8. Restore _build_footer
foot_parts = re.search(r'    def _build_cmd_only\(self, w: QWidget\):(.*?)    def _build_footer\(self, w: QWidget\):(.*?)    def _setup_shortcuts', code, flags=re.DOTALL)
if foot_parts:
    cmd_code = foot_parts.group(1).replace('lay = QVBoxLayout(w)', 'lay.addSpacing(5)')
    ft_code = foot_parts.group(2).replace('lay = QVBoxLayout(w)', 'lay.addSpacing(5)')
    
    new_foot = f'''    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(80)
        w.setStyleSheet(f"background: {{C.DARK}}; border-top: 1px solid {{C.BORDER}};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(15, 10, 15, 10)
        lay.setSpacing(20)
        
        # Command Input
{cmd_code}
        # Footer text
{ft_code}        lay.addWidget(_fl("◈ STARK INDUSTRIES", C.PRI_DIM))
        return w

    def _setup_shortcuts'''
    code = code.replace(foot_parts.group(0), new_foot)

# 9. Restore _handle_ui_cmd
old_handle_cmd = re.search(r'        panels = \{.*?        \}', code, flags=re.DOTALL)
if old_handle_cmd:
    new_handle_cmd = '''        panels = {
            "sys": self._left_panel,
            "log": self._right_panel,
        }'''
    code = code.replace(old_handle_cmd.group(0), new_handle_cmd)

# 10. Remove Floating widget specific toggle functions
code = re.sub(r'    def toggle_sys_monitor\(self\):.*?    def set_state\(self, value: str\):', '    def set_state(self, value: str):', code, flags=re.DOTALL)

with open('ui.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('UI Restored successfully!')
