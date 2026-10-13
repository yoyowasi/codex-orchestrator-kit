"""Install Orchestrator Kit for Codex, or for Claude Code without the plugin marketplace.

Installs the generated `orchestrate` skill and the role agents of the selected packs, records
every installed file with its sha256 in <home>/orchestrator-kit/install-manifest.json, and uses
that manifest to update, prune and uninstall without touching files it did not install.
"""
from __future__ import annotations

import argparse
import codecs
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from typing import NamedTuple
import uuid

REPO = Path(__file__).resolve().parents[1]
TARGETS = ('codex', 'claude')
INSTALL_NAME = 'orchestrator-kit'  # install-manifest directory, manifest name and backup prefix
INSTALL_MANIFEST = Path(INSTALL_NAME) / 'install-manifest.json'
CLI_FILES = ('codex-team.mjs', 'windows_helper.py')
CLAUDE_PLUGIN_NOTE = ('Claude Code: use either the plugin install (/plugin install {plugin}@{marketplace}) '
                      'or this script install, never both. Both register the same skill and agents.')
DEFAULT_MAX_SUBAGENTS = 12
LIMIT_KEY = 'max_concurrent_threads_per_session'
LEGACY_LIMIT_KEY = 'max_threads'
_KEY_PART = r'''(?:[A-Za-z0-9_-]+|'[^'\r\n]*'|"(?:[^"\\\r\n]|\\.)*")'''
_KEY_PATH = rf'{_KEY_PART}(?:[ \t]*\.[ \t]*{_KEY_PART})*'
_HEADER = re.compile(
    rf'^[ \t]*(?P<open>\[\[?)[ \t]*(?P<key>{_KEY_PATH})[ \t]*'
    r'(?P<close>\]\]?)[ \t]*(?:#[^\r\n]*)?(?:\r?\n)?$')
_ASSIGNMENT = re.compile(rf'^[ \t]*(?P<key>{_KEY_PATH})[ \t]*=[ \t]*')


def _key_path(source: str) -> tuple[str, ...]:
    """Let the TOML parser decode quoted/dotted keys instead of interpreting them."""
    value = tomllib.loads(source + ' = 0')
    path = []
    while isinstance(value, dict):
        key, value = next(iter(value.items()))
        path.append(key)
    return tuple(path)


def _statements(source: str):
    """Yield complete TOML statements without mistaking multiline values for keys."""
    start = i = depth = 0
    quote = None
    while i < len(source):
        char = source[i]
        if quote:
            if quote[0] == '"' and char == '\\':
                i += 2
                continue
            if source.startswith(quote, i):
                i += len(quote)
                if len(quote) == 3:
                    # A multiline string can end with four or five quote marks.
                    while i < len(source) and source[i] == quote[0]:
                        i += 1
                quote = None
                continue
        elif char in "\"'":
            quote = char * 3 if source.startswith(char * 3, i) else char
            i += len(quote)
            continue
        elif char == '#':
            end = source.find('\n', i)
            i = len(source) if end < 0 else end
            continue
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
        elif char == '\n' and depth == 0:
            yield start, i + 1, source[start:i + 1]
            start = i + 1
        i += 1
    if start < len(source):
        yield start, len(source), source[start:]


def _same_toml(left, right) -> bool:
    """Compare parsed values, including TOML nan, which normally differs from itself."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_toml(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_toml(a, b) for a, b in zip(left, right))
    return left == right or (isinstance(left, float) and math.isnan(left) and math.isnan(right))


def _decode_toml(data: bytes, label) -> tuple[str, dict]:
    """Decode a TOML file the user owns; errors name the file and how to fix it."""
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        raise ValueError(f'{label} is UTF-16 (PowerShell 5.1 ">" writes UTF-16); re-save it as UTF-8 and rerun.')
    try:
        source = data.decode('utf-8-sig')
        return source, tomllib.loads(source)
    except UnicodeDecodeError as error:
        raise ValueError(f'{label} is not valid UTF-8 ({error}); re-save it as UTF-8 and rerun.') from None
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f'{label} is not valid TOML ({error}); fix it and rerun.') from None


def _config_with_limit(data: bytes, max_subagents: int | None, label='config.toml') -> tuple[bytes, int]:
    """Patch only the concurrency setting, then verify all other TOML values agree."""
    if max_subagents is not None and (type(max_subagents) is not int or max_subagents < 1):
        raise ValueError('--max-subagents must be a positive integer.')
    source, config = _decode_toml(data, label)
    agents = config.get('agents', {})
    if not isinstance(agents, dict):
        raise ValueError('config.toml agents must be a table.')
    for key in (LIMIT_KEY, LEGACY_LIMIT_KEY):
        if key in agents and (type(agents[key]) is not int or agents[key] < 1):
            raise ValueError(f'config.toml agents.{key} must be a positive integer.')
    if max_subagents is None:
        for key in (LIMIT_KEY, LEGACY_LIMIT_KEY):
            if key in agents:
                return data, agents[key]
    limit = DEFAULT_MAX_SUBAGENTS if max_subagents is None else max_subagents
    expected = deepcopy(config)
    expected.setdefault('agents', {})[LIMIT_KEY] = limit
    expected['agents'].pop(LEGACY_LIMIT_KEY, None)
    if _same_toml(expected, config):
        return data, limit

    newline_match = re.search(r'\r?\n', source)
    newline = newline_match.group() if newline_match else '\n'
    context = ()
    agent_header_end = None
    root_end = len(source)
    root_dotted_agents = False
    assignments = {}
    for start, end, statement in _statements(source):
        header = _HEADER.fullmatch(statement)
        if header:
            root_end = min(root_end, start)
            context = _key_path(header['key'])
            if context == ('agents',) and header['open'] == '[':
                agent_header_end = end
            continue
        assignment = _ASSIGNMENT.match(statement)
        if assignment:
            key = _key_path(assignment['key'])
            if not context and len(key) > 1 and key[0] == 'agents':
                root_dotted_agents = True
            full_key = context + key
            if full_key in (('agents', LIMIT_KEY), ('agents', LEGACY_LIMIT_KEY)):
                assignments[full_key[-1]] = (start, end, statement, assignment, context)

    unsupported = ('Cannot safely edit the agents setting in config.toml. '
                   'Use a regular [agents] table or root agents.<key> assignments '
                   'instead of an inline table or another complex layout.')
    edits = []
    existing = [key for key in (LIMIT_KEY, LEGACY_LIMIT_KEY) if key in agents]
    for key in existing:
        if key not in assignments:
            raise ValueError(unsupported)
        start, end, statement, assignment, context = assignments[key]
        # A valid integer is a single-line value. Keep its whitespace and comment.
        value = re.fullmatch(r'([^#\r\n]*?)([ \t]*(?:#[^\r\n]*)?)(\r?\n)?',
                             statement[assignment.end():])
        if not value:
            raise ValueError(unsupported)
        suffix = value[2] + (value[3] or '')
        if key == LEGACY_LIMIT_KEY and LIMIT_KEY in agents:
            # Retain a legacy setting's explanation even when removing the alias.
            replacement = suffix.lstrip(' \t') if '#' in value[2] else ''
        else:
            prefix = statement[:assignment.end()]
            if key == LEGACY_LIMIT_KEY:
                replacement_key = LIMIT_KEY if context else 'agents.' + LIMIT_KEY
                prefix = (statement[:assignment.start('key')] + replacement_key
                          + statement[assignment.end('key'):assignment.end()])
            replacement = prefix + str(limit) + suffix
        edits.append((start, end, replacement))
    if not existing:
        setting = f'{LIMIT_KEY} = {limit}{newline}'
        if agent_header_end is not None:
            offset = agent_header_end
            insertion = setting
        elif root_dotted_agents:
            offset = root_end
            insertion = 'agents.' + setting
        else:
            offset = len(source)
            insertion = f'[agents]{newline}' + setting
            if source and source.endswith('\n'):
                insertion = newline + insertion
        if offset and not source[:offset].endswith('\n'):
            insertion = newline + insertion
        edits.append((offset, offset, insertion))
    updated = source
    for start, end, replacement in sorted(edits, reverse=True):
        updated = updated[:start] + replacement + updated[end:]
    try:
        verified = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(unsupported) from error
    if not _same_toml(verified, expected):
        raise ValueError(unsupported)
    bom = b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b''
    return bom + updated.encode('utf-8'), limit


SKILL = 'orchestrate'
_ROLE_ID = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')


class _File(NamedTuple):
    path: Path
    data: bytes
    target: str
    owned: bool  # recorded in the install manifest; config.toml is edited in place, not owned


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _default_codex_home() -> Path:
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')


def _default_skills_dir() -> Path:
    return Path.home() / '.agents' / 'skills'


def _default_claude_home() -> Path:
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude')


def _load_release(repo: Path) -> dict:
    path = repo / 'src' / 'manifest.toml'
    if not path.is_file():
        raise ValueError(f'Release manifest not found: {path}')
    release = _decode_toml(path.read_bytes(), path)[1]
    if not release.get('version') or 'core' not in release.get('packs', {}):
        raise ValueError(f'{path} needs a version and a core pack.')
    return release


def _require(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(f'Generated file is missing: {path}. Run python scripts/build.py first.')
    return path


def _role_packs(repo: Path, release: dict, target: str) -> dict[str, str]:
    """Map every role id built for `target` to its pack, read from the role sources with the same
    rules as scripts/build.py: a BOM is allowed and files starting with '_' are not roles."""
    roles = {}
    for file in sorted((repo / 'src' / 'roles').glob('*.toml')):
        if file.name.startswith('_'):
            continue
        role = _decode_toml(file.read_bytes(), file)[1]
        role_id, pack = role.get('id') or file.stem, role.get('pack')
        if not _ROLE_ID.fullmatch(role_id) or pack not in release['packs']:
            raise ValueError(f'Invalid role id or pack in {file}')
        platforms = role.get('platforms') or release['packs'][pack].get('platforms', [])
        if target in platforms:
            roles[role_id] = pack
    return roles


def _select_packs(spec, release: dict, targets, previous: dict) -> dict[str, list[str]]:
    """Resolve --packs for each target. Core is always included; None reuses the installed packs."""
    packs = release['packs']

    def built_for(name, target):
        return target in packs[name].get('platforms', [])

    chosen = None
    if spec is not None:
        names = [name.strip() for name in (spec.split(',') if isinstance(spec, str) else spec) if name.strip()]
        unknown = sorted(set(names) - set(packs) - {'all'})
        if not names or unknown:
            raise ValueError(f'Unknown pack: {", ".join(unknown) or "(none)"}. '
                             f'Use a comma-separated list of {", ".join(packs)}, or all.')
        if 'all' in names:
            chosen = set(packs)  # every pack, each target keeps the packs built for it
        else:
            chosen = set(names)
            for name in sorted(chosen):
                if not any(built_for(name, target) for target in targets):
                    raise ValueError(f'Pack {name} is not built for {" or ".join(targets)}.')
    selected = {}
    for target in targets:
        wanted = chosen if chosen is not None else set(previous.get(target) or ())
        selected[target] = [name for name in packs if (name in wanted or name == 'core') and built_for(name, target)]
    return selected


def _toml_name(file: Path):
    return _decode_toml(file.read_bytes(), file)[1].get('name')


def _markdown_name(file: Path):
    """Return the `name` of a Claude Code agent's YAML frontmatter."""
    match = re.match(r'\A---\r?\n(.*?)\r?\n---', file.read_text(encoding='utf-8-sig', errors='replace'), re.S)
    for line in (match[1].splitlines() if match else ()):
        key, separator, value = line.partition(':')
        if separator and key.strip() == 'name':
            return value.strip().strip('\'"')
    return None


def _guard_role_names(directory: Path, pattern: str, ours: dict, read_name, skip: set):
    """A second file with one of our role names would make role selection ambiguous."""
    if not directory.is_dir():
        return
    for item in sorted(directory.glob(pattern)):
        if item in skip or not item.is_file():
            continue
        name = read_name(item)
        if name in ours and item.name != ours[name]:
            raise ValueError(f'Role {name} already exists in another file: {item}')


def _oem_encoding() -> str:
    """cmd.exe reads batch files in the console's code page, which starts as the OEM code page."""
    try:
        import ctypes
        encoding = f'cp{ctypes.windll.kernel32.GetOEMCP()}'
        codecs.lookup(encoding)
        return encoding
    except (AttributeError, OSError, LookupError):
        return 'ascii'


def _launcher_shim(codex_home: Path, python: str, node: str, encoding: str) -> bytes:
    """The codex-team.cmd shim, pinning this installation's role/state root and Python.
    These paths are generated on the installing computer and never published."""
    escape = lambda value: str(value).replace('%', '%%')
    entry = Path(codex_home) / 'tools' / 'codex-team' / 'codex-team.mjs'
    body = ('@echo off\r\nsetlocal\r\n'
            f'set "CODEX_HOME={escape(codex_home)}"\r\n'
            f'set "CODEX_TEAM_PYTHON={escape(python)}"\r\n'
            f'"{escape(node)}" "{escape(entry)}" %*\r\n')
    try:
        return body.encode(encoding)
    except UnicodeEncodeError:
        raise ValueError(f'The launcher shim cannot hold these paths in the console code page ({encoding}): '
                         f'{codex_home}, {python}, {node}. Use --codex-home and a Python and Node.js '
                         'installation whose paths that code page can represent (ASCII always works).') from None


def _plan_codex(repo, release, packs, codex_home, skills_dir, with_cli, bin_dir, max_subagents, add):
    config_file = codex_home / 'config.toml'
    config, limit = _config_with_limit(config_file.read_bytes() if config_file.exists() else b'',
                                       max_subagents, config_file)
    add('codex', codex_home, Path('config.toml'), config, owned=False)

    source = _require(repo / 'skills' / SKILL / 'SKILL.md').parent
    for item in sorted(source.rglob('*')):
        if item.is_file():
            add('codex', skills_dir, Path(SKILL) / item.relative_to(source), item.read_bytes())

    names = {}
    for role_id, pack in _role_packs(repo, release, 'codex').items():
        if pack not in packs:
            continue
        item = _require(repo / 'codex' / 'agents' / f'{role_id}.toml')
        data = item.read_bytes()
        role = tomllib.loads(data.decode('utf-8'))
        if not all(role.get(key) for key in ['name', 'description', 'developer_instructions']):
            raise ValueError(f'Incomplete role: {item.name}')
        if role['name'] in names:
            raise ValueError(f'Duplicate role name: {role["name"]}')
        names[role['name']] = item.name
        add('codex', codex_home, Path('agents') / item.name, data)

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
        for name in CLI_FILES:
            data = _require(repo / 'extras' / 'codex-team' / name).read_bytes()
            add('codex', codex_home, Path('tools/codex-team') / name, data)
        if bin_dir is None:
            appdata = os.environ.get('APPDATA')
            if not appdata:
                raise ValueError('APPDATA is unavailable; specify --bin-dir.')
            bin_dir = Path(appdata) / 'npm'
        bin_dir = Path(bin_dir).expanduser().resolve()
        add('codex', bin_dir, Path('codex-team.cmd'),
            _launcher_shim(codex_home, sys.executable, node, _oem_encoding()))
        shim = str(bin_dir / 'codex-team.cmd')
    info = {'packs': packs, 'roles': len(names), 'skill': str(skills_dir / SKILL),
            'agents': str(codex_home / 'agents'), 'launcher': shim}
    return limit, names, info


def _plan_claude(repo, release, packs, claude_home, add):
    core = repo / 'plugins' / release['packs']['core']['plugin']
    source = _require(core / 'skills' / SKILL / 'SKILL.md').parent
    for item in sorted(source.rglob('*')):
        if item.is_file():
            add('claude', claude_home, Path('skills') / SKILL / item.relative_to(source), item.read_bytes())

    names = {}
    for role_id, pack in _role_packs(repo, release, 'claude').items():
        if pack not in packs:
            continue
        plugin = release['packs'][pack].get('plugin')
        if not plugin:
            raise ValueError(f'Pack {pack} has no plugin name in src/manifest.toml.')
        item = _require(repo / 'plugins' / plugin / 'agents' / f'{role_id}.md')
        name = _markdown_name(item)
        if not name:
            raise ValueError(f'Incomplete role: {item}')
        if name in names:
            raise ValueError(f'Duplicate role name: {name}')
        names[name] = item.name
        add('claude', claude_home, Path('agents') / item.name, item.read_bytes())

    workflows = sorted((core / 'workflows').glob('*.js'))
    for item in workflows:
        add('claude', claude_home, Path('workflows') / item.name, item.read_bytes())
    info = {'packs': packs, 'roles': len(names), 'skill': str(claude_home / 'skills' / SKILL),
            'agents': str(claude_home / 'agents'), 'workflows': len(workflows)}
    return names, info


def _read_manifest(path: Path):
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except ValueError as error:
        raise ValueError(f'Install manifest is not valid JSON: {path}. Fix or remove it.') from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list):
        raise ValueError(f'Install manifest has no file list: {path}. Fix or remove it.')
    return manifest


_SHA256 = re.compile(r'[0-9a-f]{64}')


def _recorded_path(value, label) -> Path:
    """An absolute, normalized path from the install manifest; '..' could escape every check."""
    if not isinstance(value, str) or not value:
        raise ValueError(f'Install manifest has an invalid {label}: {value!r}. Fix or remove the manifest.')
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or os.path.normpath(value) != str(path):
        raise ValueError(f'Install manifest has an invalid {label}: {value}. Fix or remove the manifest.')
    return path


def _manifest_files(manifest, allowed):
    """Yield (entry, path) for files a previous install recorded. The manifest's own roots are not
    trusted: every path must have one of the shapes this installer writes (`allowed(path)`)."""
    if not manifest:
        return
    for entry in manifest['files']:
        if not isinstance(entry, dict) or not isinstance(entry.get('sha256'), str) \
                or not _SHA256.fullmatch(entry['sha256']):
            raise ValueError(f'Install manifest has an invalid file entry: {entry!r}. Fix or remove the manifest.')
        path = _recorded_path(entry.get('path'), 'file path')
        if not allowed(path):
            raise ValueError(f'Install manifest lists an unexpected file: {path}')
        yield entry, path


def _manifest_bytes(release, target, packs, with_cli, roots, entries, extra) -> bytes:
    manifest = {'name': INSTALL_NAME, 'version': release['version'], 'target': target,
                'packs': packs, 'roots': sorted(str(root) for root in roots),
                'files': sorted(entries, key=lambda entry: entry['path'])}
    if target == 'codex':
        manifest['with_cli'] = bool(with_cli)
    manifest.update({key: value for key, value in extra.items() if value})
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


_TEMP_SUFFIX = '.12345678.tmp'  # shape of the temporary name used by _write_atomic
_MAX_PATH = 259  # Windows path limit without long-path support (260 including the terminator)


def _long_paths_enabled() -> bool:
    if os.name != 'nt':
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
            return winreg.QueryValueEx(key, 'LongPathsEnabled')[0] == 1
    except OSError:
        return False


def _check_path_lengths(paths):
    """Refuse before writing anything when a path would hit the Windows path limit mid-install."""
    if _long_paths_enabled():
        return
    too_long = [str(path) for path in paths if len(str(path)) + len(_TEMP_SUFFIX) > _MAX_PATH]
    if too_long:
        raise ValueError('These paths are too long for Windows without long-path support: '
                         + ', '.join(too_long) + '. Use a shorter --codex-home, --skills-dir, --claude-home '
                         'or --bin-dir, or enable LongPathsEnabled in Windows.')


def _write_atomic(destination: Path, data: bytes):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    temporary.write_bytes(data)
    os.replace(temporary, destination)
    if destination.read_bytes() != data:
        raise IOError(f'Installed contents differ: {destination}')


def _remove_empty_dirs(files, roots):
    """Remove directories emptied by this run, but only inside directories this tool owns."""
    for directory in sorted({file.parent for file in files}, key=lambda path: len(path.parts), reverse=True):
        while any(directory.is_relative_to(root) for root in roots):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent


def install(codex_home: Path | None = None, skills_dir: Path | None = None, *, target='codex',
            packs=None, claude_home: Path | None = None, with_cli=None, bin_dir=None, force=False,
            dry_run=False, max_subagents=None, uninstall=False, prune_legacy=False,
            repo: Path = REPO) -> dict:
    """Install or update the selected targets, or uninstall them. All checks run before any write.
    A dry run never writes: it reports the plan, including conflicts a real run would stop at."""
    if target not in (*TARGETS, 'all'):
        raise ValueError('--target must be codex, claude or all.')
    targets = TARGETS if target == 'all' else (target,)
    if max_subagents is not None and (type(max_subagents) is not int or max_subagents < 1):
        raise ValueError('--max-subagents must be a positive integer.')
    if 'codex' not in targets and (with_cli or max_subagents is not None):
        raise ValueError('--with-cli and --max-subagents apply only to the codex target.')
    repo = Path(repo)
    release = _load_release(repo)
    homes = {}
    if 'codex' in targets:
        codex_home = homes['codex'] = Path(codex_home or _default_codex_home()).expanduser().resolve()
    if 'claude' in targets:
        claude_home = homes['claude'] = Path(claude_home or _default_claude_home()).expanduser().resolve()
    manifests = {t: homes[t] / INSTALL_MANIFEST for t in targets}
    previous = {t: _read_manifest(manifests[t]) for t in targets}

    skill_dirs, owned_dirs, skill_roots = {}, [], []
    if 'codex' in targets:
        before = previous['codex'] or {}
        recorded_skills = before.get('skills_dir') and _recorded_path(before['skills_dir'], 'skills_dir')
        recorded_bin = before.get('bin_dir') and _recorded_path(before['bin_dir'], 'bin_dir')
        # Without the option, a rerun keeps the directories the previous install used.
        skills_dir = Path(skills_dir or recorded_skills or _default_skills_dir()).expanduser().resolve()
        if bin_dir is None:
            bin_dir = recorded_bin or None
        skill_dirs['codex'] = skills_dir / SKILL
        skill_roots = [skills_dir / SKILL] + ([recorded_skills / SKILL] if recorded_skills else [])
        owned_dirs += [codex_home / 'tools' / 'codex-team', codex_home / INSTALL_MANIFEST.parent, *skill_roots]
    if 'claude' in targets:
        skill_dirs['claude'] = claude_home / 'skills' / SKILL
        owned_dirs += [claude_home / INSTALL_MANIFEST.parent, skill_dirs['claude']]

    def allowed(t):
        """The only places this installer writes, so a damaged manifest cannot point elsewhere."""
        if t == 'codex':
            agents, launcher = codex_home / 'agents', codex_home / 'tools' / 'codex-team'
            return lambda path: ((path.parent == agents and path.suffix == '.toml')
                                 or path.is_relative_to(launcher) or path.name == 'codex-team.cmd'
                                 or any(path.is_relative_to(root) for root in skill_roots))
        return lambda path: ((path.parent == claude_home / 'agents' and path.suffix == '.md')
                             or (path.parent == claude_home / 'workflows' and path.suffix == '.js')
                             or path.is_relative_to(skill_dirs['claude']))

    recorded = {t: list(_manifest_files(previous[t], allowed(t))) for t in targets}
    created = {}
    for t in targets:
        made = (previous[t] or {}).get('created_dirs') or []
        if not isinstance(made, list):
            raise ValueError(f'Install manifest has an invalid created_dirs list: {manifests[t]}')
        created[t] = {_recorded_path(directory, 'created directory') for directory in made}

    plan: list[_File] = []
    roots = {t: set() for t in targets}

    def add(t, root: Path, relative: Path, data: bytes, owned=True):
        destination = root / relative
        if not destination.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'{destination} resolves outside {root}, so a directory on the way is a link. '
                             'Pass --codex-home, --skills-dir or --claude-home pointing to the real directory.')
        if destination.exists() and not destination.is_file():
            raise ValueError(f'Destination is not a file: {destination}')
        plan.append(_File(destination, data, t, owned))
        if owned:
            roots[t].add(root)

    report = {'version': release['version'], 'dry_run': dry_run, 'uninstall': uninstall, 'targets': {}}
    notes = []
    guards, selected = [], {t: [] for t in targets}
    if not uninstall:
        selected = _select_packs(packs, release, targets,
                                 {t: (previous[t] or {}).get('packs') for t in targets})
        if 'codex' in targets:
            if with_cli is None:
                with_cli = bool((previous['codex'] or {}).get('with_cli'))
            limit, names, info = _plan_codex(repo, release, selected['codex'], codex_home, skills_dir,
                                             with_cli, bin_dir, max_subagents, add)
            report['max_subagents'] = limit
            report['targets']['codex'] = info
            guards.append((codex_home / 'agents', '*.toml', names, _toml_name))
        if 'claude' in targets:
            names, info = _plan_claude(repo, release, selected['claude'], claude_home, add)
            report['targets']['claude'] = info
            guards.append((claude_home / 'agents', '*.md', names, _markdown_name))
            notes.append(CLAUDE_PLUGIN_NOTE.format(
                plugin=release['packs']['core'].get('plugin', 'orchestra'),
                marketplace=release.get('marketplace', '<marketplace>')))
    elif 'codex' in targets:
        notes.append('The subagent limit in Codex config.toml is left as it is.')
    planned = [file.path for file in plan]
    if len(set(planned)) != len(planned):
        raise ValueError('Two install targets would write the same file; use separate directories.')
    planned = set(planned)

    # Files a previous install recorded that this plan no longer writes: remove them only when
    # they are unchanged since install. With --uninstall --force, back up and remove the rest too.
    removals, kept, carried, tracked = [], [], {t: [] for t in targets}, set()
    for t in targets:
        for entry, path in recorded[t]:
            tracked.add(path)
            if path in planned or path.is_symlink() or not path.is_file():
                continue
            if _sha256(path.read_bytes()) == entry['sha256']:
                removals.append((path, t, False))
            elif uninstall and force:
                removals.append((path, t, True))
            else:
                kept.append(str(path))
                carried[t].append(entry)
    # Role files no install manifest tracks (a v1 install, or copied by hand) that carry the name of
    # a role outside the selected packs: this run neither updates nor removes them unless asked to.
    unmanaged = []
    if 'codex' in targets and not uninstall:
        agents_dir = homes['codex'] / 'agents'
        unmanaged = [agents_dir / f'{role_id}.toml'
                     for role_id, pack in _role_packs(repo, release, 'codex').items()
                     if pack not in selected['codex'] and (agents_dir / f'{role_id}.toml').is_file()
                     and agents_dir / f'{role_id}.toml' not in tracked]
        if unmanaged:
            report['unmanaged_roles'] = [str(path) for path in unmanaged]
            if not prune_legacy:
                notes.append(
                    'Found role files that this installer does not manage, for roles outside the selected '
                    'packs (listed under unmanaged_roles; probably from an earlier release). They stay as '
                    'they are and may be outdated. Rerun with --packs all --force to replace them with this '
                    'release, or with --prune-legacy to back them up and remove them.')
    # Files that releases before 2.0 installed and 2.0 no longer ships: the [legacy] names, and
    # untracked files in our skill directory that this plan does not write.
    legacy = []
    for t, key in (('codex', 'codex_agents'), ('claude', 'claude_agents')):
        for name in release.get('legacy', {}).get(key, []) if t in targets else ():
            if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
                raise ValueError(f'Invalid legacy file name in src/manifest.toml: {name!r}')
            legacy.append((homes[t] / 'agents' / name, t))
    for t in targets:
        skill_dir = skill_dirs[t]
        linked = skill_dir.is_symlink() or (skill_dir.exists() and skill_dir.resolve() != skill_dir)
        if linked and prune_legacy:
            raise ValueError(f'{skill_dir} is a link; remove or update it yourself.')
        if skill_dir.is_dir() and not linked:
            legacy += [(path, t) for path in sorted(skill_dir.rglob('*'))]
    legacy = [(path, t) for path, t in legacy if path.is_file() and not path.is_symlink()
              and path not in tracked and path not in planned]
    if prune_legacy:
        removing = {path for path, _, _ in removals}
        for path, t in [(path, 'codex') for path in unmanaged] + legacy:
            if path.is_file() and not path.is_symlink() and path not in planned and path not in removing:
                removals.append((path, t, True))
                removing.add(path)
    elif legacy and not uninstall:
        report['legacy_files'] = [str(path) for path, _ in legacy]
        notes.append('Found files that a release before 2.0 installed and this release no longer ships '
                     '(listed under legacy_files). They stay as they are, and Codex or Claude Code may still '
                     'load them. Rerun with --prune-legacy to back them up and remove them.')
    if 'codex' in targets and not uninstall and not with_cli:
        old_launcher = codex_home / 'tools' / 'codex-team' / 'codex-team.mjs'
        if old_launcher.is_file() and old_launcher not in tracked:
            notes.append(f'Found a codex-team launcher that this installer does not manage in {old_launcher.parent} '
                         '(probably from an earlier release). It stays as it is and may not work with this '
                         "release's roles. Rerun with --with-cli to replace it, or delete it and its "
                         'codex-team.cmd shim yourself.')
    removing = {path for path, _, _ in removals}
    for directory, pattern, names, read_name in guards:
        _guard_role_names(directory, pattern, names, read_name, removing)

    hashes = {path: entry['sha256'] for t in targets for entry, path in recorded[t]}
    writes, conflicts = [], []
    for file in plan:
        if file.path.exists():
            current = file.path.read_bytes()
            if current == file.data:
                continue
            # A file this tool installed and nobody changed since is a plain update.
            if not (file.owned and hashes.get(file.path) == _sha256(current)):
                conflicts.append((file.path, file.target))
        writes.append(file)
    if conflicts and not force:
        if not dry_run:
            raise FileExistsError('Existing files differ; review them and rerun with --force to back them up: '
                                  + ', '.join(str(path) for path, _ in conflicts))
        notes.append('A real run stops at the conflicts listed above. Review them, then rerun with --force '
                     'to back them up and replace them.')
    _check_path_lengths([file.path for file in writes] + list(manifests.values()))

    report.update(files=len(plan), changed=len(writes), conflicts=[str(path) for path, _ in conflicts],
                  removed=[str(path) for path, _, _ in removals], kept_modified=kept)
    if dry_run:
        report['would_write'] = [str(file.path) for file in writes]
    for t in targets:
        report['targets'].setdefault(t, {})['manifest'] = str(manifests[t])
        if uninstall and not previous[t]:
            report['targets'][t]['manifest'] += ' (not found: nothing recorded to uninstall)'
    if notes:
        report['notes'] = notes
    if dry_run:
        return report

    # Directories this run creates, so that an uninstall can remove them again once they are empty.
    for file in writes + [_File(manifests[t], b'', t, False) for t in targets]:
        directory = file.path.parent
        while not directory.exists() and directory != directory.parent:
            created[file.target].add(directory)
            directory = directory.parent

    backed_up = {}
    for path, t in conflicts + [(path, t) for path, t, backup in removals if backup]:
        backed_up.setdefault(t, []).append(path)
    if backed_up:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
        report['backups'] = []
        for t, files in backed_up.items():
            backup = homes[t] / 'agent-backups' / f'{INSTALL_NAME}-{stamp}'
            for index, file in enumerate(files):
                copy = backup / str(index) / file.name
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, copy)
            (backup / 'restore-map.txt').write_text(
                '\n'.join(f'{i}/{p.name}\t{p}' for i, p in enumerate(files)), encoding='utf-8')
            report['backups'].append(str(backup))
    for path, _, _ in removals:
        path.unlink()
    for file in writes:
        _write_atomic(file.path, file.data)

    emptied, leftover_dirs = [path for path, _, _ in removals], []
    for t in targets:
        entries = [{'path': str(file.path), 'sha256': _sha256(file.data)}
                   for file in plan if file.target == t and file.owned]
        if not entries and not carried[t]:
            if manifests[t].exists():
                manifests[t].unlink()
                emptied.append(manifests[t])
            leftover_dirs += created[t]
            continue
        if carried[t]:
            roots[t].update(_recorded_path(root, 'root') for root in previous[t].get('roots', []))
        launcher = report['targets'][t].get('launcher')
        if launcher:
            launcher_dir = str(Path(launcher).parent)
        else:  # an uninstall that keeps modified files still remembers where the shim was
            launcher_dir = str(bin_dir) if uninstall and t == 'codex' and bin_dir else None
        extra = {'skills_dir': str(skills_dir) if t == 'codex' else None, 'bin_dir': launcher_dir,
                 'created_dirs': sorted(str(directory) for directory in created[t] if directory.is_dir())}
        data = _manifest_bytes(release, t, selected[t], with_cli and t == 'codex', roots[t],
                               entries + carried[t], extra)
        if not manifests[t].exists() or manifests[t].read_bytes() != data:
            _write_atomic(manifests[t], data)
    _remove_empty_dirs(emptied, owned_dirs)
    # After an uninstall, remove the directories the installs created, deepest first, if now empty.
    for directory in sorted(leftover_dirs, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return report


def _print_report(report: dict):
    for key, value in report.items():
        if key in ('targets', 'notes'):
            continue
        if isinstance(value, list):
            print(f'{key}: {len(value)}')
            for item in value:
                print(f'  {item}')
        else:
            print(f'{key}: {value}')
    for name, info in report['targets'].items():
        print(f'{name}:')
        for field, detail in info.items():
            print(f'  {field}: {", ".join(detail) if isinstance(detail, list) else detail}')
    if report.get('kept_modified'):
        print('Warning: kept files that changed since they were installed. Review and delete them yourself, '
              'or run --uninstall --force to back them up and remove them.')
    for note in report.get('notes', []):
        print(f'Note: {note}')
    if any(info.get('launcher') for info in report['targets'].values()):
        print('Run the launcher by its path, or add its directory to your user PATH.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--target', choices=['codex', 'claude', 'all'], default='codex',
                        help='Where to install (default: codex)')
    parser.add_argument('--packs', help='Comma-separated role packs or "all"; core is always included '
                                        '(default: the packs installed before, otherwise core)')
    parser.add_argument('--codex-home', type=Path, default=_default_codex_home(),
                        help='Codex home (default: CODEX_HOME or ~/.codex)')
    parser.add_argument('--skills-dir', type=Path,
                        help='Codex skills directory (default: as installed before, otherwise ~/.agents/skills)')
    parser.add_argument('--claude-home', type=Path, default=_default_claude_home(),
                        help='Claude Code config directory (default: CLAUDE_CONFIG_DIR or ~/.claude)')
    parser.add_argument('--with-cli', action=argparse.BooleanOptionalAction,
                        help='Install the optional Windows Codex launcher from extras/codex-team '
                             '(default: as installed before)')
    parser.add_argument('--bin-dir', type=Path,
                        help='Launcher shim directory (default: as installed before, otherwise APPDATA/npm)')
    parser.add_argument('--max-subagents', type=int,
                        help='Override the per-session subagent limit (positive integer; default: preserve existing or 12)')
    parser.add_argument('--force', action='store_true',
                        help='Back up and replace conflicting files; with --uninstall, also back up and remove modified files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report the plan, including conflicts, without writing files')
    parser.add_argument('--uninstall', action='store_true',
                        help='Remove the files recorded in the install manifest that are unchanged since install')
    parser.add_argument('--prune-legacy', action='store_true',
                        help='Back up and remove files that releases before 2.0 installed, including '
                             'unmanaged Codex role files of packs that are not selected')
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    args = parser.parse_args(argv)
    try:
        result = install(**vars(args))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Install failed: {error}\n')
    _print_report(result)


if __name__ == '__main__':
    main()
