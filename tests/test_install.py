import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kit_install', REPO / 'scripts/install.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

RELEASE = '''version = "2.0.0"
marketplace = "codex-orchestrator-kit"
[skill]
name = "orchestrate"
[packs.core]
plugin = "orchestra"
platforms = ["claude", "codex"]
[packs.dev]
plugin = "orchestra-dev"
platforms = ["claude", "codex"]
[packs.codex-only]
platforms = ["codex"]
[legacy]
codex_agents = ["orchestrator.toml", "template-author.toml"]
'''
ROLES = {'reviewer': 'core', 'architect': 'core', 'database-engineer': 'dev', 'sites-builder': 'codex-only'}
PLUGINS = {'core': 'orchestra', 'dev': 'orchestra-dev'}


def codex_role(role_id):
    name = role_id.replace('-', '_')
    return f'name = "{name}"\ndescription = "{role_id} role"\ndeveloper_instructions = """\nWork as {name}.\n"""\n'


def claude_agent(role_id):
    return f'---\nname: {role_id}\ndescription: {role_id} role\ndisallowedTools: Agent\n---\nWork as {role_id}.\n'


def make_generated_tree(repo: Path):
    """Write a tiny stand-in for the build output so tests do not depend on the real roles."""
    files = {
        'src/manifest.toml': RELEASE,
        'skills/orchestrate/SKILL.md': '---\nname: orchestrate\n---\nCodex skill\n',
        'skills/orchestrate/agents/openai.yaml': 'interface: {}\n',
        'skills/orchestrate/references/roles/reviewer.md': 'Reviewer brief\n',
        'plugins/orchestra/skills/orchestrate/SKILL.md': '---\nname: orchestrate\n---\nClaude skill\n',
        'plugins/orchestra/skills/orchestrate/references/models.md': 'Models\n',
        'plugins/orchestra/workflows/team-review.js': 'export const meta = {name: "team-review"};\n',
    }
    for role_id, pack in ROLES.items():
        files[f'src/roles/{role_id}.toml'] = f'id = "{role_id}"\npack = "{pack}"\n'
        files[f'codex/agents/{role_id}.toml'] = codex_role(role_id)
        if pack in PLUGINS:
            files[f'plugins/{PLUGINS[pack]}/agents/{role_id}.md'] = claude_agent(role_id)
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))
    return repo


def tree(root: Path):
    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()) \
        if root.exists() else []


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = make_generated_tree(self.root / 'repo')
        self.home = self.root / 'codex'
        self.skills = self.root / 'skills'
        self.claude = self.root / 'claude'

    def install(self, home=None, skills=None, **options):
        options.setdefault('repo', self.repo)
        options.setdefault('claude_home', self.claude)
        return module.install(home or self.home, skills or self.skills, **options)

    def manifest(self, home):
        return json.loads((home / 'orchestrator-kit/install-manifest.json').read_text(encoding='utf-8'))

    def write_config(self, contents):
        self.home.mkdir(parents=True, exist_ok=True)
        path = self.home / 'config.toml'
        path.write_bytes(contents)
        return path

    # Layout, packs and the install manifest -------------------------------------------------

    def test_codex_install_is_self_contained_idempotent_and_recorded(self):
        result = self.install()
        source = self.repo / 'skills/orchestrate'
        self.assertEqual(tree(self.skills / 'orchestrate'), tree(source))
        for relative in tree(source):
            self.assertEqual((self.skills / 'orchestrate' / relative).read_bytes(),
                             (source / relative).read_bytes())
        self.assertEqual(tree(self.home / 'agents'), ['architect.toml', 'reviewer.toml'])
        self.assertEqual((self.home / 'agents/reviewer.toml').read_bytes(),
                         (self.repo / 'codex/agents/reviewer.toml').read_bytes())
        self.assertEqual(result['targets']['codex']['roles'], 2)
        self.assertEqual(result['targets']['codex']['packs'], ['core'])
        self.assertFalse(self.claude.exists())
        config = tomllib.loads((self.home / 'config.toml').read_text(encoding='utf-8'))
        self.assertEqual(config, {'agents': {'max_concurrent_threads_per_session': 12}})
        self.assertEqual(result['max_subagents'], 12)

        manifest = self.manifest(self.home)
        self.assertEqual((manifest['version'], manifest['target'], manifest['packs'], manifest['with_cli']),
                         ('2.0.0', 'codex', ['core'], False))
        recorded = {Path(entry['path']): entry['sha256'] for entry in manifest['files']}
        self.assertNotIn(self.home.resolve() / 'config.toml', recorded)
        self.assertEqual(len(recorded), len(tree(source)) + 2)
        for path, digest in recorded.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        again = self.install()
        self.assertEqual((again['changed'], again['removed'], again['kept_modified']), (0, [], []))
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)

    def test_claude_install_places_skill_agents_and_workflows(self):
        result = self.install(target='claude')
        self.assertEqual(tree(self.claude), [
            'agents/architect.md', 'agents/reviewer.md', 'orchestrator-kit/install-manifest.json',
            'skills/orchestrate/SKILL.md', 'skills/orchestrate/references/models.md', 'workflows/team-review.js'])
        self.assertEqual((self.claude / 'skills/orchestrate/SKILL.md').read_bytes(),
                         (self.repo / 'plugins/orchestra/skills/orchestrate/SKILL.md').read_bytes())
        self.assertFalse(self.home.exists())
        self.assertFalse(self.skills.exists())
        self.assertEqual(result['targets']['claude']['workflows'], 1)
        self.assertIn('never both', result['notes'][0])
        self.assertIn('/plugin install orchestra@codex-orchestrator-kit', result['notes'][0])
        manifest = self.manifest(self.claude)
        self.assertEqual((manifest['target'], manifest['packs']), ('claude', ['core']))
        self.assertNotIn('with_cli', manifest)
        self.assertEqual(self.install(target='claude')['changed'], 0)

    def test_target_all_and_pack_filtering(self):
        result = self.install(target='all', packs='all')
        self.assertEqual(result['targets']['codex']['packs'], ['core', 'dev', 'codex-only'])
        self.assertEqual(result['targets']['claude']['packs'], ['core', 'dev'])
        self.assertEqual(tree(self.home / 'agents'),
                         ['architect.toml', 'database-engineer.toml', 'reviewer.toml', 'sites-builder.toml'])
        self.assertEqual(tree(self.claude / 'agents'), ['architect.md', 'database-engineer.md', 'reviewer.md'])

        home, claude = self.root / 'codex2', self.root / 'claude2'
        result = self.install(home, self.root / 'skills2', target='all', packs='dev', claude_home=claude)
        self.assertEqual(result['targets']['codex']['packs'], ['core', 'dev'])
        self.assertEqual(tree(claude / 'agents'), ['architect.md', 'database-engineer.md', 'reviewer.md'])

        result = self.install(self.root / 'codex3', self.root / 'skills3', target='all',
                              packs='core,codex-only', claude_home=self.root / 'claude3')
        self.assertEqual(result['targets']['codex']['packs'], ['core', 'codex-only'])
        self.assertEqual(result['targets']['claude']['packs'], ['core'])

        for packs, target in (('codex-only', 'claude'), ('unknown', 'codex'), (' , ', 'codex')):
            with self.subTest(packs=packs, target=target):
                fresh = self.root / ('refused-' + target)
                with self.assertRaises(ValueError):
                    self.install(fresh, fresh / 'skills', target=target, packs=packs, claude_home=fresh)
                self.assertFalse(fresh.exists())

    def test_omitted_packs_reuse_the_installed_selection(self):
        self.install(target='all', packs='core,dev')
        result = self.install(target='all')
        self.assertEqual((result['changed'], result['removed']), (0, []))
        self.assertEqual(result['targets']['codex']['packs'], ['core', 'dev'])
        self.assertEqual(self.manifest(self.claude)['packs'], ['core', 'dev'])

    def test_update_replaces_unchanged_files_without_force(self):
        self.install(target='all')
        (self.repo / 'skills/orchestrate/SKILL.md').write_text('Codex skill v2\n', encoding='utf-8')
        (self.repo / 'plugins/orchestra/agents/reviewer.md').write_text(claude_agent('reviewer') + 'More.\n',
                                                                         encoding='utf-8')
        result = self.install(target='all')
        self.assertEqual((result['changed'], result['conflicts']), (2, []))
        self.assertNotIn('backups', result)
        self.assertEqual((self.skills / 'orchestrate/SKILL.md').read_text(encoding='utf-8'), 'Codex skill v2\n')
        recorded = {Path(e['path']): e['sha256'] for e in self.manifest(self.claude)['files']}
        reviewer = (self.claude / 'agents/reviewer.md').resolve()
        self.assertEqual(recorded[reviewer], hashlib.sha256(reviewer.read_bytes()).hexdigest())

    def test_update_removes_unchanged_orphans_and_keeps_modified_ones(self):
        self.install(target='all', packs='core,dev')
        reference = self.repo / 'skills/orchestrate/references/roles/reviewer.md'
        reference.unlink()
        modified = self.home / 'agents/database-engineer.toml'
        modified.write_text(codex_role('database-engineer') + '# local note\n', encoding='utf-8')
        result = self.install(target='all', packs='core')
        self.assertFalse((self.claude / 'agents/database-engineer.md').exists())
        self.assertFalse((self.skills / 'orchestrate/references').exists())
        self.assertTrue((self.skills / 'orchestrate/SKILL.md').exists())
        self.assertIn('# local note', modified.read_text(encoding='utf-8'))
        self.assertEqual(result['kept_modified'], [str(modified.resolve())])
        self.assertEqual(len(result['removed']), 2)
        self.assertNotIn('backups', result)
        # The kept file stays tracked so a later uninstall can deal with it.
        tracked = [Path(entry['path']) for entry in self.manifest(self.home)['files']]
        self.assertIn(modified.resolve(), tracked)

    def test_uninstall_removes_unmodified_files_and_keeps_modified_ones(self):
        self.install(target='all', packs='core,dev')
        user_file = self.claude / 'agents/my-own.md'
        user_file.write_text('---\nname: my-own\n---\n', encoding='utf-8')
        modified = self.claude / 'agents/reviewer.md'
        modified.write_text('customized', encoding='utf-8')
        config = (self.home / 'config.toml').read_bytes()

        dry = self.install(target='all', uninstall=True, dry_run=True)
        self.assertTrue(dry['removed'])
        self.assertTrue((self.claude / 'agents/architect.md').exists())

        result = self.install(target='all', uninstall=True)
        self.assertEqual(result['kept_modified'], [str(modified.resolve())])
        self.assertEqual(tree(self.claude), ['agents/my-own.md', 'agents/reviewer.md',
                                             'orchestrator-kit/install-manifest.json'])
        self.assertEqual(tree(self.home), ['config.toml'])
        self.assertEqual((self.home / 'config.toml').read_bytes(), config)
        self.assertFalse((self.skills / 'orchestrate').exists())
        self.assertFalse(self.skills.exists())  # the install created it, and it is empty again

        forced = self.install(target='all', uninstall=True, force=True)
        self.assertEqual(forced['removed'], [str(modified.resolve())])
        self.assertEqual(tree(self.claude / 'agents'), ['my-own.md'])
        self.assertFalse((self.claude / 'orchestrator-kit').exists())
        backup = Path(forced['backups'][0])
        self.assertEqual((backup / '0/reviewer.md').read_text(encoding='utf-8'), 'customized')
        self.assertIn(str(modified.resolve()), (backup / 'restore-map.txt').read_text(encoding='utf-8'))
        nothing = self.install(target='all', uninstall=True)
        self.assertEqual(nothing['removed'], [])
        self.assertIn('not found', nothing['targets']['codex']['manifest'])

    def test_prune_legacy_backs_up_and_removes_pre_2_0_files(self):
        agents = self.home / 'agents'
        agents.mkdir(parents=True)
        (agents / 'orchestrator.toml').write_text(codex_role('orchestrator'), encoding='utf-8')
        (agents / 'personal.toml').write_text(codex_role('personal'), encoding='utf-8')
        leftover = self.skills / 'orchestrate/references/roles/reviewer.toml'
        leftover.parent.mkdir(parents=True)
        leftover.write_text('v1 role', encoding='utf-8')

        self.install()
        self.assertTrue((agents / 'orchestrator.toml').exists())
        self.assertTrue(leftover.exists())

        result = self.install(prune_legacy=True)
        self.assertFalse((agents / 'orchestrator.toml').exists())
        self.assertFalse(leftover.exists())
        self.assertTrue((agents / 'personal.toml').exists())
        self.assertTrue((self.skills / 'orchestrate/references/roles/reviewer.md').exists())
        self.assertEqual(len(result['removed']), 2)
        backup = Path(result['backups'][0])
        self.assertTrue(backup.is_relative_to(self.home.resolve() / 'agent-backups'))
        restore = (backup / 'restore-map.txt').read_text(encoding='utf-8')
        self.assertIn(str((agents / 'orchestrator.toml').resolve()), restore)
        self.assertIn(str(leftover.resolve()), restore)
        self.assertEqual(self.install(prune_legacy=True)['removed'], [])

    def test_unmanaged_roles_outside_selected_packs_are_reported_then_pruned(self):
        agents = self.home / 'agents'
        agents.mkdir(parents=True)
        v1_role = agents / 'database-engineer.toml'
        v1_role.write_text('name = "database_engineer"\n', encoding='utf-8')

        result = self.install()
        self.assertEqual(result['unmanaged_roles'], [str(v1_role.resolve())])
        self.assertTrue(any('--packs all --force' in note and '--prune-legacy' in note for note in result['notes']))
        self.assertEqual(v1_role.read_text(encoding='utf-8'), 'name = "database_engineer"\n')
        self.assertNotIn(str(v1_role.resolve()), [e['path'] for e in self.manifest(self.home)['files']])

        pruned = self.install(prune_legacy=True)
        self.assertEqual(pruned['removed'], [str(v1_role.resolve())])
        self.assertFalse(v1_role.exists())
        self.assertIn(str(v1_role.resolve()), (Path(pruned['backups'][0]) / 'restore-map.txt').read_text(encoding='utf-8'))
        self.assertTrue(Path(pruned['backups'][0]).name.startswith('orchestrator-kit-'))
        self.assertNotIn('unmanaged_roles', self.install())

    def test_packs_all_force_replaces_unmanaged_roles(self):
        v1_role = self.home / 'agents/database-engineer.toml'
        v1_role.parent.mkdir(parents=True)
        v1_role.write_text('name = "database_engineer"\n', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.install(packs='all')
        result = self.install(packs='all', force=True)
        self.assertNotIn('unmanaged_roles', result)
        self.assertEqual(v1_role.read_bytes(), (self.repo / 'codex/agents/database-engineer.toml').read_bytes())

    def test_dry_run_writes_nothing(self):
        legacy = self.home / 'agents/template-author.toml'
        legacy.parent.mkdir(parents=True)
        legacy.write_text(codex_role('template-author'), encoding='utf-8')
        before = tree(self.root)
        result = self.install(target='all', packs='all', prune_legacy=True, dry_run=True)
        self.assertGreater(result['changed'], 0)
        self.assertEqual(result['removed'], [str(legacy.resolve())])
        self.assertEqual(tree(self.root), before)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['codex', 'repo'])

    def test_conflict_refused_without_partial_write_and_force_backs_up(self):
        skill_file = self.skills / 'orchestrate/SKILL.md'
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text('local customization', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.install()
        self.assertEqual(skill_file.read_text(encoding='utf-8'), 'local customization')
        self.assertFalse(self.home.exists())
        result = self.install(force=True)
        backups = list(Path(result['backups'][0]).glob('*/SKILL.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), 'local customization')

        # A file changed after install is a conflict too, not a silent update.
        self.install(target='claude')
        agent = self.claude / 'agents/architect.md'
        agent.write_text('edited', encoding='utf-8')
        (self.repo / 'plugins/orchestra/agents/architect.md').write_text(claude_agent('architect') + 'v2\n',
                                                                          encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.install(target='claude')
        self.assertEqual(agent.read_text(encoding='utf-8'), 'edited')

    def test_duplicate_role_file_refused(self):
        directory = self.home / 'agents'
        directory.mkdir(parents=True)
        (directory / 'another.toml').write_text('name="reviewer"', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.install(force=True)
        self.assertFalse(self.skills.exists())
        agents = self.claude / 'agents'
        agents.mkdir(parents=True)
        (agents / 'mine.md').write_text('---\nname: "architect"\n---\nmine\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'architect'):
            self.install(target='claude', force=True)
        self.assertEqual(tree(self.claude), ['agents/mine.md'])

    def test_missing_generated_output_and_unsafe_records_are_refused(self):
        (self.repo / 'codex/agents/architect.toml').unlink()
        with self.assertRaisesRegex(ValueError, 'build.py'):
            self.install()
        self.assertFalse(self.home.exists())

        self.install(target='claude')
        path = self.claude / 'orchestrator-kit/install-manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['files'].append({'path': str(self.root / 'repo/src/manifest.toml'), 'sha256': '0' * 64})
        path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unexpected file'):
            self.install(target='claude', uninstall=True, force=True)
        self.assertTrue((self.repo / 'src/manifest.toml').exists())

        (self.repo / 'codex/agents/architect.toml').write_text(codex_role('architect'), encoding='utf-8')
        release = self.repo / 'src/manifest.toml'
        release.write_text(RELEASE.replace('"template-author.toml"', '"../config.toml"'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'legacy'):
            self.install(prune_legacy=True)

    def test_codex_only_options_rejected_for_claude_target(self):
        for options in ({'with_cli': True}, {'max_subagents': 4}):
            with self.subTest(options=options):
                with self.assertRaisesRegex(ValueError, 'codex target'):
                    self.install(target='claude', **options)
                self.assertFalse(self.claude.exists())

    # Codex config.toml subagent limit ---------------------------------------------------------

    def test_existing_config_requires_force_and_keeps_unrelated_bytes(self):
        original = (b'\xef\xbb\xbf# personal settings\r\nmodel = "chosen-model"\r\n'
                    b'\r\n[agents] # team\r\nmax_depth = 2 # keep this\r\n'
                    b'\r\n[profiles.work]\r\nmodel_reasoning_effort = "high"\r\n')
        path = self.write_config(original)
        with self.assertRaisesRegex(FileExistsError, '--force'):
            self.install()
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(self.skills.exists())
        self.assertFalse((self.home / 'agents').exists())
        report = self.install(force=True)
        expected = original.replace(b'[agents] # team\r\n',
                                    b'[agents] # team\r\nmax_concurrent_threads_per_session = 12\r\n')
        self.assertEqual(path.read_bytes(), expected)
        backups = list(Path(report['backups'][0]).glob('*/config.toml'))
        self.assertEqual([backup.read_bytes() for backup in backups], [original])
        self.assertEqual(self.install()['changed'], 0)

    def test_config_without_agents_section_preserves_settings(self):
        original = b'# personal settings\nmodel = "chosen-model"\n[profiles.work]\nmodel = "other"'
        path = self.write_config(original)
        self.install(force=True)
        self.assertEqual(path.read_bytes(), original + b'\n[agents]\nmax_concurrent_threads_per_session = 12\n')
        parsed = tomllib.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(parsed['profiles']['work'], {'model': 'other'})

    def test_existing_explicit_limits_are_preserved_without_force(self):
        cases = [
            b'[agents]\nmax_concurrent_threads_per_session = 7 # custom\n',
            b'[agents]\nmax_threads = 7 # legacy\n',
            b'agents.max_concurrent_threads_per_session = 7\n',
            b'agents.max_threads = 7\n',
            b'agents = { max_threads = 7, max_depth = 2 }\n',
        ]
        for index, original in enumerate(cases):
            with self.subTest(config=original):
                home = self.root / str(index)
                home.mkdir()
                path = home / 'config.toml'
                path.write_bytes(original)
                result = self.install(home, self.root / f'skills{index}')
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(result['max_subagents'], 7)

    def test_override_updates_current_or_legacy_setting_and_preserves_comments(self):
        cases = [
            (b'[agents]\nmax_concurrent_threads_per_session = 7 # chosen\n',
             b'[agents]\nmax_concurrent_threads_per_session = 20 # chosen\n'),
            (b'[agents]\nmax_threads = 7 # chosen\nmax_depth = 2\n',
             b'[agents]\nmax_concurrent_threads_per_session = 20 # chosen\nmax_depth = 2\n'),
            (b'agents.max_threads = 0x7 # chosen\n',
             b'agents.max_concurrent_threads_per_session = 20 # chosen\n'),
            (b'[agents]\nmax_threads = 5 # old\nmax_concurrent_threads_per_session = 7 # new\n',
             b'[agents]\n# old\nmax_concurrent_threads_per_session = 20 # new\n'),
            (b'["agents"]\n"max_threads" = 7',
             b'["agents"]\nmax_concurrent_threads_per_session = 20'),
        ]
        for index, (original, expected) in enumerate(cases):
            with self.subTest(config=original):
                home = self.root / str(index)
                skills = self.root / f'skills{index}'
                home.mkdir()
                path = home / 'config.toml'
                path.write_bytes(original)
                report = self.install(home, skills, max_subagents=20, force=True)
                self.assertEqual(path.read_bytes(), expected)
                parsed = tomllib.loads(path.read_text(encoding='utf-8'))['agents']
                self.assertEqual(parsed['max_concurrent_threads_per_session'], 20)
                self.assertNotIn('max_threads', parsed)
                self.assertEqual(report['max_subagents'], 20)
                self.assertEqual(self.install(home, skills, max_subagents=20)['changed'], 0)

    def test_root_dotted_settings_and_implicit_agents_parent(self):
        cases = [
            b'agents.max_depth = 2\n[profiles.work]\nmodel = "other"\n',
            b'"agents" . "max_depth" = 2',
            b'[agents.worker]\ndescription = "specialist"\n',
            b'[agents] # no newline',
        ]
        for original in cases:
            with self.subTest(config=original):
                updated, limit = module._config_with_limit(original, None)
                parsed = tomllib.loads(updated.decode('utf-8'))
                self.assertEqual(parsed['agents'].pop('max_concurrent_threads_per_session'), 12)
                expected = tomllib.loads(original.decode('utf-8'))
                expected.setdefault('agents', {})
                self.assertEqual(parsed, expected)
                self.assertEqual(limit, 12)

    def test_multiline_values_do_not_masquerade_as_agent_settings(self):
        original = (b'note = """\n[agents]\nmax_threads = 4\n"""\n'
                    b'items = [\n  "[agents]", # keep\n  "value"\n]\n'
                    b'[agents]\nmax_threads = 7 # real\n')
        updated, _ = module._config_with_limit(original, 15)
        self.assertEqual(updated, original.replace(b'max_threads = 7',
                                                   b'max_concurrent_threads_per_session = 15'))

    def test_unrelated_nan_values_survive_config_edits(self):
        original = b'custom_threshold = nan\nvalues = [nan, +nan, -nan]\n'
        updated, _ = module._config_with_limit(original, None)
        self.assertEqual(updated, original + b'\n[agents]\nmax_concurrent_threads_per_session = 12\n')
        with_legacy = original + b'[agents]\nmax_threads = 4\n'
        updated, _ = module._config_with_limit(with_legacy, 12)
        self.assertEqual(updated, with_legacy.replace(b'max_threads = 4',
                                                      b'max_concurrent_threads_per_session = 12'))

    def test_config_dry_run_backs_up_only_when_actually_writing(self):
        original = b'model = "chosen-model"\n'
        path = self.write_config(original)
        report = self.install(force=True, dry_run=True, max_subagents=9)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.home.iterdir()), [path])
        self.assertFalse(self.skills.exists())
        self.assertEqual(report['max_subagents'], 9)
        self.assertNotIn('backups', report)

    def test_invalid_limits_and_unsupported_config_do_not_write(self):
        for limit in (0, -1, True, 1.5, '12'):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    self.install(max_subagents=limit, force=True)
                self.assertFalse(self.home.exists())
                self.assertFalse(self.skills.exists())
        for original in (b'[agents', b'agents = { max_depth = 2 }\n',
                         b'agents = { max_threads = 7 }\n', b'agents = 7\n',
                         b'[agents]\nmax_threads = true\n'):
            with self.subTest(config=original):
                path = self.write_config(original)
                with self.assertRaises(ValueError):
                    self.install(max_subagents=8, force=True)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(self.home.iterdir()), [path])
                self.assertFalse(self.skills.exists())

    # Dry runs, earlier releases and damaged inputs ---------------------------------------------

    def test_dry_run_reports_conflicts_without_force(self):
        config = self.write_config(b'model = "x"\n')
        skill_file = self.skills / 'orchestrate/SKILL.md'
        skill_file.parent.mkdir(parents=True)
        skill_file.write_bytes(b'local customization\n')
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}

        report = self.install(dry_run=True)
        self.assertEqual(sorted(report['conflicts']), sorted([str(config.resolve()), str(skill_file.resolve())]))
        self.assertIn(str((self.home / 'agents/reviewer.toml').resolve()), report['would_write'])
        self.assertTrue(any('real run stops' in note and '--force' in note for note in report['notes']))
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)

        cli = subprocess.run(
            [sys.executable, str(REPO / 'scripts/install.py'), '--dry-run', '--codex-home', str(self.home),
             '--skills-dir', str(self.skills), '--claude-home', str(self.claude)],
            capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONUTF8': '1'})
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn(f'  {config.resolve()}', cli.stdout.splitlines())
        self.assertIn('Note: A real run stops', cli.stdout)
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)
        with self.assertRaises(FileExistsError):
            self.install()

    def test_v1_leftovers_are_reported_without_prune_legacy(self):
        agents = self.home / 'agents'
        agents.mkdir(parents=True)
        (agents / 'orchestrator.toml').write_text(codex_role('orchestrator'), encoding='utf-8')
        leftover = self.skills / 'orchestrate/references/workflows.md'
        leftover.parent.mkdir(parents=True)
        leftover.write_text('v1 workflows', encoding='utf-8')
        launcher = self.home / 'tools/codex-team/codex-team.mjs'
        launcher.parent.mkdir(parents=True)
        launcher.write_text('// v1 launcher', encoding='utf-8')

        report = self.install(packs='all', force=True)
        self.assertEqual(sorted(report['legacy_files']),
                         sorted([str((agents / 'orchestrator.toml').resolve()), str(leftover.resolve())]))
        self.assertTrue(any('--prune-legacy' in note and 'legacy_files' in note for note in report['notes']))
        self.assertTrue(any('codex-team launcher' in note and '--with-cli' in note for note in report['notes']))
        self.assertTrue(leftover.exists() and launcher.exists())

        pruned = self.install(prune_legacy=True)
        self.assertNotIn('legacy_files', pruned)
        self.assertFalse(leftover.exists() or (agents / 'orchestrator.toml').exists())

    def test_claude_legacy_names_are_pruned(self):
        release = self.repo / 'src/manifest.toml'
        release.write_text(RELEASE + 'claude_agents = ["orchestrator.md"]\n', encoding='utf-8')
        agents = self.claude / 'agents'
        agents.mkdir(parents=True)
        (agents / 'orchestrator.md').write_text('---\nname: orchestrator\n---\n', encoding='utf-8')
        report = self.install(target='claude')
        self.assertEqual(report['legacy_files'], [str((agents / 'orchestrator.md').resolve())])
        self.install(target='claude', prune_legacy=True)
        self.assertFalse((agents / 'orchestrator.md').exists())

    def test_damaged_manifest_entries_are_refused(self):
        self.install(target='claude')
        path = self.claude / 'orchestrator-kit/install-manifest.json'
        original = path.read_text(encoding='utf-8')
        victim = self.root / 'victim.txt'
        victim.write_bytes(b'keep me')
        digest = hashlib.sha256(b'keep me').hexdigest()
        escape = str(self.claude.resolve() / 'agents') + os.sep + '..' + os.sep + '..' + os.sep + 'victim.txt'
        for name, entry, roots in (
                ('dot-dot path', {'path': escape, 'sha256': digest}, None),
                ('outside every install location', {'path': str(victim.resolve()), 'sha256': digest},
                 [str(Path(victim.resolve().anchor))]),
                ('not an object', 'victim.txt', None),
                ('bad hash', {'path': str((self.claude / 'agents/architect.md').resolve()), 'sha256': 'x'}, None)):
            with self.subTest(name):
                manifest = json.loads(original)
                manifest['files'].append(entry)
                if roots:
                    manifest['roots'] = roots
                path.write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Install manifest'):
                    self.install(target='claude', uninstall=True, force=True)
                self.assertEqual(victim.read_bytes(), b'keep me')

    def test_role_sources_follow_the_build_rules(self):
        reviewer = self.repo / 'src/roles/reviewer.toml'
        reviewer.write_bytes(b'\xef\xbb\xbf' + reviewer.read_bytes().replace(b'\n', b'\r\n'))
        (self.repo / 'src/roles/_draft.toml').write_bytes(b'not = [valid')
        self.assertEqual(self.install()['targets']['codex']['roles'], 2)
        (self.repo / 'src/roles/broken.toml').write_bytes(b'id = \n')
        with self.assertRaisesRegex(ValueError, 'broken.toml'):
            self.install()

    def test_unreadable_user_files_are_named(self):
        agents = self.home / 'agents'
        agents.mkdir(parents=True)
        mine = agents / 'mine.toml'
        mine.write_bytes(b'description = unquoted\n')
        with self.assertRaisesRegex(ValueError, 'mine.toml'):
            self.install(force=True)
        mine.unlink()
        for data, message in ((b'\xff\xfem\x00o\x00', 'UTF-16'), (b'model = "\xb0\xa1"\n', 'UTF-8'),
                              (b'model = "a"\nmodel = "b"\n', 'not valid TOML')):
            with self.subTest(message):
                config = self.write_config(data)
                with self.assertRaisesRegex(ValueError, f'config.toml.*{message}|{message}.*config.toml'):
                    self.install(force=True)
                self.assertEqual(config.read_bytes(), data)

    def test_rerun_keeps_the_skills_directory_of_the_previous_install(self):
        custom = self.root / 'custom-skills'
        self.install(skills=custom)
        self.assertEqual(self.manifest(self.home)['skills_dir'], str(custom.resolve()))
        with mock.patch.object(module, '_default_skills_dir', return_value=self.root / 'default-skills'):
            result = module.install(self.home, None, repo=self.repo, claude_home=self.claude)
        self.assertEqual((result['changed'], result['removed']), (0, []))
        self.assertEqual(result['targets']['codex']['skill'], str(custom.resolve() / 'orchestrate'))
        self.assertFalse((self.root / 'default-skills').exists())

    def test_existing_directories_survive_uninstall(self):
        self.skills.mkdir()
        (self.home / 'agents').mkdir(parents=True)
        self.install()
        self.install(uninstall=True)
        self.assertTrue(self.skills.is_dir())
        self.assertTrue((self.home / 'agents').is_dir())
        self.assertEqual(tree(self.home), ['config.toml'])

    def test_launcher_shim_uses_the_console_code_page(self):
        home = Path('C:/Users/홍길동/.codex')
        shim = module._launcher_shim(home, 'C:/Py 100%/python.exe', 'C:/node/node.exe', 'cp949')
        text = shim.decode('cp949')
        self.assertIn('set "CODEX_HOME=' + str(home) + '"\r\n', text)
        self.assertIn('C:/Py 100%%/python.exe', text)
        self.assertTrue(text.startswith('@echo off\r\n') and text.endswith('" %*\r\n'))
        self.assertIn(str(home / 'tools' / 'codex-team' / 'codex-team.mjs'), text)
        with self.assertRaisesRegex(ValueError, 'cp437'):
            module._launcher_shim(home, 'python.exe', 'node.exe', 'cp437')

    def test_too_long_paths_are_refused_before_writing(self):
        deep = self.root / ('d' * 120) / ('e' * 120)
        with mock.patch.object(module, '_long_paths_enabled', return_value=False):
            with self.assertRaisesRegex(ValueError, 'too long'):
                self.install(skills=deep)
        self.assertFalse(self.home.exists())

    def test_cli_rejects_invalid_limit_without_writing(self):
        for limit in ('0', '-1', 'not-a-number'):
            with self.subTest(limit=limit):
                result = subprocess.run(
                    [sys.executable, str(REPO / 'scripts/install.py'),
                     '--codex-home', str(self.home), '--skills-dir', str(self.skills),
                     '--claude-home', str(self.claude), '--max-subagents', limit],
                    capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('--max-subagents', result.stderr)
                self.assertFalse(self.home.exists())
                self.assertFalse(self.skills.exists())


class RealRepositoryTests(unittest.TestCase):
    """Install the real generated outputs (not the stand-in tree) into temporary homes."""

    def test_install_rerun_and_uninstall_every_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home, skills, claude = root / 'codex', root / 'skills', root / 'claude'
            options = dict(target='all', packs='all', claude_home=claude, repo=REPO)
            first = module.install(home, skills, **options)
            self.assertEqual(first['conflicts'], [])
            self.assertEqual(first['targets']['codex']['roles'], 35)
            self.assertEqual(first['targets']['claude']['roles'], 33)
            self.assertEqual(first['targets']['claude']['workflows'], 2)
            self.assertEqual(module.install(home, skills, **options)['changed'], 0)
            module.install(home, skills, target='all', claude_home=claude, repo=REPO, uninstall=True)
            self.assertEqual(tree(root), ['codex/config.toml'])


if __name__ == '__main__':
    unittest.main()
