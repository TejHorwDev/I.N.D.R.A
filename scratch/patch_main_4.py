import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Change audio/pcm to audio/pcm;rate=16000
content = content.replace('"mime_type": "audio/pcm"', '"mime_type": "audio/pcm;rate=16000"')

# Change send_realtime_input(media=msg) to send_realtime_input(audio=msg)
content = content.replace('await self.session.send_realtime_input(media=msg)', 'await self.session.send_realtime_input(audio=msg)')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
