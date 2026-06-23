import os

with open(r'd:\PROJECTS\AI\main.py', 'r', encoding='utf-8') as f:
    content = f.read()

with open('tools_rebuilt.py', 'r', encoding='utf-8') as f:
    tools_str = f.read()

if 'TOOL_DECLARATIONS = [' not in content:
    content = content.replace('def _clean_transcript(text: str) -> str:', tools_str + '\n\ndef _clean_transcript(text: str) -> str:')

old_config = '''            system_instruction="\\n".join(parts),
            
            speech_config=types.SpeechConfig('''
new_config = '''            system_instruction="\\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig('''

if 'tools=[{"function_declarations": TOOL_DECLARATIONS}],' not in content:
    content = content.replace(old_config, new_config)

with open(r'd:\PROJECTS\AI\main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Injection done.')
