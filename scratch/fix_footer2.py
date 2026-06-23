import re

with open('ui.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_footer = re.search(r'    def _build_cmd_only\(self.*?(?=    def _on_file_selected)', code, flags=re.DOTALL)
if old_footer:
    new_foot = '''    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(80)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(15, 10, 15, 10)
        lay.setSpacing(20)
        
        # Command Input
        cmd_widget = QWidget()
        cmd_lay = QVBoxLayout(cmd_widget)
        cmd_lay.setContentsMargins(0,0,0,0)
        cmd_lay.setSpacing(5)
        
        hdr = QLabel("◈ COMMAND INPUT")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; padding-bottom: 2px;")
        cmd_lay.addWidget(hdr)

        inp_lay = QHBoxLayout()
        inp_lay.setSpacing(8)
        self._cmd_input = QLineEdit()
        self._cmd_input.setPlaceholderText("Type a command...")
        self._cmd_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.BG}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px;
                padding: 4px 8px; font-family: 'Courier New';
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        inp_lay.addWidget(self._cmd_input)

        run_btn = QPushButton("▶")
        run_btn.setFixedSize(28, 28)
        run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.BG}; color: {C.PRI};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {C.BG}; background: {C.PRI};
            }}
        """)
        run_btn.clicked.connect(self._run_cmd)
        inp_lay.addWidget(run_btn)

        cmd_lay.addLayout(inp_lay)
        lay.addWidget(cmd_widget)

        # Footer text
        ft_widget = QWidget()
        ft_lay = QVBoxLayout(ft_widget)
        ft_lay.setContentsMargins(0,0,0,0)
        ft_lay.setSpacing(5)
        
        title = QLabel("I.N.D.R.A  ◈  SYSTEM CONTROLS")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ft_lay.addWidget(title)

        sub = QLabel("[F4] Toggle Microphone   |   [F11] Toggle Fullscreen")
        sub.setFont(QFont("Courier New", 8))
        sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ft_lay.addWidget(sub)

        copy = QLabel("FatihMakes Industries  ◈  ◈ STARK INDUSTRIES")
        copy.setFont(QFont("Courier New", 7))
        copy.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ft_lay.addWidget(copy)
        
        lay.addWidget(ft_widget, stretch=1)
        return w\n\n'''
    code = code.replace(old_footer.group(0), new_foot)
    with open('ui.py', 'w', encoding='utf-8') as f:
        f.write(code)
    print('Fixed footer!')
