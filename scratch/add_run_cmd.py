import re

with open('ui.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_foot = """        lay.addWidget(ft_widget, stretch=1)
        return w

    def _run_cmd(self):
        txt = self._cmd_input.text().strip()
        if not txt:
            return
        self._cmd_input.clear()
        if hasattr(self, "_log"):
            self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            import threading
            threading.Thread(
                target=self.on_text_command, args=(txt,), daemon=True
            ).start()

    def _setup_shortcuts(self):"""

code = code.replace('''        lay.addWidget(ft_widget, stretch=1)\n        return w\n\n    def _setup_shortcuts(self):''', new_foot)

with open('ui.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Applied _run_cmd')
