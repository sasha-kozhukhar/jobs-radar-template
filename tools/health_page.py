# Renders status.json into a standalone health page (radar-health.html).
# Run after any radar run — including DRY_RUN=1, which writes status.json too:
#
#   DRY_RUN=1 node radar.mjs && python3 tools/health_page.py
#
# The output is self-contained (Google Fonts is the only external request) and is
# published as a Claude Artifact. GitHub Pages is not an option here: the repo is
# private and Pages needs a paid plan for private repos.
import json, html, datetime, collections

import os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'radar-health.html')
d = json.load(open(os.path.join(HERE, 'status.json')))
t = d['totals']; srcs = d['sources']
gen = d['generatedAt']
dt = datetime.datetime.strptime(gen[:19], '%Y-%m-%dT%H:%M:%S')
stamp = dt.strftime('%d %B %Y, %H:%M UTC')

by = collections.OrderedDict()
for s in srcs:
    a = by.setdefault(s['kind'], {'n':0,'ok':0,'p':0})
    a['n'] += 1; a['ok'] += 1 if s['ok'] else 0; a['p'] += max(0, s['postings'])
by = collections.OrderedDict(sorted(by.items(), key=lambda kv: -kv[1]['p']))
maxp = max(v['p'] for v in by.values()) or 1

def chip(s):
    if not s['ok']:
        return '<span class="chip chip--crit">%s</span>' % (s['http'] or 'ERR')
    if s['postings'] == 0:
        return '<span class="chip chip--warn">%d · empty</span>' % s['http']
    return '<span class="chip chip--ok">%d</span>' % s['http']

rows = []
for s in sorted(srcs, key=lambda x: (x['kind'], -x['postings'])):
    rows.append(
      '<tr data-ats="%s"><td class="mono dim">%s</td><td class="mono strong">%s</td>'
      '<td>%s</td><td class="mono num">%s</td><td class="mono num dim">%s ms</td></tr>'
      % (s['kind'], s['kind'], html.escape(str(s['company'])), chip(s),
         '{:,}'.format(s['postings']), '{:,}'.format(s['ms'])))

atsrows = ''.join(
  '<tr><td class="mono strong">%s</td><td class="mono num">%d</td>'
  '<td class="mono num">%d</td><td class="mono num">%s</td>'
  '<td class="barcell"><span class="bar" style="width:%.1f%%"></span></td></tr>'
  % (k, v['n'], v['ok'], '{:,}'.format(v['p']), 100.0*v['p']/maxp)
  for k, v in by.items())

verdict = 'All boards responding' if t['down'] == 0 else '%d boards down' % t['down']
vclass = 'ok' if t['down'] == 0 else ('warn' if t['down'] <= 3 else 'crit')

down_html = ('<p class="none">Nothing down. Every one of the %d endpoints answered.</p>' % t['sources']) if t['down']==0 else ''
empty_html = '<p class="none">Nothing silent. Every board that answered also parsed to at least one posting.</p>' if t['liveButEmpty']==0 else ''

HTML = f"""<title>Radar Board Health</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {{
  --ground:#f3f5f9; --surface:#ffffff; --sunken:#eaeef5;
  --line:#d7dde9; --ink:#151a24; --dim:#5d6779;
  --accent:#4c5b96; --accent-soft:#e5e8f4;
  --ok:#2f7a52; --ok-soft:#e2f0e8;
  --warn:#96690f; --warn-soft:#f7eddb;
  --crit:#b13a2e; --crit-soft:#f8e5e2;
  --radius:10px;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#0d1119; --surface:#151b26; --sunken:#111721;
    --line:#28303f; --ink:#e7ebf3; --dim:#94a0b5;
    --accent:#93a2e0; --accent-soft:#1f2740;
    --ok:#6fc793; --ok-soft:#16281f;
    --warn:#dcae5c; --warn-soft:#2a2114;
    --crit:#f08a7c; --crit-soft:#2e1a18;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0d1119; --surface:#151b26; --sunken:#111721;
  --line:#28303f; --ink:#e7ebf3; --dim:#94a0b5;
  --accent:#93a2e0; --accent-soft:#1f2740;
  --ok:#6fc793; --ok-soft:#16281f;
  --warn:#dcae5c; --warn-soft:#2a2114;
  --crit:#f08a7c; --crit-soft:#2e1a18;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:1000px; margin:0 auto; padding:48px 24px 96px; display:flex; flex-direction:column; gap:40px; }}
.mono {{ font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,monospace; }}
.num {{ font-variant-numeric:tabular-nums; text-align:right; }}
.dim {{ color:var(--dim); }}
.strong {{ font-weight:600; }}

header {{ display:flex; flex-direction:column; gap:10px; }}
h1 {{
  font-family:Fraunces,Georgia,serif; font-weight:600;
  font-size:clamp(30px,5vw,46px); line-height:1.05; margin:0;
  letter-spacing:-.015em; text-wrap:balance;
}}
.eyebrow {{
  font-family:"IBM Plex Mono",monospace; font-size:11px; font-weight:500;
  letter-spacing:.14em; text-transform:uppercase; color:var(--accent); margin:0;
}}
.sub {{ margin:0; color:var(--dim); max-width:64ch; }}

.verdict {{
  display:flex; flex-wrap:wrap; align-items:baseline; gap:14px;
  padding:22px 24px; border-radius:var(--radius);
  background:var(--surface); border:1px solid var(--line);
  border-left:4px solid var(--vc,var(--ok));
}}
.verdict.ok {{ --vc:var(--ok); }} .verdict.warn {{ --vc:var(--warn); }} .verdict.crit {{ --vc:var(--crit); }}
.verdict h2 {{ margin:0; font-size:20px; font-weight:600; letter-spacing:-.01em; }}
.verdict .when {{ margin-left:auto; font-size:12px; }}

.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; }}
.stat {{ background:var(--surface); padding:18px 20px; display:flex; flex-direction:column; gap:4px; }}
.stat .k {{ font-family:"IBM Plex Mono",monospace; font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--dim); }}
.stat .v {{ font-family:"IBM Plex Mono",monospace; font-size:26px; font-weight:600; font-variant-numeric:tabular-nums; letter-spacing:-.02em; }}
.stat .note {{ font-size:12px; color:var(--dim); }}

.funnel {{ display:flex; flex-wrap:wrap; align-items:center; gap:12px; padding:18px 20px; background:var(--sunken); border-radius:var(--radius); font-family:"IBM Plex Mono",monospace; font-size:13px; }}
.funnel b {{ font-weight:600; font-variant-numeric:tabular-nums; }}
.funnel .arrow {{ color:var(--accent); }}
.funnel .lbl {{ color:var(--dim); }}

section h3 {{ font-size:13px; font-family:"IBM Plex Mono",monospace; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); margin:0 0 12px; font-weight:600; }}
section p.lead {{ margin:0 0 16px; color:var(--dim); max-width:66ch; font-size:14px; }}
.none {{ margin:0; padding:16px 18px; border-radius:var(--radius); background:var(--ok-soft); color:var(--ok); font-size:14px; border:1px solid transparent; }}

.tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th {{ text-align:left; font-family:"IBM Plex Mono",monospace; font-size:10.5px; letter-spacing:.1em; text-transform:uppercase; color:var(--dim); font-weight:600; padding:12px 16px; border-bottom:1px solid var(--line); white-space:nowrap; background:var(--sunken); }}
th.num {{ text-align:right; }}
td {{ padding:9px 16px; border-bottom:1px solid var(--line); white-space:nowrap; }}
tr:last-child td {{ border-bottom:0; }}
tbody tr:hover td {{ background:var(--sunken); }}

.chip {{ display:inline-block; font-family:"IBM Plex Mono",monospace; font-size:11px; font-weight:600; padding:2px 8px; border-radius:999px; font-variant-numeric:tabular-nums; }}
.chip--ok {{ background:var(--ok-soft); color:var(--ok); }}
.chip--warn {{ background:var(--warn-soft); color:var(--warn); }}
.chip--crit {{ background:var(--crit-soft); color:var(--crit); }}

.barcell {{ width:34%; min-width:120px; }}
.bar {{ display:block; height:7px; border-radius:3px; background:var(--accent); opacity:.75; }}

.filters {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:14px; }}
.filters button {{ font-family:"IBM Plex Mono",monospace; font-size:11.5px; padding:5px 11px; border-radius:999px; border:1px solid var(--line); background:var(--surface); color:var(--dim); cursor:pointer; transition:background .12s,color .12s,border-color .12s; }}
.filters button:hover {{ border-color:var(--accent); color:var(--accent); }}
.filters button[aria-pressed="true"] {{ background:var(--accent-soft); border-color:var(--accent); color:var(--accent); font-weight:600; }}
.filters button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}

footer {{ border-top:1px solid var(--line); padding-top:20px; color:var(--dim); font-size:13px; display:flex; flex-direction:column; gap:8px; }}
code {{ font-family:"IBM Plex Mono",monospace; font-size:.92em; background:var(--sunken); padding:1px 5px; border-radius:4px; }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} }}
</style>

<div class="wrap">
  <header>
    <p class="eyebrow">Jobs Radar · board health</p>
    <h1>Radar Board Health</h1>
    <p class="sub">Every four hours the radar asks {t['sources']} job boards what they are advertising, scores each posting against the profile, and pushes what clears the bar to Telegram. This page is the state of those {t['sources']} endpoints on the run below.</p>
  </header>

  <div class="verdict {vclass}">
    <h2>{verdict}</h2>
    <span class="mono dim">{t['ok']} of {t['sources']} answered</span>
    <span class="mono dim when">run of {stamp}</span>
  </div>

  <div class="stats">
    <div class="stat"><span class="k">Endpoints</span><span class="v">{t['sources']}</span><span class="note">across 17 board types</span></div>
    <div class="stat"><span class="k">Down</span><span class="v">{t['down']}</span><span class="note">no response or error</span></div>
    <div class="stat"><span class="k">Live but silent</span><span class="v">{t['liveButEmpty']}</span><span class="note">answered, parsed to nothing</span></div>
    <div class="stat"><span class="k">Sent to Telegram</span><span class="v">{t['aboveThreshold']}</span><span class="note">scored ≥ {t['threshold']}</span></div>
  </div>

  <div class="funnel">
    <span class="lbl">postings fetched</span> <b>{t['postings']:,}</b>
    <span class="arrow">→</span>
    <span class="lbl">product-manager titles</span> <b>{t['pmTitled']:,}</b>
    <span class="arrow">→</span>
    <span class="lbl">scored ≥ {t['threshold']}</span> <b>{t['aboveThreshold']}</b>
  </div>

  <section>
    <h3>Not responding</h3>
    <p class="lead">The failure this page exists to catch. Fetch errors are deliberately non-fatal, so a board that starts returning 404 after a company changes ATS contributes nothing and looks exactly like a company with no openings.</p>
    {down_html}
  </section>

  <section>
    <h3>Answered, but parsed to nothing</h3>
    <p class="lead">Reachable and valid, yet zero postings came out. Normal for a small company with no openings — a bug if it persists on a board that should always carry jobs.</p>
    {empty_html}
  </section>

  <section>
    <h3>Where the postings come from</h3>
    <p class="lead">Bar length is share of the largest contributor. Greenhouse and Ashby carry the volume; Personio, Teamtailor and the Getro venture boards were added to reach the small European companies the big-brand boards never list.</p>
    <div class="tablewrap">
      <table>
        <thead><tr><th>Board type</th><th class="num">Boards</th><th class="num">Answered</th><th class="num">Postings</th><th>Share</th></tr></thead>
        <tbody>{atsrows}</tbody>
      </table>
    </div>
  </section>

  <section>
    <h3>Every endpoint</h3>
    <p class="lead">One row per board, with the HTTP code it returned, how many postings it parsed to, and how long it took.</p>
    <div class="filters" id="filters"></div>
    <div class="tablewrap">
      <table>
        <thead><tr><th>Board type</th><th>Board</th><th>Status</th><th class="num">Postings</th><th class="num">Latency</th></tr></thead>
        <tbody id="rows">{''.join(rows)}</tbody>
      </table>
    </div>
  </section>

  <footer>
    <p style="margin:0"><strong>This is a snapshot, not a live dial.</strong> It shows the run of {stamp}. The always-current version is <code>STATUS.md</code> in the jobs-radar repository, rewritten and committed by CI on every run.</p>
    <p style="margin:0">Check health locally without sending anything: <code>DRY_RUN=1 node radar.mjs &amp;&amp; cat STATUS.md</code></p>
  </footer>
</div>

<script>
(function () {{
  var kinds = Array.from(new Set(Array.from(document.querySelectorAll('#rows tr')).map(function (r) {{ return r.dataset.ats; }})));
  var box = document.getElementById('filters');
  var mk = function (label, value) {{
    var b = document.createElement('button');
    b.type = 'button'; b.textContent = label; b.dataset.value = value;
    b.setAttribute('aria-pressed', value === 'all' ? 'true' : 'false');
    box.appendChild(b); return b;
  }};
  mk('all ' + document.querySelectorAll('#rows tr').length, 'all');
  kinds.sort().forEach(function (k) {{ mk(k, k); }});
  box.addEventListener('click', function (e) {{
    var b = e.target.closest('button'); if (!b) return;
    Array.from(box.children).forEach(function (x) {{ x.setAttribute('aria-pressed', String(x === b)); }});
    var v = b.dataset.value;
    Array.from(document.querySelectorAll('#rows tr')).forEach(function (r) {{
      r.style.display = (v === 'all' || r.dataset.ats === v) ? '' : 'none';
    }});
  }});
}})();
</script>
"""
open(OUT,'w').write(HTML)
print('written', OUT, len(HTML), 'bytes')
