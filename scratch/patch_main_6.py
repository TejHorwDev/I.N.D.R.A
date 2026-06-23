import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix _process_ws_command
old_ws = 'turns={"parts": [{"text": text}]}'
new_ws = 'turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])]'
content = content.replace(old_ws, new_ws)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
