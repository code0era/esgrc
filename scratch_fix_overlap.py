import os

file_path = 'e:/Desktop/CodeEra/ESGRC_ML/esgrc-streamlit/app.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = '''    .auth-title {
        font-size: 4rem;
        font-weight: 900;
        color: #FFFFFF;
        text-align: center;
        letter-spacing: -2px;
        margin-bottom: 0.5rem;
    }'''

replacement = '''    .auth-title {
        font-size: 4rem;
        font-weight: 900;
        color: #FFFFFF;
        text-align: center;
        letter-spacing: -2px;
        margin-bottom: 0.5rem;
        margin-top: 15vh;
    }'''

if target in content:
    content = content.replace(target, replacement)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed auth title overlap!")
else:
    print("Target not found!")
