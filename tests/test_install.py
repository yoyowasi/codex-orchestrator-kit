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
        self.assertEqual(result['roles'], 20)
        roles = list((self.home / 'agents').glob('*.toml'))
        self.assertEqual(len(roles), 20)
        for role in roles:
            self.assertEqual(role.read_bytes(), (self.skills / 'orchestrate/references/roles' / role.name).read_bytes())
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
        self.assertGreater(result['changed'], 20)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_duplicate_role_file_refused(self):
        directory = self.home / 'agents'
        directory.mkdir(parents=True)
        (directory / 'another.toml').write_text('name="backend_developer"', encoding='utf-8')
        with self.assertRaises(ValueError):
            module.install(self.home, self.skills, force=True)
        self.assertFalse(self.skills.exists())

    def test_role_models_allow_task_selection(self):
        for file in (REPO / 'skills/orchestrate/references/roles').glob('*.toml'):
            role = tomllib.loads(file.read_text(encoding='utf-8'))
            if role['name'] == 'orchestrator':
                self.assertEqual((role['model'], role['model_reasoning_effort']), ('gpt-6-astra', 'high'))
            else:
                self.assertNotIn('model', role)
                self.assertNotIn('model_reasoning_effort', role)


if __name__ == '__main__':
    unittest.main()
