// Ad-hoc hunt: runs the Jobs Radar pipeline and prints a ranked shortlist with URLs.
// Excludes roles already applied to, and anything that scores as US-only.
import fs from 'node:fs';

const wf = JSON.parse(fs.readFileSync(new URL('./jobs-radar.workflow.json', import.meta.url)));
const code = (n) => wf.nodes.find((x) => x.name === n).parameters.jsCode;
const run = (src, ctx) => new Function('$input', '$', '$getWorkflowStaticData', src)(ctx.$input, ctx.$, ctx.$getWorkflowStaticData);

const ALREADY = [/* /some role title/i — titles to exclude */];
// Companies you have already applied to, been rejected by, or ruled out.
// Keep this in sync with wherever you track applications.
const DONE_COMPANIES = /^(example-company|another-company)$/i;
// Only show roles reachable without a work-authorisation fight.
const EU_OK = (j) => j.reasons.some((r) => /Spain-eligible|remote EU\/EMEA|EU location|worldwide$/.test(r));

const sources = run(code('Build Source List'), {});
const responses = [];
for (const s of sources) {
  try {
    const r = await fetch(s.json.url, {
      method: s.json.method || 'GET',
      headers: { 'User-Agent': 'Mozilla/5.0 (jobs-radar)', ...(s.json.headers || {}) },
      body: s.json.body,
      signal: AbortSignal.timeout(25000),
    });
    responses.push({ json: { data: await r.text() } });
    process.stdout.write(r.ok ? '.' : 'x');
  } catch {
    responses.push({ json: { data: '' } });
    process.stdout.write('!');
  }
  await new Promise((r) => setTimeout(r, 250));
}
console.log(`\nfetched ${responses.length} boards`);

const normalized = run(code('Normalize Jobs'), {
  $input: { all: () => responses },
  $: (n) => ({ all: () => (n === 'Build Source List' ? sources : []) }),
});
const scored = run(code('Score vs Profile'), { $input: { all: () => normalized } });

// DONE_COMPANIES tags rather than drops: a company-level filter cannot tell that a
// NEW posting at a company you already applied to is a level up, and dropping it
// makes that role invisible to triage. The judgement belongs to the read.
const seenRole = new Set();
const shortlist = scored
  .map((s) => s.json)
  .filter((j) => !j.reasons.includes('-US-only'))
  .filter((j) => !j.reasons.includes('-likely US-only'))
  .filter((j) => !ALREADY.some((re) => re.test(j.title)))
  .filter(EU_OK)
  // Collapse per-country clones of one role, same as the pipeline does.
  .sort((a, b) => b.score - a.score)
  .filter((j) => {
    const k = `${(j.company || '').toLowerCase()}|${j.title.toLowerCase()}`;
    if (seenRole.has(k)) return false;
    seenRole.add(k);
    return true;
  })
  .map((j) => ({ ...j, applied: DONE_COMPANIES.test(j.company || '') }));

console.log(`\n${normalized.length} postings -> ${scored.length} PM-titled -> ${shortlist.length} EU-eligible roles (country clones collapsed; [APPLIED BEFORE] = already in DONE_COMPANIES)\n`);
for (const j of shortlist.slice(0, 30)) {
  console.log(`${String(j.score).padStart(3)} | ${j.company}${j.applied ? ' [APPLIED BEFORE]' : ''} | ${j.title}`);
  console.log(`      ${j.location}  ·  ${j.reasons.join(' · ')}`);
  console.log(`      ${j.url}`);
}
