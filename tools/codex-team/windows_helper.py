"""Small standard-library helpers for Codex Team on Windows."""
import json
import os
import pathlib
import subprocess
import sys
import tomllib

if sys.argv[1] == 'roles':
    roles = {}
    for path in pathlib.Path(sys.argv[2]).glob('*.toml'):
        data = tomllib.loads(path.read_text(encoding='utf-8-sig'))
        if data.get('name') and data.get('developer_instructions'):
            roles[data['name']] = data
    print(json.dumps(roles, ensure_ascii=False))
elif sys.argv[1] == 'window':
    env = os.environ.copy()
    if env.get('TERM') == 'dumb':
        env.pop('TERM')
    subprocess.Popen(sys.argv[2:], creationflags=subprocess.CREATE_NEW_CONSOLE, env=env)
else:
    raise SystemExit('Unknown helper mode')
