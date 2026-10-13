export const meta = {
  name: 'team-review',
  description: 'Read-only code review through correctness, security and missing-test lenses; every finding must survive an independent refutation attempt',
  whenToUse: 'When the user asks for a thorough, verified review of the current diff, a branch, a pull request or specific files. Pass a target description, or {target, focus}.',
  phases: [
    { title: 'Scope', detail: 'list the changed files and summarize the intent of the change' },
    { title: 'Review', detail: 'correctness, security and missing-test lenses run independently' },
    { title: 'Verify', detail: 'a fresh verifier tries to refute each finding' },
  ],
}

// Role agents resolve in order: plugin install ("orchestra:<id>"), script install ("<id>"),
// then a general workflow agent that receives a one-line role brief.
const ROLE_BRIEFS = {
  reviewer: 'an independent code reviewer who finds real defects, behavior regressions and missing tests in changed code',
  'security-reviewer': 'a security reviewer who checks trust boundaries, authentication, authorization, input handling, secrets and dependency risk',
}
const missingTypes = new Set()
const announced = new Set()
// Only a rejection for an unknown agent type moves on to the next candidate. Any other failure
// (schema validation, stalls) belongs to the stage itself and must not downgrade the role.
const unknownType = (error, agentType) => {
  const message = String((error && error.message) || error)
  return /not found/i.test(message) && message.includes(agentType)
}
async function roleAgent(id, prompt, opts) {
  for (const agentType of ['orchestra:' + id, id]) {
    if (missingTypes.has(agentType)) continue
    try {
      return await agent(prompt, { ...opts, agentType })
    } catch (e) {
      if (!unknownType(e, agentType)) throw e
      missingTypes.add(agentType)
    }
  }
  if (!announced.has(id)) {
    announced.add(id)
    log(`Role "${id}" is not installed as an agent; using a general agent with the role brief.`)
  }
  return agent(`Act as ${ROLE_BRIEFS[id]} (role: ${id}).\n\n${prompt}`, opts)
}

let input = args
if (typeof input === 'string' && input.trim().startsWith('{')) {
  try { input = JSON.parse(input) } catch (e) { /* plain-text target */ }
}
const rawTarget = typeof input === 'string' ? input : input && input.target
const target = (rawTarget && String(rawTarget).trim()) || 'the current uncommitted git diff'
const focus = input && typeof input === 'object' && input.focus ? String(input.focus).trim() : ''

const READ_ONLY = 'This is a read-only review. Do not create, edit, delete, stage or commit any file, and do not run commands that change the working tree or any external system. Read-only commands (git diff/log/show, search, existing tests or linters that do not rewrite sources) are allowed. Write prose in the language of the review request.'
const SEVERITIES = ['critical', 'high', 'medium', 'low']
const RANK = { critical: 0, high: 1, medium: 2, low: 3 }

const SCOPE = {
  type: 'object',
  properties: {
    intent: { type: 'string', description: 'What the change is meant to do, in a few sentences' },
    files: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path relative to the repository root' },
          change: { type: 'string', description: 'added, modified, deleted or renamed' },
          hunks: { type: 'string', description: 'Changed line ranges, if known' },
        },
        required: ['path', 'change'],
      },
    },
  },
  required: ['intent', 'files'],
}
const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer', minimum: 0, description: '1-based line the finding anchors to; 0 for file-level' },
          title: { type: 'string', description: 'One-line statement of the defect' },
          scenario: { type: 'string', description: 'Concrete inputs or state that lead to the wrong result' },
          severity: { type: 'string', enum: SEVERITIES },
          suggestion: { type: 'string', description: 'Direction for the fix' },
        },
        required: ['file', 'line', 'title', 'scenario', 'severity'],
      },
    },
  },
  required: ['findings'],
}
const VERDICT = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reason: { type: 'string', description: 'Short justification that cites the code you read' },
    severity: { type: 'string', enum: SEVERITIES, description: 'Severity you would assign if the finding stands' },
  },
  required: ['refuted', 'reason'],
}

const LENSES = [
  { id: 'correctness', role: 'reviewer', ask: 'correctness bugs and behavior regressions: wrong logic, broken callers or contracts, unhandled edge cases and errors, concurrency, data loss.' },
  { id: 'security', role: 'security-reviewer', ask: 'reachable security problems: authentication or authorization gaps, injection, unsafe input handling, secret or data exposure, unsafe defaults, risky dependency use.' },
  { id: 'tests', role: 'reviewer', ask: 'missing or inadequate tests: changed behavior with no test, tests that cannot fail, removed coverage, untested error paths. Anchor each finding at the line that implements the untested behavior.' },
]

phase('Scope')
const scope = await roleAgent('reviewer', [
  `Review target: ${target}`,
  'Identify exactly what this target changes. List every changed file and summarize the intent of the change. Do not review it yet.',
  READ_ONLY,
].join('\n'), { label: 'scope', phase: 'Scope', schema: SCOPE })
  .catch(e => { log(`Scope agent failed: ${(e && e.message) || e}`); return null })
if (!scope || !scope.files.length) {
  log(scope ? 'Nothing to review: the target has no changed files.' : 'Scope agent failed; review not run.')
  return { target, intent: scope ? scope.intent : '', files: [], findings: [], dropped: { refuted: 0, unverified: 0, items: [] }, uncoveredLenses: scope ? [] : LENSES.map(l => l.id) }
}

const context = [
  `Review target: ${target}`,
  `Intent of the change: ${scope.intent}`,
  'Changed files:',
  ...scope.files.map(f => `- ${f.path} (${f.change}${f.hunks ? '; ' + f.hunks : ''})`),
  focus && `Extra focus requested by the user: ${focus}`,
].filter(Boolean).join('\n')

const findPrompt = lens => [
  context, '',
  `Your lens: ${lens.ask}`,
  'Read the changed code, its callers and related tests. Report only defects with a concrete, reachable failure scenario; skip style preferences and anything outside your lens.',
  'Severity: critical = exploitable or data loss on a common path; high = wrong behavior on a common path; medium = failure on an edge case; low = minor impact.',
  'Return an empty list when nothing qualifies.',
  READ_ONLY,
].join('\n')

const verifyPrompt = (f, lens) => [
  context, '',
  `A ${lens.id} reviewer reported the finding below. Independently try to REFUTE it.`,
  `Location: ${f.file}:${f.line}`,
  `Claim: ${f.title}`,
  `Scenario: ${f.scenario}`,
  `Claimed severity: ${f.severity}`, '',
  'Read the code yourself. Set refuted=true if the scenario cannot happen, is already handled, is not in code the target touches or affects, or cannot be confirmed from the code. Set refuted=false only when you can trace the failure path.',
  READ_ONLY,
].join('\n')

phase('Review')
const results = await pipeline(
  LENSES,
  lens => roleAgent(lens.role, findPrompt(lens), { label: `review:${lens.id}`, phase: 'Review', schema: FINDINGS }),
  (found, lens) => {
    if (!found) return null
    log(`${lens.id}: ${found.findings.length} finding(s) to verify`)
    return parallel(found.findings.map((f, i) => async () => {
      const verdict = await roleAgent(lens.role, verifyPrompt(f, lens), { label: `verify:${lens.id}#${i + 1}`, phase: 'Verify', schema: VERDICT }).catch(() => null)
      return { ...f, lens: lens.id, verdict }
    }))
  },
)

const uncoveredLenses = LENSES.filter((l, i) => !results[i]).map(l => l.id)
if (uncoveredLenses.length) log(`Lens(es) failed and are NOT covered: ${uncoveredLenses.join(', ')}`)

const all = results.filter(Boolean).flat().filter(Boolean)
const refuted = all.filter(f => f.verdict && f.verdict.refuted)
const unverified = all.filter(f => !f.verdict)
const brief = f => ({ file: f.file, line: f.line, title: f.title, lens: f.lens })
const droppedItems = [
  ...refuted.map(f => ({ ...brief(f), reason: `refuted: ${f.verdict.reason}` })),
  ...unverified.map(f => ({ ...brief(f), reason: 'unverified: the verifier failed or was skipped' })),
]
for (const d of droppedItems) log(`Dropped ${d.file}:${d.line} ${d.title} (${d.reason})`)

const findings = all
  .filter(f => f.verdict && !f.verdict.refuted)
  .map(f => ({ ...brief(f), severity: f.verdict.severity || f.severity, scenario: f.scenario, suggestion: f.suggestion || '', evidence: f.verdict.reason }))
  .sort((a, b) => RANK[a.severity] - RANK[b.severity] || a.file.localeCompare(b.file) || a.line - b.line)

log(`Confirmed ${findings.length}; dropped ${refuted.length} refuted and ${unverified.length} unverified.`)
const dropped = { refuted: refuted.length, unverified: unverified.length, items: droppedItems }
return { target, intent: scope.intent, files: scope.files.map(f => f.path), findings, dropped, uncoveredLenses }
