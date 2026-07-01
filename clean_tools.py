import re

with open('tools_extracted.txt', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('\\r', '')
text = text.replace('\\n', '\n')
text = text.replace('\\"', '"')

cleaned_lines = []
for line in text.split('\n'):
    line = re.sub(r'^\d+:\s', '', line)
    cleaned_lines.append(line)

cleaned_text = '\n'.join(cleaned_lines)

end_idx = cleaned_text.find(']\n')
if end_idx != -1:
    cleaned_text = cleaned_text[:end_idx+2]
else:
                     
    end_idx = cleaned_text.find(']')
    if end_idx != -1:
        cleaned_text = cleaned_text[:end_idx+1]

                                                         
                                                                      
with open('tools_clean.py', 'w', encoding='utf-8') as f:
    f.write(cleaned_text)

print("Created tools_clean.py")
