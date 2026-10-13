export const meta = {
  name: 'team-research',
  description: 'Source-backed research: plan sub-questions, research each, check every claim against its source, then write a cited answer',
  whenToUse: 'When the user wants a researched answer in which every claim is checked against its source. Pass the question, or {question, depth} with depth quick, standard or deep.',
  phases: [
    { title: 'Plan', detail: 'split the question into 3 to 6 sub-questions' },
    { title: 'Research', detail: 'one researcher per sub-question collects sourced claims' },
    { title: 'Verify', detail: 'an evidence reviewer checks each claim against its source' },
    { title: 'Synthesize', detail: 'write the cited answer with uncertainty and open questions' },
  ],
}

// Role agents resolve in order: plugin install ("orchestra:<id>"), script install ("<id>"),
// then a general workflow agent that receives a one-line role brief.
const ROLE_BRIEFS = {
  researcher: 'a researcher who answers from primary and official sources and records source, date and uncertainty for every claim',
  'evidence-reviewer': 'an evidence reviewer who independently checks claims, figures and citations against their sources',
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
  try { input = JSON.parse(input) } catch (e) { /* plain-text question */ }
}
const rawQuestion = typeof input === 'string' ? input : input && input.question
const question = rawQuestion ? String(rawQuestion).trim() : ''
if (!question) throw new Error('team-research: pass a question, or {question, depth}.')
const DEPTHS = { quick: { subs: 3, claims: 3 }, standard: { subs: 5, claims: 5 }, deep: { subs: 6, claims: 8 } }
const askedDepth = input && typeof input === 'object' && input.depth ? String(input.depth) : 'standard'
const depth = Object.hasOwn(DEPTHS, askedDepth) ? DEPTHS[askedDepth] : DEPTHS.standard
if (!Object.hasOwn(DEPTHS, askedDepth)) log(`Unknown depth "${askedDepth}"; using standard.`)

const NO_WRITES = 'Do not create, edit or delete files and do not change any external system; return your result only.'
const CONFIDENCE = ['high', 'medium', 'low']

const PLAN = {
  type: 'object',
  properties: {
    subQuestions: {
      type: 'array', minItems: 1, maxItems: depth.subs,
      items: {
        type: 'object',
        properties: {
          question: { type: 'string' },
          evidence: { type: 'string', description: 'What evidence would answer it' },
        },
        required: ['question', 'evidence'],
      },
    },
    assumptions: { type: 'string', description: 'Scope the question leaves open (time frame, region, version) and how you resolved it' },
  },
  required: ['subQuestions'],
}
const CLAIMS = {
  type: 'object',
  properties: {
    claims: {
      type: 'array', maxItems: depth.claims,
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string', description: 'One checkable statement' },
          url: { type: 'string', description: 'Source URL you actually opened' },
          title: { type: 'string' },
          date: { type: 'string', description: 'Publication or last-updated date of the source, or "unknown"' },
          excerpt: { type: 'string', description: 'Short supporting excerpt, under 25 words' },
          confidence: { type: 'string', enum: CONFIDENCE },
        },
        required: ['claim', 'url', 'date', 'confidence'],
      },
    },
    gaps: { type: 'array', items: { type: 'string' }, description: 'What you could not find or access, and where sources disagree' },
  },
  required: ['claims', 'gaps'],
}
const VERDICT = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['supported', 'partial', 'unsupported'] },
    note: { type: 'string', description: 'Why, citing what the source says' },
    correctedClaim: { type: 'string', description: 'For partial: the claim narrowed to what the source supports' },
  },
  required: ['status', 'note'],
}

phase('Plan')
const plan = await roleAgent('researcher', [
  `Research question: ${question}`, '',
  `Plan the research only; do not answer yet. Split the question into 3 to ${depth.subs} sub-questions that can each be answered from sources and together cover what the question needs.`,
  'State any scope the question leaves open (time frame, region, product version) and how you resolved it.',
  NO_WRITES,
].join('\n'), { label: 'plan', phase: 'Plan', schema: PLAN })
if (!plan || !plan.subQuestions.length) throw new Error('team-research: planning produced no sub-questions.')
const subs = plan.subQuestions
const scopeLine = plan.assumptions ? `Scope assumptions: ${plan.assumptions}` : ''

const researchPrompt = sq => [
  `Overall question: ${question}`, scopeLine,
  `Your sub-question: ${sq.question}`,
  `Evidence that would answer it: ${sq.evidence}`, '',
  `Return up to ${depth.claims} key claims that answer the sub-question. Prefer primary and official sources and check time-sensitive facts against current material.`,
  'Back every claim with a source you actually opened. Never invent URLs, quotes, numbers or dates. If you have no web access, say so in gaps and use only material available to you.',
  NO_WRITES,
].filter(Boolean).join('\n')

const verifyPrompt = (c, sq) => [
  `Sub-question: ${sq.question}`,
  `Claim: ${c.claim}`,
  `Cited source: ${c.url}${c.title ? ` (${c.title})` : ''}, dated ${c.date}`,
  c.excerpt ? `Excerpt offered by the researcher: ${c.excerpt}` : '', '',
  'Open the source yourself. Check that it states the claim, that its date and scope match, and that the claim does not overstate it.',
  'supported = the source states it; partial = the source supports only a narrower, older or qualified version (give correctedClaim); unsupported = the source does not say it, contradicts it, or cannot be opened.',
  NO_WRITES,
].filter(Boolean).join('\n')

phase('Research')
const results = await pipeline(
  subs,
  (sq, _item, i) => roleAgent('researcher', researchPrompt(sq), { label: `research#${i + 1}`, phase: 'Research', schema: CLAIMS }),
  (found, sq, i) => {
    if (!found) return null
    log(`Sub-question ${i + 1}: ${found.claims.length} claim(s) to verify`)
    return parallel(found.claims.map((c, j) => async () => {
      const v = await roleAgent('evidence-reviewer', verifyPrompt(c, sq), { label: `verify#${i + 1}.${j + 1}`, phase: 'Verify', schema: VERDICT }).catch(() => null)
      if (v && v.status === 'partial' && !(v.correctedClaim || '').trim()) {
        v.status = 'unverified'
        v.note = `partial verdict has no nonempty correctedClaim: ${v.note}`
      }
      return { ...c, subQuestion: i + 1, status: v ? v.status : 'unverified', note: v ? v.note : 'verifier failed or was skipped', correctedClaim: (v && v.correctedClaim) || '' }
    })).then(claims => ({ claims, gaps: found.gaps }))
  },
)

const failedSubs = subs.map((s, i) => (results[i] ? null : `${i + 1}. ${s.question}`)).filter(Boolean)
if (failedSubs.length) log(`Sub-question(s) with no result, NOT covered: ${failedSubs.join(' | ')}`)
const done = results.filter(Boolean)
const all = done.flatMap(r => r.claims.filter(Boolean))
const claims = all.filter(c => c.status === 'supported' || c.status === 'partial').map((c, n) => ({ id: n + 1, ...c }))
const dropped = all.filter(c => c.status === 'unsupported' || c.status === 'unverified')
for (const c of dropped) log(`Dropped (${c.status}): ${c.claim} [${c.url}] ${c.note}`)
log(`Kept ${claims.length} claim(s); dropped ${dropped.length}.`)
const gaps = done.flatMap(r => r.gaps)

phase('Synthesize')
const answer = await roleAgent('researcher', [
  `Question: ${question}`, scopeLine, '',
  'Verified claims (cite by number):',
  ...(claims.length ? claims.map(c => `[${c.id}] ${c.correctedClaim || c.claim} | ${c.title ? c.title + ' | ' : ''}${c.url} | ${c.date} | ${c.status}${c.status === 'partial' ? ` (${c.note})` : ''} | confidence ${c.confidence}`) : ['(none)']),
  '', 'Research gaps:', ...(gaps.length ? gaps.map(g => `- ${g}`) : ['(none reported)']),
  ...(failedSubs.length ? ['', 'Sub-questions that returned nothing:', ...failedSubs] : []),
  ...(dropped.length ? ['', 'Claims that failed verification (not facts; candidates for open questions):', ...dropped.map(c => `- ${c.claim} (${c.status})`)] : []),
  '',
  'Write the answer in the language of the question, as Markdown. Lead with the direct answer, then the supporting points. Cite every factual statement with [n] using only the verified claims above, and end with a Sources list mapping [n] to title, URL and date.',
  'State uncertainty where claims are partial, low-confidence, dated or in conflict, then list open questions. If no claim is verified, say the question could not be answered from verified sources.',
  NO_WRITES,
].join('\n'), { label: 'synthesize', phase: 'Synthesize' })
  .catch(e => { log(`Synthesis agent failed: ${(e && e.message) || e}`); return null })
if (!answer) log('Synthesis failed; returning verified claims without an answer.')

return { answer: answer || '', claims, dropped }
