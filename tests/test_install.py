import importlib.util
from pathlib import Path
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
        self.assertFalse((self.home / 'config.toml').exists())

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
