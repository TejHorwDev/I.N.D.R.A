import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the deprecation warning
content = content.replace(
    'await self.session.send(input=greeting_prompt, end_of_turn=True)',
    'await self.session.send_client_content(turns={"parts": [{"text": greeting_prompt}]}, turn_complete=True)'
)

# Fix the lack of output parsing in _receive_audio
old_parse = """                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)"""

new_parse = """                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                
                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.text:
                                    txt = _clean_transcript(part.text)
                                    if txt:
                                        if getattr(part, 'thought', False):
                                            out_buf.append(f"[Thinking: {txt}]")
                                        else:
                                            out_buf.append(txt)"""

content = content.replace(old_parse, new_parse)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
