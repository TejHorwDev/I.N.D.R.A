import re

with open('tools_extracted.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace escaped strings
text = text.replace('\\r', '')
text = text.replace('\\n', '\n')
text = text.replace('\\"', '"')

# Remove the line numbers that were prepended by view_file (e.g., '86: ')
cleaned_lines = []
for line in text.split('\n'):
    line = re.sub(r'^\d+:\s', '', line)
    cleaned_lines.append(line)

cleaned_text = '\n'.join(cleaned_lines)

# Stop at the end of the list
end_idx = cleaned_text.find(']\n')
if end_idx != -1:
    cleaned_text = cleaned_text[:end_idx+2]
else:
    # try another way
    end_idx = cleaned_text.find(']')
    if end_idx != -1:
        cleaned_text = cleaned_text[:end_idx+1]

# Now, we need to remove the "show_details" tool if it exists
# actually we will just find it and remove the dictionary
# A safe way is to let python format it or just insert it into main.py
with open('tools_clean.py', 'w', encoding='utf-8') as f:
    f.write(cleaned_text)

print("Created tools_clean.py")
