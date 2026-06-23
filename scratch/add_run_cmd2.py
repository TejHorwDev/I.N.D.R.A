import re

with open('ui.py', 'r', encoding='utf-8') as f:
    code = f.read()

old = re.search(r'        lay.addWidget\(ft_widget, stretch=1\)\n        return w\n', code).group(0)

new_run = '''        lay.addWidget(ft_widget, stretch=1)
        return w

    def _run_cmd(self):
        txt = self._cmd_input.text().strip()
        if not txt:
            return
        self._cmd_input.clear()
        if hasattr(self, '_log'):
            self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            import threading
            threading.Thread(
                target=self.on_text_command, args=(txt,), daemon=True
            ).start()
'''
code = code.replace(old, new_run)
with open('ui.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Done!')
