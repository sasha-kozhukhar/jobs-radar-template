# Jobs Radar

Scans 119 public job boards every 4 hours, scores each posting against a profile you
configure, and pushes anything relevant to Telegram. Self-hosted, no API keys, no paid
services — GitHub Actions is the only runtime it needs.

## This is a template — you have to build your own version

Cloning this and pressing run will get you somebody else's shortlist. Two things are
yours to create before it is useful:

**1. Your own flow.** `jobs-radar.workflow.json` is an n8n workflow export. Import it into
your own n8n instance (`http://localhost:5678` in Docker is enough) and it becomes an
editable flow you own — or skip n8n entirely and run `radar.mjs`, which executes the exact
same Code-node scripts from that same JSON file. Either way the workflow is yours to
change: sources, schedule, threshold, delivery channel.

**2. Your own filters, derived from your own CV.** The scoring node shipped here encodes
one candidate's search — senior/lead product management, B2B SaaS and AI products, EU-based,
with penalties for on-site work and for languages that candidate does not speak. **None of
that is logic; all of it is configuration**, and none of it fits you.

Sit down with your CV and rewrite it against what you actually have and actually want:

- the **titles** at, above and below your level (`TITLE_LEAD`, `TITLE_SENIOR`, `TITLE_BASE`)
- the **topics** worth weighting in a job title (`TITLE_AI`, `TITLE_PLATFORM`, `TITLE_KW`)
- the **description keywords** that map to real evidence you can point at in an interview —
  not everything you find interesting (`KW`)
- the **title shapes to reject outright**: wrong level, wrong function (`TITLE_BLOCK`)
- your **geography and work arrangement** — which countries and cities, remote vs hybrid vs
  on-site, and where you need no work-permit conversation
- the **languages you do not work in**, so roles run in them score down

`SETUP.md` walks through all five steps, including the Telegram bot and the secrets.

The rest of the repo — 17 ATS integrations, the normalisation layer, the aggregator-distrust
rule for location claims, the staleness penalty, the board-health report — is generic and
works unchanged.

## Where it runs

**GitHub Actions is the scheduler** — `.github/workflows/radar.yml`, every 4 hours,
plus manual `workflow_dispatch` with a `dry_run` toggle. Secrets `TELEGRAM_TOKEN` and
`TELEGRAM_CHAT_ID` live in repo settings, never in the code.

`radar.mjs` executes the *same* Code-node scripts stored in `jobs-radar.workflow.json`,
so the cloud runner and n8n can never drift apart. Dedup state is `seen.json`, committed
back by the workflow after each run.

```bash
gh workflow run radar.yml -f dry_run=true    # score and print, send nothing
gh run list --limit 5
```

**`gh` account matters.** If `gh` is authenticated as a different account than the one
owning the repo, it returns a bare 404 for the repo and for every Actions call rather than
a permissions error — `gh auth switch --user <your-account>` fixes it.

## Health

`STATUS.md` is regenerated on every run (dry runs included) and committed by CI
next to `seen.json`, so the current state is readable straight from the repo
without opening a log. `status.json` is the same data unrounded, per board:
HTTP code, bytes, latency and how many postings that board parsed to.

The failure it exists to catch is a board that quietly stops contributing — a
404 after a company migrates ATS, or a 403 from bot protection. Nothing else in
the pipeline notices: fetch failures are deliberately non-fatal, so a dead board
looks exactly like a board with no openings. Two sections separate those cases —
**Down** (did not respond) and **Live but returning nothing** (responded, parsed
clean, zero postings).

CI fails the run if more than a third of boards are down, which is loud without
being noisy about the one or two that 404 on any given day.

```bash
DRY_RUN=1 node radar.mjs && cat STATUS.md   # health check, sends nothing
```

The n8n copy still exists locally for editing and inspection, but its schedule is
**deactivated** (`active = 0`) so it cannot double-send:

| | |
|---|---|
| URL | http://localhost:5678 |
| Container | `n8n-local` |
| Data volume | `~/.n8n-local` |
| Workflow ID | `jobsradar0000001` — inactive by design |

Only re-activate it if you also disable the GitHub schedule — the two keep separate
dedup stores, so running both means duplicate alerts.

## Pipeline

```
Every 4 hours ─┐
Run manually  ─┴→ Build Source List → Fetch Board → Normalize Jobs
                → Score vs Profile → Collapse Role Clones → Relevant enough?
                → Drop Already Sent → Send to Telegram
```

- **Build Source List** — 119 endpoints: 34 Greenhouse boards,
  42 Ashby, **10 Personio**, **8 Teamtailor**, 3 Recruitee, 3 Lever,
  1 Workable (Hugging Face), 1 SmartRecruiters (Delivery Hero, pre-filtered with
  `q="product manager"`), **8 Getro VC talent boards**, and 9 aggregator feeds
  (RemoteOK, Himalayas, WWR RSS, Remotive, Jobicy, WorkingNomads, Arbeitnow,
  TheMuse ×2). All are official public JSON/RSS. No scraping, no auth, nothing
  that can get an account flagged.

  **Getro (added 2026-08-20, unverified in CI).** One endpoint per VC covers that
  fund's whole portfolio, which is the cheapest way to reach early-stage EU
  companies — a single probe turned up Mistral AI (Paris/London/Munich), finmid,
  Climatiq and Lokalise, none of which any other source in this list carries.
  Network ids come from the fund's own board: open `https://<board>/jobs` and read
  `props.pageProps.network.id` out of `__NEXT_DATA__`. Three quirks: the API is
  **POST-only** (GET 404s), it wants **exactly** `accept: application/json`
  (`*/*` returns 406), and the default ordering is already newest-first, so page 0
  is what a radar wants. `description` comes back null, so these score on title
  and location alone.

  **The caveat:** api.getro.com sits behind Datadog bot protection. Probing it
  hard enough to work out the above got this machine's IP 403-ed, and the block
  did not lift with a 4 s gap between calls, so the source list ships **unverified
  from CI**. Runner IPs differ and the load is 8 requests every 4 hours, so it may
  simply work — `STATUS.md` after the next scheduled run is the answer. If all
  eight stay 403 there, drop the `getro` list; nothing else depends on it.

  **Personio and Teamtailor were added 2026-08-20** to reach the small-EU-company
  bracket the big-brand boards miss — the segment alago (Munich ConTech, 11 people)
  turned up in. Both carry caveats worth knowing before adding tenants:
  Teamtailor's `jobs.json` returns only the ~10 most recent postings per board and
  ignores `?page=`, which is fine for a new-posting radar but is not a full listing;
  Personio's XML has no job URL (it is built from the id) and its
  `<jobDescriptions>` is frequently empty, so those postings score on title and
  office alone. Personio also rate-limits hard — probing tenants without spacing
  returns 429.
- **Fetch Board** — sequential, 1 request per 1.2 s, failures skipped rather
  than fatal.
- **Normalize Jobs** — one shape per source → `{source, company, title,
  location, url, description, postedAt}`.
- **Score vs Profile** — see below.
- **Collapse Role Clones** — one entry per real role, keyed on
  `(company, normalized title)`. See "The clone problem" below.
- **Drop Already Sent** — remembers URLs in n8n static data for 45 days, so a
  posting is announced once, and retires a collapsed role's sibling `cloneUrls`
  along with it. Caps each run at 12 messages and marks **only what actually
  goes out**.
- **Relevant enough?** — threshold **30** (lowered from 48 on 2026-08-17).
- **Send to Telegram** — via your own bot (create one with `@BotFather`). Token and chat id come from the
  `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` environment variables — never committed.

## Scoring

Signal lives in the **title** and the **location** field. Nearly every tech
posting name-drops "AI" somewhere in its description, so description keywords
score weakly and are capped at +22 — without that cap everything saturates at
100 and the ranking is useless (this was the first version's bug).

Gates (drop outright):
- title is not a product-management title
- title says junior/intern/graduate, engineer/designer/architect,
  sales/CS/recruiter, or marketing

Points:
- lead/staff/principal/head/director title +28 · senior +24 · plain PM +12
- AI in title +18 · agents in title +14 · platform +10 · governance +8 · API/ecosystem +7
- description keywords +2…+5 each, capped +26 (includes non-AI signals: PLG,
  activation/retention, experimentation, analytics, people leadership, pre-sales)
- worldwide +16 (only +6 from aggregators, see below) · remote EU/EMEA +16 ·
  EU location +9 · generic remote +7 · **Spain named +7**
- **US-only −32** · likely US-only from an aggregator −20 · hybrid −10 · onsite −12
- Spanish-language role −25 · other native language required −18
- posting older than 45 days −12 · older than 30 days −6 (penalty-only, no
  freshness bonus; missing dates cost nothing). Greenhouse uses `first_published`,
  not `updated_at`, so an edited-but-old posting still reads as old. Added after
  A posting that has been live for six weeks is usually deep in final rounds: one
  application went out to a role open since six weeks prior and came back "position filled"
  two days later. Penalty-only, so nothing is pushed over the threshold just for being new.
  a posting live 6+ weeks is likely already in final rounds.

### Two corrections made after the first live day

**WeWorkRemotely lies about location.** It labelled Coinbase and Stripe roles "Anywhere in
the World" while those companies' own ATS said "Remote - USA". Three of the top six results
were phantom US-only roles. Fix: aggregator sources (`wwr`, `remoteok`, `himalayas`) get
only +6 for a worldwide claim instead of +16, and any US signal in the description costs
−20 with a `-likely US-only` flag. Coinbase's Compliance Agent Experience went 75 → 48.

**Strong non-AI roles were invisible.** One strong product-led-growth role — the closest fit found
all day, Spain remote, every requirement backed by CV evidence — scored 44 and fell under
the threshold, because the keyword list had no growth/PLG terms and Spain earned no bonus.
Fix: added the non-AI keyword group and the Spain bonus. It now scores 51, and three more
the same company's other remote roles surfaced at 47.

Calibration check on a live run: Hostaway "Staff PM – AI – Remote EMEA" scored
**80** and Appfire "Senior PM – AI Governance" scored **65** — the two roles
The roles a human would shortlist came out on top, which is the behaviour wanted.

Last live run (2026-08-20, 111 sources): 9 625 postings fetched → 379 with a PM title.
The two new platforms contributed 454 postings, 11 PM-titled, top of them a
Senior Product Manager at Userlane in London scoring 36.

### The clone problem

One employer posting one role in ten countries is **one decision, not ten
notifications**. It is common, and it is expensive: an employer publishing two
roles as 19 country clones can fill a whole `MAX_PER_RUN` batch on its own,
pushing everything else to the next run. The cap makes that failure silent.

The naive fix — keep the best-scoring clone, drop the rest — is wrong, because
clones are often **not interchangeable**. The same role is frequently
country-locked with a different salary band per country, and sometimes only one
clone is reachable without a work-authorisation fight. Dropping the wrong ones can
hide the only clone worth applying to. So the node collapses the *notification*,
not the information:

1. **Group** by `(company, normalized title)`.
2. **Pick the reachable variant**, ranking on eligibility first and score only as
   a tie-break: `home country > remote EU/EMEA > EU location > worldwide >
   everything else`. An eligible clone at 45 beats an unreachable one at 45, which
   raw score cannot express. **The tier strings are example config** — they must
   match the reasons your own geography rules emit.
3. **Keep the alternatives in the message** — `also open in: Poland, Portugal,
   Ireland, …` — so a fallback stays visible if the picked one closes.
4. **Retire the whole group in `seen`** via `cloneUrls`, or the sibling URLs
   arrive on the next run looking like new roles.

**Cross-source disagreement is treated as a lie, not a tie.** When the same role
arrives from two feeds with different locations, one feed is wrong, and it is
reliably the *optimistic* one. A role listed by one aggregator as "United Kingdom"
and by another as "Singapore" was Singapore-only in the employer's own posting —
and the inflated copy scored **17 points higher**, enough to top the batch. Same
failure mode as the WeWorkRemotely mislabels below. So on conflict the node keeps
the **least** eligible read and says `-sources disagree (a vs b) - took the
strictest` in the message. Useful side effect: two sources disagreeing becomes a
cheap automatic trigger for "open the employer's own board before believing
either".

`node test_collapse.mjs` covers all of it — country clones, cross-source conflict,
the eligibility tie-break, lone postings, and two different titles at one employer
staying separate. No network required.

### Mark only what you send

Worth knowing if you write your own dedup: it is tempting to mark every posting
you examine and then slice to the cap. That records the overflow as "sent", so
anything past the cap is **never announced at all** — the opposite of "it waits
for the next run". Gate on the threshold *before* dedup, and mark only the batch
that actually goes out.

## Editing

```bash
cd ~/Desktop/cv/n8n
# edit build_workflow.py (source list, weights, threshold live there)
python3 build_workflow.py
node test_pipeline.mjs              # dry run: counts + top 15, sends nothing
node test_collapse.mjs              # unit-tests the clone collapsing, no network
node test_pipeline.mjs --notify 3   # also pushes top 3 to Telegram

docker cp jobs-radar.workflow.json n8n-local:/tmp/jobs-radar.json
docker exec n8n-local n8n import:workflow --input=/tmp/jobs-radar.json
docker restart n8n-local
```

`test_pipeline.mjs` runs the actual Code-node scripts extracted from the
workflow JSON, so what it prints is what n8n will do.

To widen coverage, add company slugs to the `greenhouse` / `ashby` arrays in
`build_workflow.py`. Verify a slug first:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://boards-api.greenhouse.io/v1/boards/SLUG/jobs
curl -s -o /dev/null -w '%{http_code}\n' https://api.ashbyhq.com/posting-api/job-board/SLUG
curl -s 'https://api.lever.co/v0/postings/SLUG?mode=json' | head -c 200   # [] = live but empty
curl -s -o /dev/null -w '%{http_code}\n' https://apply.workable.com/api/v1/widget/accounts/SLUG
curl -s 'https://api.smartrecruiters.com/v1/companies/SLUG/postings?limit=1' # check totalFound > 0
```

## Known limits

- **No LinkedIn.** No public jobs API; scraping breaks and risks the account.
  The ATS boards above carry the same roles, with full descriptions.
- **Scoring is deterministic, not a judgement.** It ranks by title, geography
  and keywords — it cannot tell a genuinely good platform role from one that
  merely uses the right words. A pre-wired LLM rerank step is the upgrade path;
  it needs an Anthropic or OpenAI key in n8n credentials.
- **Dedup state is `seen.json` in this repo.** Deleting it re-announces everything.
  Seed `DONE_COMPANIES` with companies you have already applied to or ruled out —
  see the `_why` map inside the file for the reason on each.
- **`MAX_PER_RUN` is 12.** Anything above threshold beyond that waits for the next run,
  and the run log says how many were held back.
