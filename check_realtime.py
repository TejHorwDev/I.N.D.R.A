
import re
with open(r'C:\Users\Administrator\.gemini\antigravity-ide\brain\7adb6caf-8bd3-4cc5-9084-a5c66bab6619\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if 'send_realtime_input' in line:
            m = re.findall(r'send_realtime_input[^)]*\)', line)
            if m:
                for match in set(m):
                    print(match)

