import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix greeting prompt send_client_content
old_greeting = '''                    await self.session.send_client_content(
                        turns={"parts": [{"text": greeting_prompt}]}, turn_complete=True
                    )'''
new_greeting = '''                    await self.session.send_client_content(
                        turns=[types.Content(role="user", parts=[types.Part.from_text(text=greeting_prompt)])], turn_complete=True
                    )'''
content = content.replace(old_greeting, new_greeting)

# Fix _on_text_command
old_on_text = '''        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]}, turn_complete=True
            ),
            self._loop,
        )'''
new_on_text = '''        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])], turn_complete=True
            ),
            self._loop,
        )'''
content = content.replace(old_on_text, new_on_text)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
