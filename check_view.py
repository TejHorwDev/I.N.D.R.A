
import json
with open(r'C:\Users\Administrator\.gemini\antigravity-ide\brain\7adb6caf-8bd3-4cc5-9084-a5c66bab6619\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get('type') == 'VIEW_FILE':
            print('Viewed:', repr(data.get('content', ''))[:150])

