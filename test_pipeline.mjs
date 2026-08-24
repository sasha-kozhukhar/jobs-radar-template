// Executes the workflow's Code-node scripts against live API responses,
// so bugs surface here rather than after import into n8n.
import fs from 'node:fs';

const wf = JSON.parse(fs.readFileSync(new URL('./jobs-radar.workflow.json', import.meta.url)));
const code = (name) => wf.nodes.find((n) => n.name === name).parameters.jsCode;

const run = (src, ctx) => {
  const fn = new Function('$input', '$', '$getWorkflowStaticData', `${src}`);
  return fn(ctx.$input, ctx.$, ctx.$getWorkflowStaticData);
};

// ---- Build Source List -----------------------------------------------------
const sources = run(code('Build Source List'), {});
console.log(`sources: ${sources.length}`);

// ---- Fetch Board (sequential, polite) --------------------------------------
const responses = [];
for (const s of sources) {
  try {
    const r = await fetch(s.json.url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (n8n jobs-radar test)' },
      signal: AbortSignal.timeout(20000),
    });
    responses.push({ json: { data: await r.text() } });
    process.stdout.write(r.ok ? '.' : 'x');
  } catch (e) {
    responses.push({ json: { data: '' } });
    process.stdout.write('!');
  }
  await new Promise((r) => setTimeout(r, 300));
}
console.log('\nfetched');

// ---- Normalize Jobs --------------------------------------------------------
const ctx = {
  $input: { all: () => responses },
  $: (name) => ({ all: () => (name === 'Build Source List' ? sources : []) }),
};
const normalized = run(code('Normalize Jobs'), ctx);
console.log(`normalized jobs: ${normalized.length}`);

const bySource = {};
for (const n of normalized) bySource[n.json.source] = (bySource[n.json.source] || 0) + 1;
console.log('per source:', bySource);

// ---- Score vs Profile ------------------------------------------------------
const scored = run(code('Score vs Profile'), { $input: { all: () => normalized } });
console.log(`PM-titled after gates: ${scored.length}`);

const THRESHOLD = 48;
const passing = scored.filter((s) => s.json.score >= THRESHOLD);
console.log(`>= ${THRESHOLD}: ${passing.length}`);

console.log('\n--- top 15 ---');
for (const s of scored.slice(0, 15)) {
  const j = s.json;
  console.log(`${String(j.score).padStart(3)} | ${j.company} | ${j.title} | ${j.location}`);
  console.log(`      ${j.reasons.join(' · ')}`);
}

// ---- Dedup (static data) ---------------------------------------------------
const store = {};
const dedupCtx = {
  $input: { all: () => passing },
  $getWorkflowStaticData: () => store,
};
const first = run(code('Drop Already Sent'), dedupCtx);
const second = run(code('Drop Already Sent'), dedupCtx);
console.log(`\ndedup: first run would send ${first.length}, immediate re-run ${second.length} (expect 0)`);

// ---- optional live Telegram delivery: node test_pipeline.mjs --notify N -----
if (process.argv.includes('--notify')) {
  const n = Number(process.argv[process.argv.indexOf('--notify') + 1]) || 3;
  const TOKEN = process.env.TELEGRAM_TOKEN;
  const CHAT = process.env.TELEGRAM_CHAT_ID;
  if (!TOKEN || !CHAT) { console.error('set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID to use --notify'); process.exit(1); }
  for (const s of passing.slice(0, n)) {
    const j = s.json;
    const text = `${j.score}/100  ${j.title}\n${j.company}  ·  ${j.location}\n${j.reasons.join(' · ')}\n${j.url}`;
    const r = await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: CHAT, text }),
    });
    const b = await r.json();
    console.log(`telegram ${r.status} ok=${b.ok} -> ${j.title.slice(0, 50)}`);
    await new Promise((res) => setTimeout(res, 1200));
  }
}
