// Claude Code Workflow script: classify every review thread in the batch dossiers
// produced by make_batches.py, then let one skeptic re-check the "invalid" verdicts.
//
// Invoke from a Claude Code session with the Workflow tool:
//   Workflow({
//     scriptPath: '<repo>/audit/classify-workflow.js',
//     args: {
//       dataDir: '<repo>/audit/data',                 // holds batches/batch-NN.md
//       batches: ['batch-01', 'batch-02'],            // printed by make_batches.py
//       configRepo: '<workspace>/coderabbit',         // .coderabbit.yaml + standards/
//       checkouts: '<workspace>',                     // optional: read-only checkouts, one folder per repo
//       model: 'opus',                                // optional model override
//     },
//   })
// Copy the "result" object of the workflow output to <dataDir>/classification.json
// and run aggregate_classification.py.
export const meta = {
  name: 'coderabbit-review-audit',
  description: 'Classify every CodeRabbit/Copilot review finding for validity, substance and the config lever that would have improved it; verify the invalid verdicts',
  phases: [
    { title: 'Classify', detail: 'one agent per batch of ~20 review threads' },
    { title: 'Verify', detail: 'one skeptic re-checks all findings judged invalid' },
  ],
}

const DATA = args.dataDir
const BATCHES = args.batches
const CONFIG_REPO = args.configRepo
const CHECKOUTS = args.checkouts || ''
const MODEL = args.model || undefined

const FINDING = {
  type: 'object',
  properties: {
    id: { type: 'string', description: 'thread tag from the dossier, e.g. CR-3 or COPILOT-1' },
    pr: { type: 'string', description: 'repo#number' },
    bot: { type: 'string', enum: ['CR', 'Copilot'] },
    verdict: { type: 'string', enum: ['valid-substantive', 'valid-minor', 'invalid', 'unverifiable'] },
    substance: { type: 'string', enum: ['bug', 'security', 'data-integrity', 'concurrency-or-resilience', 'test-gap', 'docs', 'style', 'org-convention', 'process', 'other'] },
    outcome_observed: { type: 'string', enum: ['fixed', 'rejected-by-author', 'withdrawn-by-bot', 'ignored', 'silent', 'discussed'] },
    root_cause_if_invalid: { type: 'string', enum: ['missing-cross-repo-context', 'misread-code', 'stale-or-wrong-guideline', 'style-preference', 'already-handled', 'speculative', 'not-applicable'] },
    config_lever: { type: 'string', enum: ['path_instruction', 'standards_doc', 'learning', 'path_filter', 'profile_quiet', 'tool_toggle', 'none', 'unclear'] },
    lever_note: { type: 'string', description: 'concrete rule text or config change (<=220 chars), empty if none' },
    overlap_with: { type: 'string', description: 'tag of the other bot thread reporting the same issue, else empty' },
    note: { type: 'string', description: 'one sentence, <=200 chars' },
  },
  required: ['id', 'pr', 'bot', 'verdict', 'substance', 'outcome_observed', 'root_cause_if_invalid', 'config_lever', 'lever_note', 'overlap_with', 'note'],
}
const BATCH_SCHEMA = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: FINDING },
    patterns: { type: 'array', items: { type: 'string' }, description: 'up to 5 cross-finding observations for this batch (<=200 chars each)' },
    guideline_effect: { type: 'string', description: 'did cited path instructions / standards / learnings make findings better or worse? <=400 chars' },
  },
  required: ['findings', 'patterns', 'guideline_effect'],
}

const checkoutHint = CHECKOUTS
  ? `Local read-only checkouts exist at ${CHECKOUTS}/<repo> for most repos (use ONLY read-only git commands such as git -C <repo> log/show/diff — never checkout, stash, pull or modify anything; the owner works in these checkouts in parallel). If a checkout is missing, you may call 'gh api repos/<org>/<repo>/pulls/<num>/files' at most ONCE per PR (the GitHub rate limit is shared and tight).`
  : `You may call 'gh api repos/<org>/<repo>/pulls/<num>/files' at most ONCE per PR (the GitHub rate limit is shared and tight).`

function classifyPrompt(batch) {
  return `You audit AI code-review quality for a GitHub organization. Read ${DATA}/batches/${batch}.md — it holds pull-request dossiers, each with review threads tagged [CR-n] (CodeRabbit) or [COPILOT-n] (GitHub Copilot) including the author's replies.

For EVERY thread produce one finding object. Judge:
- verdict: was the finding technically correct AND worth a human reviewer's attention? 'valid-substantive' = a real bug/risk/contract violation or a rule the org actually enforces; 'valid-minor' = correct but low value (wording, trivial style, cosmetic docs); 'invalid' = wrong, inapplicable, or contradicted by the code/org conventions; 'unverifiable' = you could not tell.
- Use the author's reply as strong evidence, but do not blindly trust either side: a "Fixed in <sha>" reply may be compliance with a low-value nit; an author pushback may be wrong. When no reply exists, look at the code. ${checkoutHint}
- root_cause_if_invalid: why the bot was wrong ('not-applicable' when valid).
- config_lever: which CodeRabbit configuration change would have prevented an invalid finding or sharpened a valid one. The org config is ${CONFIG_REPO}/.coderabbit.yaml (path_instructions per glob) plus the standards documents in ${CONFIG_REPO}/standards/ (injected into every review) — read the relevant path instruction / standard before choosing. 'learning' = a per-org learning CodeRabbit would record from author feedback; 'profile_quiet' = the finding is the kind the quiet profile (only critical/major inline) would have suppressed; 'path_filter' = the file should not be reviewed at all; 'tool_toggle' = a linter/static tool integration; 'none' = nothing to fix. lever_note must be a concrete, copy-pasteable rule or config line when the lever is path_instruction/standards_doc/learning.
- overlap_with: if a CR thread and a COPILOT thread in the same PR report the same issue, cross-reference both directions.
- outcome_observed: from the replies and resolved/outdated flags (flags may be None for some PRs — then rely on replies; 'silent' = no reply and no evidence).

Be strict and specific. Do not pad. Return the structured result only.`
}

phase('Classify')
const batchResults = await pipeline(
  BATCHES,
  b => agent(classifyPrompt(b), { label: `classify:${b}`, phase: 'Classify', schema: BATCH_SCHEMA, model: MODEL, effort: 'medium' }),
)
const results = batchResults.map((r, i) => ({ batch: BATCHES[i], ...(r || { findings: [], patterns: ['AGENT FAILED'], guideline_effect: '' }) }))
const all = results.flatMap(r => r.findings.map(f => ({ ...f, batch: r.batch })))
const invalid = all.filter(f => f.verdict === 'invalid')
log(`classified ${all.length} findings; ${invalid.length} judged invalid`)

phase('Verify')
const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    verdicts: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, pr: { type: 'string' },
      agree_invalid: { type: 'boolean' },
      corrected_verdict: { type: 'string', enum: ['valid-substantive', 'valid-minor', 'invalid', 'unverifiable'] },
      reason: { type: 'string', description: '<=200 chars' },
    }, required: ['id', 'pr', 'agree_invalid', 'corrected_verdict', 'reason'] } },
  },
  required: ['verdicts'],
}
let verify = { verdicts: [] }
if (invalid.length) {
  const listing = invalid.map(f => `- ${f.pr} ${f.id} (batch ${f.batch}): ${f.note} | claimed root cause: ${f.root_cause_if_invalid}`).join('\n')
  const codeHint = CHECKOUTS ? ` and, where needed, the code in the read-only checkout ${CHECKOUTS}/<repo> (only git -C <repo> log/show/diff; never modify, checkout, stash or pull)` : ''
  verify = await agent(`You are a skeptic. A first-pass audit judged these CodeRabbit/Copilot review findings INVALID (false positives). Your job is to try to REFUTE that judgement: for each, re-read the original thread in ${DATA}/batches/<batch>.md (tags [CR-n]/[COPILOT-n])${codeHint}. Decide whether the bot's finding was actually valid. Default to agree_invalid=true only when the evidence clearly shows the bot was wrong or inapplicable.\n\n${listing}\n\nReturn structured verdicts only.`, { label: 'verify:invalid', phase: 'Verify', schema: VERIFY_SCHEMA, model: MODEL, effort: 'medium' }) || { verdicts: [] }
}
return { results, verify }
