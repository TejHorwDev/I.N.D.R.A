import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove tools from LiveConnectConfig to prevent 1008/1007 crashes on tool response
content = content.replace(
    'tools=[{"function_declarations": TOOL_DECLARATIONS}],',
    ''
)

# 2. Change greeting prompt to avoid calling the tool
old_greeting = '''                    greeting_prompt = (
                        "System Boot Sequence Complete. You are INDRA. "
                        "Give a short, cool, slightly sci-fi greeting to the user (e.g. 'Welcome back sir' or 'Systems online') "
                        "and then call the system_monitor tool to check the system status."
                    )'''

new_greeting = '''                    greeting_prompt = (
                        "System Boot Sequence Complete. You are INDRA. "
                        "Give a short, cool, slightly sci-fi greeting to the user (e.g. 'Welcome back sir' or 'Systems online')."
                    )'''

content = content.replace(old_greeting, new_greeting)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
