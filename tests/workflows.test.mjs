// Static checks for generated Claude Code Workflows and mocked execution of workflow sources.
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

test('research only synthesizes supported or narrowed partial claims', async t => {
  const { body } = readMeta(fs.readFileSync(path.join(ROOT, 'src', 'workflows', 'team-research.js'), 'utf8'));
  const run = new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', body);
  const cases = [
    { name: 'missing correction', status: 'partly supported', kept: false },
    { name: 'empty correction', status: 'partly supported', correctedClaim: '', kept: false },
    { name: 'whitespace correction', status: 'partly supported', correctedClaim: ' \t\n ', kept: false },
    { name: 'narrowed partial', status: 'partly supported', correctedClaim: 'Feature X is supported in version 2.', kept: true },
    { name: 'supported', status: 'supported', kept: true },
    { name: 'unsupported', status: 'unsupported', kept: false },
    { name: 'unverifiable', status: 'unverifiable', kept: false },
  ];
  for (const item of cases) {
    await t.test(item.name, async () => {
      const claim = { claim: 'Feature X is supported in every version.', url: 'https://example.com/release-notes', date: '2026-10-13', confidence: 'confirmed' };
      const verdict = { status: item.status, note: 'The source only mentions version 2.' };
      if (Object.hasOwn(item, 'correctedClaim')) verdict.correctedClaim = item.correctedClaim;
      let synthesisPrompt;
      const agent = async (prompt, options) => {
        if (options.label === 'plan') return { subQuestions: [{ question: 'Which versions support Feature X?', evidence: 'release notes' }] };
        if (options.label.startsWith('research#')) return { claims: [claim], gaps: [] };
        if (options.label.startsWith('verify#')) return verdict;
        assert.equal(options.label, 'synthesize');
        synthesisPrompt = prompt;
        return 'mock answer';
      };
      const parallel = tasks => Promise.all(tasks.map(task => task()));
      const pipeline = (items, ...stages) => Promise.all(items.map(async (item, i) => {
        let value = item;
        for (const stage of stages) value = await stage(value, item, i);
        return value;
      }));
      const result = await run('Which versions support Feature X?', agent, parallel, pipeline, () => {}, () => {});
      assert.equal(result.claims.length, item.kept ? 1 : 0);
      assert.equal(result.dropped.length, item.kept ? 0 : 1);
      const verified = synthesisPrompt.split('Verified claims (cite by number):\n')[1].split('\n\nResearch gaps:')[0];
      if (item.kept) {
        assert.equal(result.claims[0].status, item.status);
        assert.ok(verified.includes(item.correctedClaim || claim.claim));
      } else {
        assert.equal(verified, '(none)');
        assert.equal(result.dropped[0].status, item.status === 'partly supported' ? 'unverifiable' : item.status);
        assert.ok(result.dropped[0].note.includes('The source only mentions version 2.'));
        if (item.status === 'partly supported') assert.match(result.dropped[0].note, /correct/i);
      }
    });
  }
});

const parallel = tasks => Promise.all(tasks.map(task => task()));
const pipeline = (items, ...stages) => Promise.all(items.map(async (item, i) => {
  let value = item;
  for (const stage of stages) value = await stage(value, item, i);
  return value;
}));

function reviewRunner() {
  const { body } = readMeta(fs.readFileSync(path.join(ROOT, 'src', 'workflows', 'team-review.js'), 'utf8'));
  return new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', body);
}

test('review reports every lens as uncovered when the scope agent fails', async () => {
  const agent = async () => { throw new Error('stalled'); };
  const result = await reviewRunner()('the current diff', agent, parallel, pipeline, () => {}, () => {});
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.uncoveredLenses, ['correctness', 'security', 'tests']);
});

test('review keeps only unrefuted findings on each lens scale, and reports failed lenses and verifiers', async () => {
  const types = [];
  const logs = [];
  const schemas = {};
  const finding = (file, line, title, severity) => ({ file, line, title, scenario: 's', severity });
  const agent = async (prompt, opts) => {
    types.push(opts.agentType || 'general');
    // Plugin install missing: the script install ("<id>") must be tried next.
    if (opts.agentType && opts.agentType.startsWith('orchestra:')) throw new Error(`Agent type '${opts.agentType}' not found`);
    schemas[opts.label] = opts.schema;
    if (opts.label === 'scope') return { intent: 'fix', files: [{ path: 'a.js', change: 'modified' }] };
    if (opts.label === 'review:correctness') return { findings: [finding('b.js', 9, 'small bug', 'minor'), finding('a.js', 3, 'refuted bug', 'major'), finding('a.js', 7, 'real bug', 'major'), finding('d.js', 1, 'unchecked bug', 'major')] };
    if (opts.label === 'review:security') return { findings: [finding('c.js', 2, 'injection', 'high')] };
    if (opts.label === 'review:tests') return null;
    if (opts.label === 'verify:correctness#2') return { refuted: true, reason: 'handled' };
    if (opts.label === 'verify:correctness#3') return { refuted: false, reason: 'traced', severity: 'blocker' };
    if (opts.label === 'verify:correctness#4') throw new Error('verifier stalled');
    return { refuted: false, reason: 'traced' };
  };
  const result = await reviewRunner()({ target: 'PR 7', focus: 'auth' }, agent, parallel, pipeline, () => {}, msg => logs.push(msg));
  assert.equal(result.target, 'PR 7');
  assert.deepEqual(result.uncoveredLenses, ['tests']);
  // blocker sorts with critical, major with high, minor with low.
  assert.deepEqual(result.findings.map(f => [f.file, f.line, f.severity]), [['a.js', 7, 'blocker'], ['c.js', 2, 'high'], ['b.js', 9, 'minor']]);
  assert.equal(result.dropped.refuted, 1);
  assert.equal(result.dropped.unverified, 1);
  const severities = label => schemas[label].properties.findings.items.properties.severity.enum;
  assert.deepEqual(severities('review:correctness'), ['blocker', 'major', 'minor']);
  assert.deepEqual(severities('review:security'), ['critical', 'high', 'medium', 'low']);
  assert.deepEqual(schemas['verify:correctness#1'].properties.severity.enum, ['blocker', 'major', 'minor']);
  assert.ok(types.includes('reviewer') && types.includes('security-reviewer'));
  // A type found missing once is not retried.
  assert.equal(types.filter(type => type === 'orchestra:reviewer').length, 1);
  assert.ok(logs.some(msg => /NOT covered: tests/.test(msg)));
});

test('review falls back to a general agent with the role brief when no role is installed', async () => {
  const prompts = [];
  const agent = async (prompt, opts) => {
    if (opts.agentType) throw new Error(`Agent type '${opts.agentType}' not found`);
    prompts.push(prompt);
    if (opts.label === 'scope') return { intent: 'fix', files: [] };
    throw new Error('unexpected stage');
  };
  const result = await reviewRunner()('the current diff', agent, parallel, pipeline, () => {}, () => {});
  assert.deepEqual(result.uncoveredLenses, []);
  assert.match(prompts[0], /^Act as an independent code reviewer .*\(role: reviewer\)/);
});

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
