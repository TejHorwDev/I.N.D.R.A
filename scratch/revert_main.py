import re

content = open('main.py', encoding='utf-8').read()

if 'show_insight' in content:
    lines = content.split('\n')
    new_lines = []
    skip = False
    for line in lines:
        if 'name == "show_insight":' in line or 'name == "close_insight":' in line:
            skip = True
        
        if skip:
            if 'return types.FunctionResponse' in line:
                skip = False
            continue
        new_lines.append(line)
    
    content = '\n'.join(new_lines)
    
    # regex remove tool dicts
    content = re.sub(r'\s*\{\s*"name":\s*"show_insight".*?"required":\s*\["title",\s*"meta",\s*"html_body"\]\s*\}\s*\},', '', content, flags=re.DOTALL)
    content = re.sub(r'\s*\{\s*"name":\s*"close_insight".*?\}\s*\}\s*\},', '', content, flags=re.DOTALL)
    open('main.py', 'w', encoding='utf-8').write(content)
