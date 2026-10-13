// Static checks for the Claude Code Workflow scripts generated into plugins/orchestra/workflows.
// Workflow scripts run as an async function body (top-level await and return), so `node --check`
// cannot parse them; compile each body with AsyncFunction instead. Run: node tests/workflows.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIR = path.join(ROOT, 'plugins', 'orchestra', 'workflows');
const AsyncFunction = (async () => {}).constructor;
const files = fs.readdirSync(DIR).filter(name => name.endsWith('.js')).sort();

function readMeta(source) {
  const body = source.replace(/^export const meta =/m, 'const meta =');
  const literal = /^const meta = (\{[\s\S]*?\n\})/m.exec(body)[1];
  return { body, meta: new Function(`return ${literal}`)() };
}

test('workflow scripts exist', () => {
  // team-* names keep script installs from registering generic /review or /research commands.
  assert.deepEqual(files, ['team-research.js', 'team-review.js']);
});

for (const name of files) {
  test(`${name} compiles and declares meta`, () => {
    const source = fs.readFileSync(path.join(DIR, name), 'utf8');
    assert.match(source, /^export const meta = \{/m);
    const { body, meta } = readMeta(source);
    assert.doesNotThrow(() => new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', body));
    assert.equal(meta.name, path.basename(name, '.js'));
    assert.ok(meta.description && meta.whenToUse);
    assert.ok(Array.isArray(meta.phases) && meta.phases.every(phase => phase.title));
    // The Workflow runtime has no clock, randomness, modules or process access.
    assert.doesNotMatch(source, /Date\.now|Math\.random|\brequire\(|^import\s|\bprocess\./m);
  });
}

function markdownFiles(start) {
  if (!fs.existsSync(start)) return [];
  if (fs.statSync(start).isFile()) return [start];
  return fs.readdirSync(start, { withFileTypes: true }).flatMap(entry =>
    entry.isDirectory() ? markdownFiles(path.join(start, entry.name))
      : entry.name.endsWith('.md') ? [path.join(start, entry.name)] : []);
}

test('documented /orchestra:<name> commands exist', () => {
  const names = new Set(['orchestrate', ...files.map(name =>
    readMeta(fs.readFileSync(path.join(DIR, name), 'utf8')).meta.name)]);
  const sources = ['src/skill', 'docs', 'README.md', 'README.ko.md', 'CHANGELOG.md', 'extras/codex-team/README.md']
    .flatMap(relative => markdownFiles(path.join(ROOT, relative)));
  assert.ok(sources.length > 5);
  const unknown = [];
  for (const file of sources) {
    for (const match of fs.readFileSync(file, 'utf8').matchAll(/\/orchestra:([a-z0-9-]+)/g)) {
      if (!names.has(match[1])) unknown.push(`${path.relative(ROOT, file)}: /orchestra:${match[1]}`);
    }
  }
  assert.deepEqual(unknown, []);
});
