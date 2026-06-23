import sys
import os

with open(r'd:\PROJECTS\AI\main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('LIVE_MODEL = "models/gemini-3.1-flash-live-preview"', 'LIVE_MODEL = "models/gemini-2.5-flash"')

old_turn1 = 'turns={"parts": [{"text": text}]}, turn_complete=True'
new_turn1 = 'turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])], turn_complete=True'
content = content.replace(old_turn1, new_turn1)

old_turn2 = 'turns={"parts": [{"text": text}]},'
new_turn2 = 'turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])],'
content = content.replace(old_turn2, new_turn2)

old_turn3 = 'turns={"parts": [{"text": greeting_prompt}]}, turn_complete=True'
new_turn3 = 'turns=[types.Content(role="user", parts=[types.Part.from_text(text=greeting_prompt)])], turn_complete=True'
content = content.replace(old_turn3, new_turn3)

content = content.replace('await self.session.send_realtime_input(media=msg)', 'await self.session.send_realtime_input([msg])')

content = content.replace('"mime_type": "audio/pcm"', '"mime_type": "audio/pcm;rate=16000"')

with open(r'd:\PROJECTS\AI\main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('main.py fixed')
