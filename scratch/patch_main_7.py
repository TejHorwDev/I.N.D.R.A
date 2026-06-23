import re

with open('main.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_config = """        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\\n".join(parts),
            
            speech_config=types.SpeechConfig("""

new_config = """        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig("""

text = text.replace(old_config, new_config)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(text)
