// Jobs Radar — standalone runner for GitHub Actions.
//
// It executes the *same* Code-node scripts that live in jobs-radar.workflow.json,
// so n8n and CI can never drift apart. The workflow JSON stays the single source
// of truth; build_workflow.py generates it.
//
// Env:
//   TELEGRAM_TOKEN    required
//   TELEGRAM_CHAT_ID  required
//   DRY_RUN=1         score and print, send nothing
//   THRESHOLD=40      override the score cut-off
//   MAX_PER_RUN=12    cap notifications per run
import fs from 'node:fs';
import path from 'node:path';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const WF = JSON.parse(fs.readFileSync(path.join(HERE, 'jobs-radar.workflow.json'), 'utf8'));
const SEEN_FILE = path.join(HERE, 'seen.json');
const STATUS_JSON = path.join(HERE, 'status.json');
const STATUS_MD = path.join(HERE, 'STATUS.md');

const TOKEN = process.env.TELEGRAM_TOKEN;
const CHAT = process.env.TELEGRAM_CHAT_ID;
const DRY = process.env.DRY_RUN === '1';
const THRESHOLD = Number(process.env.THRESHOLD || 40);
const MAX_PER_RUN = Number(process.env.MAX_PER_RUN || 12);

if (!DRY && (!TOKEN || !CHAT)) {
  console.error('TELEGRAM_TOKEN and TELEGRAM_CHAT_ID are required unless DRY_RUN=1');
  process.exit(1);
}

const code = (name) => {
  const node = WF.nodes.find((n) => n.name === name);
  if (!node) throw new Error(`node not found: ${name}`);
  return node.parameters.jsCode;
};
const run = (src, ctx) =>
  new Function('$input', '$', '$getWorkflowStaticData', src)(
    ctx.$input, ctx.$, ctx.$getWorkflowStaticData,
  );

// ---- dedup state, persisted in the repo -----------------------------------
let store = { seen: {} };
if (fs.existsSync(SEEN_FILE)) {
  try { store = JSON.parse(fs.readFileSync(SEEN_FILE, 'utf8')); } catch { /* start fresh */ }
}
store.seen = store.seen || {};
const seenBefore = Object.keys(store.seen).length;

// ---- 1. sources ------------------------------------------------------------
const sources = run(code('Build Source List'), {});
console.log(`sources: ${sources.length}`);

// ---- 2. fetch --------------------------------------------------------------
// health[i] mirrors sources[i]; it is what STATUS.md is built from. A board that
// starts 403-ing or silently returns zero postings is the radar's real failure
// mode — it contributes nothing and nobody notices without this.
const responses = [];
const health = [];
let ok = 0;
for (const s of sources) {
  const t0 = Date.now();
  let entry = { kind: s.json.kind, company: s.json.company, url: s.json.url,
    http: 0, ok: false, bytes: 0, ms: 0, postings: 0 };
  try {
    const r = await fetch(s.json.url, {
      method: s.json.method || 'GET',
      headers: { 'User-Agent': 'jobs-radar (personal job monitor)', ...(s.json.headers || {}) },
      body: s.json.body,
      signal: AbortSignal.timeout(25000),
    });
    const text = await r.text();
    responses.push({ json: { data: text } });
    entry.http = r.status; entry.ok = r.ok; entry.bytes = text.length;
    if (r.ok) ok++;
  } catch (e) {
    responses.push({ json: { data: '' } });
    entry.http = 0; entry.error = String((e && e.message) || e).slice(0, 80);
  }
  entry.ms = Date.now() - t0;
  health.push(entry);
  // Getro sits behind Datadog bot protection and 403s a burst of consecutive
  // calls to the same host; it needs a much wider gap than a per-company board.
  await new Promise((r) => setTimeout(r, s.json.delayMs || 200));
}
console.log(`fetched ${ok}/${sources.length} boards ok`);

// ---- 3. normalize + score --------------------------------------------------
const normalized = run(code('Normalize Jobs'), {
  $input: { all: () => responses },
  $: (n) => ({ all: () => (n === 'Build Source List' ? sources : []) }),
});
const scored = run(code('Score vs Profile'), { $input: { all: () => normalized } });
console.log(`${normalized.length} postings -> ${scored.length} PM-titled`);

// Per-board yield: normalize one source at a time so a board that parses to
// nothing is distinguishable from a board that simply has no openings.
sources.forEach((s, i) => {
  try {
    health[i].postings = run(code('Normalize Jobs'), {
      $input: { all: () => [responses[i]] },
      $: (n) => ({ all: () => (n === 'Build Source List' ? [s] : []) }),
    }).length;
  } catch { health[i].postings = -1; }
});

// ---- 4. dedup + threshold --------------------------------------------------
const now = Date.now();
const TTL = 45 * 24 * 60 * 60 * 1000;
for (const k of Object.keys(store.seen)) {
  if (now - store.seen[k] > TTL) delete store.seen[k];
}

// Collapse per-country clones of one role before the cap, or a single
// multi-country employer can spend the whole run. The kept variant is the one the
// configured profile can actually take; the others are named in the message.
const collapsed = run(code('Collapse Role Clones'), { $input: { all: () => scored } });
console.log(`PM-titled: ${scored.length} -> ${collapsed.length} distinct roles after collapsing clones`);

const fresh = [];
let suppressed = 0;
for (const s of collapsed) {
  const j = s.json;
  if (j.score < THRESHOLD) continue;
  if (!j.url || store.seen[j.url]) continue;
  // Closed doors only. `applied` stays in and gets a warning line in the message --
  // hard-dropping those once hid the best role of the week.
  if (j.history === 'closed') { suppressed += 1; continue; }
  // hunt.mjs always dropped these from its shortlist; the bot only got away with
  // keeping them because a higher threshold excluded most US-only postings anyway.
  if (j.reasons.some((r) => /^-US-only$|^-likely US-only$/.test(r))) { suppressed += 1; continue; }
  fresh.push(j);
}
if (suppressed) console.log(`suppressed ${suppressed} posting(s): closed-door companies or US-only`);
const batch = fresh.slice(0, MAX_PER_RUN);
console.log(`above threshold ${THRESHOLD}: ${fresh.length}, sending ${batch.length}`);
if (fresh.length > batch.length) {
  console.log(`NOTE: ${fresh.length - batch.length} held back by MAX_PER_RUN, they will go next run`);
}

// ---- 5. notify -------------------------------------------------------------
for (const j of batch) {
  const text = [
    `${j.score}/100  ${j.title}`,
    `${j.company}  ·  ${j.location}`,
    ...(j.history === 'applied'
      ? ['⚠ already applied to this company — check your log before spending another']
      : []),
    j.reasons.join(' · '),
    // Naming the sibling locations is the point of collapsing: the reachable
    // clone is the one linked, and the fallbacks stay visible.
    ...(j.alsoOpenIn && j.alsoOpenIn.length
      ? [`also open in: ${j.alsoOpenIn.join(', ')}`]
      : []),
    j.url,
  ].join('\n');

  if (DRY) {
    console.log('---\n' + text);
  } else {
    const r = await fetch(`https://api.telegram.org/bot${TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: CHAT, text, disable_web_page_preview: false }),
    });
    if (!r.ok) {
      console.error(`telegram ${r.status} for ${j.title}: ${(await r.text()).slice(0, 200)}`);
      continue; // do not mark as seen, so it retries next run
    }
    await new Promise((res) => setTimeout(res, 1200));
  }
  store.seen[j.url] = now;
  // Retire the sibling clones with it, so the other locations of the same role do
  // not arrive next run looking new.
  for (const u of j.cloneUrls || []) store.seen[u] = now;
}

// ---- 6. persist ------------------------------------------------------------
if (!DRY) {
  fs.writeFileSync(SEEN_FILE, JSON.stringify(store, null, 0) + '\n');
  console.log(`seen: ${seenBefore} -> ${Object.keys(store.seen).length}`);
}

// ---- 7. health report ------------------------------------------------------
// Written on every run, dry or not: a dry run is exactly how you check health
// without touching Telegram or seen.json.
const stamp = new Date(now).toISOString();
const down = health.filter((h) => !h.ok);
// `pinpoint-rss` is a date feed, not a board: it exists only so Normalize can join
// pubDate onto the postings.json entries for the same tenant, and it is *supposed*
// to contribute zero postings. Listing it under "live but returning nothing" made
// every healthy Pinpoint tenant look like a broken one.
const DATE_ONLY_KINDS = new Set(['pinpoint-rss']);
const empty = health.filter((h) => h.ok && h.postings === 0 && !DATE_ONLY_KINDS.has(h.kind));
const status = {
  generatedAt: stamp,
  dryRun: DRY,
  totals: {
    sources: health.length,
    ok,
    down: down.length,
    liveButEmpty: empty.length,
    postings: normalized.length,
    pmTitled: scored.length,
    aboveThreshold: fresh.length,
    threshold: THRESHOLD,
  },
  sources: health,
};
fs.writeFileSync(STATUS_JSON, JSON.stringify(status, null, 2) + '\n');

const pct = ok === health.length ? '100%' : `${Math.round((ok / health.length) * 100)}%`;
const badge = down.length === 0 ? 'green' : down.length <= 3 ? 'yellow' : 'red';
const row = (h) => `| ${h.kind} | ${h.company} | ${h.http || h.error || 'ERR'} | ${h.postings} |`;
const md = [
  '# Radar status',
  '',
  `Generated ${stamp} by \`radar.mjs\` — do not edit, it is overwritten every run.`,
  '',
  `**${badge.toUpperCase()}** · ${ok}/${health.length} boards responding (${pct}) · `
    + `${normalized.length} postings → ${scored.length} PM-titled → ${fresh.length} above ${THRESHOLD}`,
  '',
  '## Down',
  '',
  down.length ? '| ATS | Board | HTTP | Postings |\n|---|---|---|---|\n'
    + down.map(row).join('\n') : '_None — every board responded._',
  '',
  '## Live but returning nothing',
  '',
  'A board here is reachable and parsed cleanly but yielded zero postings. That is',
  'normal for a small company with no openings; it is a bug if it persists for a',
  'board that should always have jobs.',
  '',
  empty.length ? '| ATS | Board | HTTP | Postings |\n|---|---|---|---|\n'
    + empty.map(row).join('\n') : '_None._',
  '',
  '## Yield by ATS',
  '',
  '| ATS | Boards | Responding | Postings |',
  '|---|---|---|---|',
  ...Object.entries(health.reduce((acc, h) => {
    const a = acc[h.kind] || (acc[h.kind] = { n: 0, ok: 0, p: 0 });
    a.n += 1; a.ok += h.ok ? 1 : 0; a.p += Math.max(0, h.postings);
    return acc;
  }, {})).sort((a, b) => b[1].p - a[1].p)
    .map(([k, v]) => `| ${k} | ${v.n} | ${v.ok} | ${v.p} |`),
  '',
].join('\n');
fs.writeFileSync(STATUS_MD, md + '\n');
console.log(`status: ${ok}/${health.length} up, ${down.length} down, ${empty.length} live-but-empty`);
