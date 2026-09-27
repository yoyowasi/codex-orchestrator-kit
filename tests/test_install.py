import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kit_install', REPO / 'scripts/install.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'codex'
        self.skills = self.root / 'skills'

    def test_install_is_self_contained_and_idempotent(self):
        result = module.install(self.home, self.skills)
        source = REPO / 'skills/orchestrate'
        expected_roles = {file.name for file in (source / 'references/roles').glob('*.toml')}
        self.assertTrue(expected_roles)
        self.assertEqual(result['roles'], len(expected_roles))
        roles = list((self.home / 'agents').glob('*.toml'))
        self.assertEqual({role.name for role in roles}, expected_roles)
        for role in roles:
            self.assertEqual(role.read_bytes(), (self.skills / 'orchestrate/references/roles' / role.name).read_bytes())
        for file in source.rglob('*'):
            if file.is_file():
                installed = self.skills / 'orchestrate' / file.relative_to(source)
                self.assertEqual(installed.read_bytes(), file.read_bytes())
        again = module.install(self.home, self.skills)
        self.assertEqual(again['changed'], 0)
        config = tomllib.loads((self.home / 'config.toml').read_text(encoding='utf-8'))
        self.assertEqual(config, {'agents': {'max_concurrent_threads_per_session': 12}})
        self.assertEqual(result['max_subagents'], 12)

    def write_config(self, contents):
        self.home.mkdir(parents=True, exist_ok=True)
        path = self.home / 'config.toml'
        path.write_bytes(contents)
        return path

    def test_existing_config_requires_force_and_keeps_unrelated_bytes(self):
        original = (b'\xef\xbb\xbf# personal settings\r\nmodel = "chosen-model"\r\n'
                    b'\r\n[agents] # team\r\nmax_depth = 2 # keep this\r\n'
                    b'\r\n[profiles.work]\r\nmodel_reasoning_effort = "high"\r\n')
        path = self.write_config(original)
        with self.assertRaisesRegex(FileExistsError, '--force'):
            module.install(self.home, self.skills)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(self.skills.exists())
        self.assertFalse((self.home / 'agents').exists())
        report = module.install(self.home, self.skills, force=True)
        expected = original.replace(b'[agents] # team\r\n',
                                    b'[agents] # team\r\nmax_concurrent_threads_per_session = 12\r\n')
        self.assertEqual(path.read_bytes(), expected)
        backups = list(Path(report['backup']).glob('*/config.toml'))
        self.assertEqual([backup.read_bytes() for backup in backups], [original])
        self.assertEqual(module.install(self.home, self.skills)['changed'], 0)

    def test_config_without_agents_section_preserves_settings(self):
        original = b'# personal settings\nmodel = "chosen-model"\n[profiles.work]\nmodel = "other"'
        path = self.write_config(original)
        module.install(self.home, self.skills, force=True)
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
                result = module.install(home, self.skills)
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
                home.mkdir()
                path = home / 'config.toml'
                path.write_bytes(original)
                report = module.install(home, self.skills, max_subagents=20, force=True)
                self.assertEqual(path.read_bytes(), expected)
                parsed = tomllib.loads(path.read_text(encoding='utf-8'))['agents']
                self.assertEqual(parsed['max_concurrent_threads_per_session'], 20)
                self.assertNotIn('max_threads', parsed)
                self.assertEqual(report['max_subagents'], 20)
                self.assertEqual(module.install(home, self.skills, max_subagents=20)['changed'], 0)

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
        report = module.install(self.home, self.skills, force=True, dry_run=True, max_subagents=9)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.home.iterdir()), [path])
        self.assertFalse(self.skills.exists())
        self.assertEqual(report['max_subagents'], 9)
        self.assertNotIn('backup', report)

    def test_invalid_limits_and_unsupported_config_do_not_write(self):
        for limit in (0, -1, True, 1.5, '12'):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    module.install(self.home, self.skills, max_subagents=limit, force=True)
                self.assertFalse(self.home.exists())
                self.assertFalse(self.skills.exists())
        for original in (b'[agents', b'agents = { max_depth = 2 }\n',
                         b'agents = { max_threads = 7 }\n', b'agents = 7\n',
                         b'[agents]\nmax_threads = true\n'):
            with self.subTest(config=original):
                path = self.write_config(original)
                with self.assertRaises(ValueError):
                    module.install(self.home, self.skills, max_subagents=8, force=True)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(self.home.iterdir()), [path])
                self.assertFalse(self.skills.exists())

    def test_cli_rejects_invalid_limit_without_writing(self):
        for limit in ('0', '-1', 'not-a-number'):
            with self.subTest(limit=limit):
                result = subprocess.run(
                    [sys.executable, str(REPO / 'scripts/install.py'),
                     '--codex-home', str(self.home), '--skills-dir', str(self.skills),
                     '--max-subagents', limit], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('--max-subagents', result.stderr)
                self.assertFalse(self.home.exists())
                self.assertFalse(self.skills.exists())

    def test_conflict_refused_without_partial_write_and_force_backs_up(self):
        skill_file = self.skills / 'orchestrate/SKILL.md'
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text('local customization', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            module.install(self.home, self.skills)
        self.assertEqual(skill_file.read_text(encoding='utf-8'), 'local customization')
        self.assertFalse(self.home.exists())
        result = module.install(self.home, self.skills, force=True)
        backups = list(Path(result['backup']).glob('*/SKILL.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), 'local customization')

    def test_dry_run_writes_nothing(self):
        result = module.install(self.home, self.skills, dry_run=True)
        self.assertGreater(result['changed'], 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_duplicate_role_file_refused(self):
        directory = self.home / 'agents'
        directory.mkdir(parents=True)
        (directory / 'another.toml').write_text('name="backend_developer"', encoding='utf-8')
        with self.assertRaises(ValueError):
            module.install(self.home, self.skills, force=True)
        self.assertFalse(self.skills.exists())

    def test_role_models_allow_task_selection(self):
        module.install(self.home, self.skills)
        for file in (self.home / 'agents').glob('*.toml'):
            role = tomllib.loads(file.read_text(encoding='utf-8'))
            with self.subTest(role=role['name']):
                self.assertNotIn('model', role)
                self.assertNotIn('model_reasoning_effort', role)


if __name__ == '__main__':
    unittest.main()
