"""Install the portable skill, role aliases and optional Windows CLI launcher."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import uuid

REPO = Path(__file__).resolve().parents[1]


def install(codex_home: Path, skills_dir: Path, *, with_cli=False, bin_dir=None,
            force=False, dry_run=False) -> dict:
    codex_home = codex_home.expanduser().resolve()
    skills_dir = skills_dir.expanduser().resolve()
    source = REPO / 'skills' / 'orchestrate'
    plan = []

    def add(data: bytes, root: Path, relative: Path):
        destination = root / relative
        if not destination.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Destination escapes installation directory: {destination}')
        if destination.exists() and not destination.is_file():
            raise ValueError(f'Destination is not a file: {destination}')
        plan.append((destination, data))

    for item in sorted(source.rglob('*')):
        if item.is_file():
            add(item.read_bytes(), skills_dir, Path('orchestrate') / item.relative_to(source))

    names = set()
    aliases = {}
    for item in sorted((source / 'references' / 'roles').glob('*.toml')):
        role = tomllib.loads(item.read_text(encoding='utf-8'))
        if not all(role.get(key) for key in ['name', 'description', 'developer_instructions']):
            raise ValueError(f'Incomplete role: {item.name}')
        if role['name'] in names:
            raise ValueError(f'Duplicate role name: {role["name"]}')
        names.add(role['name'])
        aliases[role['name']] = item.name
        add(item.read_bytes(), codex_home, Path('agents') / item.name)
    # A second file with the same role name would make role selection ambiguous.
    for item in (codex_home / 'agents').glob('*.toml'):
        existing = tomllib.loads(item.read_text(encoding='utf-8-sig'))
        name = existing.get('name')
        if name in aliases and item.name != aliases[name]:
            raise ValueError(f'Role {name} already exists in another file: {item}')

    shim = None
    if with_cli:
        if os.name != 'nt':
            raise ValueError('--with-cli currently supports Windows only. Core skill works on other platforms.')
        node = shutil.which('node')
        if not node:
            raise ValueError('Node.js 22 or newer is required for --with-cli.')
        version = subprocess.check_output([node, '--version'], text=True).strip()
        if int(version.lstrip('v').split('.')[0]) < 22:
            raise ValueError('Node.js 22 or newer is required for --with-cli.')
        if not shutil.which('codex'):
            raise ValueError('Install and sign in to Codex CLI before using --with-cli.')
        for name in ['codex-team.mjs', 'windows_helper.py']:
            add((REPO / 'tools/codex-team' / name).read_bytes(), codex_home, Path('tools/codex-team') / name)
        if bin_dir is None:
            appdata = os.environ.get('APPDATA')
            if not appdata:
                raise ValueError('APPDATA is unavailable; specify --bin-dir.')
            bin_dir = Path(appdata) / 'npm'
        bin_dir = bin_dir.expanduser().resolve()
        entry = codex_home / 'tools/codex-team/codex-team.mjs'
        # Pin this installation's role/state root and the Python interpreter.
        # These paths are generated on the installing computer, never published.
        escape = lambda value: str(value).replace('%', '%%')
        body = ('@echo off\r\nsetlocal\r\n'
                f'set "CODEX_HOME={escape(codex_home)}"\r\n'
                f'set "CODEX_TEAM_PYTHON={escape(sys.executable)}"\r\n'
                f'"{escape(node)}" "{escape(entry)}" %*\r\n')
        add(body.encode('utf-8'), bin_dir, Path('codex-team.cmd'))
        shim = str(bin_dir / 'codex-team.cmd')

    changed = [(p, data) for p, data in plan if not p.exists() or p.read_bytes() != data]
    conflicts = [p for p, _ in changed if p.exists()]
    if conflicts and not force:
        raise FileExistsError('Existing files differ; review them and rerun with --force to back them up: '
                              + ', '.join(str(p) for p in conflicts))
    report = {'files': len(plan), 'changed': len(changed), 'roles': len(names),
              'skill': str(skills_dir / 'orchestrate'), 'launcher': shim, 'dry_run': dry_run}
    if dry_run:
        return report
    if conflicts:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
        backup = codex_home / 'agent-backups' / ('orchestrator-kit-' + stamp)
        for index, file in enumerate(conflicts):
            target = backup / str(index) / file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
        (backup / 'restore-map.txt').write_text(
            '\n'.join(f'{i}/{p.name}\t{p}' for i, p in enumerate(conflicts)), encoding='utf-8')
        report['backup'] = str(backup)
    for destination, data in changed:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
        temporary.write_bytes(data)
        os.replace(temporary, destination)
        if destination.read_bytes() != data:
            raise IOError(f'Installed contents differ: {destination}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')))
    parser.add_argument('--skills-dir', type=Path, default=Path.home() / '.agents' / 'skills')
    parser.add_argument('--with-cli', action='store_true', help='Install the optional Windows multi-window launcher')
    parser.add_argument('--bin-dir', type=Path, help='Launcher shim directory (default: APPDATA/npm)')
    parser.add_argument('--force', action='store_true', help='Back up and replace conflicting files')
    parser.add_argument('--dry-run', action='store_true', help='Inspect the plan without writing files')
    args = parser.parse_args()
    try:
        result = install(**vars(args))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Install failed: {error}\n')
    for key, value in result.items():
        print(f'{key}: {value}')
    if result.get('launcher'):
        print('Run the launcher by its path, or add its directory to your user PATH.')


if __name__ == '__main__':
    main()
