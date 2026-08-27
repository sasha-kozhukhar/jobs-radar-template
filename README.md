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

- **Build Source List** — 128 endpoints: 34 Greenhouse boards,
  42 Ashby, **10 Personio**, **8 Teamtailor**, **4 Pinpoint** (+4 Pinpoint RSS date
  feeds, which contribute no postings of their own), 3 Recruitee, 3 Lever,
  **1 BambooHR**, 1 Workable (Hugging Face), 1 SmartRecruiters (Delivery Hero,
  pre-filtered with `q="product manager"`), **8 Getro VC talent boards**, and 9 aggregator feeds
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

  **Pinpoint** is the richest feed in this list: `postings.json` carries the full
  description plus separate `key_responsibilities` and `skills_knowledge_expertise`
  blocks — the requirements section that the 12000-char description cap exists to
  reach. All three are concatenated. A company's own careers domain serves the
  identical payload, so the `<tenant>.pinpointhq.com` form is used and the tenant is
  the only unknown.

  Four quirks, all of them the kind that fail silently:
  1. **`{ data: [...] }` collides with the response unwrap** in Normalize, which
     treats a `.data` key as n8n's HTTP-response envelope — so `parsed` arrives as
     the bare array and `parsed.data` is `undefined`. Written without this, it yields
     0 postings and no error.
  2. **No country field exists anywhere in the payload** — city + `province` is all
     there is, and `province` is inconsistent (the country for Paris, a region for a
     German city, a US state *name*, not code, for New York). A city outside the
     score node's `EU_WORD` list therefore loses the EU bonus, and `US_STATE` does
     not fire on "New York City, New York".
  3. **Only `Fully remote` is appended** to the location, never Hybrid/Onsite — the
     same rule `lever` and `workable` follow. Appending the work model
     unconditionally makes Pinpoint the only source able to trigger the hybrid
     penalty, for a fact its peers never report at all.
  4. **Neither Pinpoint feed is complete, so both are fetched.** `postings.json` has
     structured locations but **no date**; `/en/jobs.rss` has `pubDate` and the full
     `content:encoded` but **no location at all**, and only the English postings (on
     one board, 49 items vs 84 including localized duplicates). So the JSON supplies
     the postings and the RSS supplies `postedAt`, joined on the job id — the RSS
     `<link>` is `/jobs/308423` and that number is `job.id` in the JSON (49 of 50
     distinct ids covered on that board). This does **not** disturb Normalize's
     response↔source pairing, which is by array index: two source entries get two
     responses and the map stays 1:1. Localized duplicates share one `job.id`, so
     the join lands on the underlying job, which is what a posting age is a property
     of. `pinpoint-rss` is excluded from the "live but returning nothing" report in
     `radar.mjs`, since contributing zero postings is its correct behaviour.

     Worth doing: the dates change the answer. On the board this was built against,
     four PM roles were 58–90 days old, so all four take the −12 stale penalty and
     none clears 48 — one of them went 52 → 33. Without the join, a 72-day-old
     posting is announced as though it were fresh.

  **BambooHR** is the cheap one: `https://<tenant>.bamboohr.com/careers/list` is
  public JSON with no auth and no bot protection, and `.../careers/<id>/detail` adds
  the full JD, `datePosted` and `compensation`. Only the list is fetched, because
  Fetch Board does one request per source — so like `workable` and `smartrecruiters`
  these postings carry no description and no date, and score on title, department and
  country alone. One quirk: `atsLocation.province` is often just the country
  repeated, which rendered one city as `"Belgrade, Serbia, Serbia"`, so the location
  parts are deduped.

  For both platforms the tenant is simply the subdomain of any careers URL, and a
  subdomain that is not a customer answers `302 text/html` — so a typo surfaces as a
  dead board in `STATUS.md` rather than as silence.

  **Personio and Teamtailor were added 2026-08-20** to reach the small-EU-company
  bracket the big-brand boards miss — the segment an 11-person Munich ConTech firm
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
- **Relevant enough?** — threshold **48**. See "Read the whole posting" below before lowering it.
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

### Scarce credentials belong outside the keyword cap

Description keywords are capped at +26 because every tech posting name-drops "AI". But if the
configured profile holds something genuinely **scarce** — a regulatory credential, a licence,
a domain almost nobody in the applicant pool can answer — that term is not name-dropping, and
burying it in the capped bucket means the roles asking for the rarest thing on the CV rank no
higher than the roles asking for nothing in particular.

There is a `SCARCE` group scored **outside** `KW_CAP` with its own `SCARCE_CAP = 24`, checked
against title **and** description, plus matching title bonuses. The shipped terms are an
**example** (medical-device regulation, medtech standards, healthcare, public sector /
sovereign) — replace them with whatever is scarce about your own profile.

Two things learned wiring it up:

- **Exclude privacy acronyms.** GDPR and HIPAA appear in the application privacy notice at the
  bottom of half of Europe's postings. They measure boilerplate, not the role.
- **A domain match is not eligibility.** The health boost promotes roles that require a
  clinical credential; hence `-clinical credential required` (−40, large enough to survive the
  boost that promoted the role). It is a **penalty, not a drop** — "licensed clinicians"
  appears in plenty of JDs that do not demand one of the candidate, and a wrong drop is
  invisible, which is the worst failure mode a radar has. A labelled role low in the list costs
  one glance.

Also blocked: `product analyst` and friends. "Staff AI Product Analyst, **Product Management**"
clears a naive PM-title gate on its trailing words.

Calibrate against **labelled** roles, not by feel: score a handful you already judged good and
bad, and check the ordering. `node test_scoring.mjs` asserts the whole group, no network.

### Read the whole posting

Two defaults that quietly cost half the corpus, worth checking in any fork of this:

**1. Greenhouse needs `?content=true`.** Its list endpoint omits the `content` key entirely
unless asked — not truncated, absent. Without it, every Greenhouse posting scores on title and
location alone, so description keywords, language gates and the US-only hint are all dead for
those boards. Here that was 34 boards and ~47% of everything fetched. Cost of the fix: a large
board's response goes from ~330 KB to ~5 MB.

**2. A 2,500-character description cap lands inside the "About us" section.** Requirements —
standards, language demands, knockout conditions — live in the second half. Measured on one
board: 37 of 37 descriptions were longer than 2,500, median 8,188. Now 12,000.

**Both change what the threshold means.** With half the corpus unable to score a single keyword
hit, a threshold of 48 was unreachable and had to be lowered to 30; with descriptions actually
present the distribution moves up about 20 points (`>=50` went from 3 postings to 55 on one
4,609-posting sample), so 48 becomes meaningful again.

**One asymmetry before you retune.** The fix lifts ATS boards and leaves **aggregator** feeds
(arbeitnow, jobicy, himalayas, remoteok, …) exactly where they were — those always returned
descriptions. A single global threshold therefore cuts hardest into the half that was always
healthy. On a live dry run right after the change: new postings above 48 = 1, above 40 ≈ 5,
above 35 ≈ 12, above 30 = 18.

**And change it in both places.** `radar.yml` pins `THRESHOLD` as an env var *and* declares a
`workflow_dispatch` input with its own default — **the input default wins**, so editing
`radar.mjs` or the env line alone changes nothing.

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
**80** and another board's "Senior PM – AI Governance" scored **65** — the two roles
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

**The title is not a stable role key.** Grouping on the raw title cannot see that
`Senior Product Manager (100% Remote within Spain)` and `… (100% Remote within
Poland)` are one role — and clones that happen to share a single title will hide the
problem from your tests. Titles are therefore stripped of bracketed, pipe-tail and
trailing-dash segments that only qualify **where or how** the job is done: locations,
`remote`/`hybrid`, `100% within X`, and gendered German tags like `(m/w/d)` /
`(f/m/x)`. **Only those** — over-stripping is the opposite failure, merging
`(XDR & Exposure Management)` with `(Strategic Account Interactions)` into one role.
Both directions are asserted in `test_collapse.mjs`.

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
node test_scoring.mjs               # unit-tests the scarce-credential scoring, no network
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

# Pinpoint and BambooHR: the tenant is just the subdomain of any careers URL, and a
# non-customer subdomain answers 302/text-html, so a typo shows up as a dead board in
# STATUS.md rather than as silence. Both report their own count, so 0 vs live is clear.
curl -s https://SLUG.pinpointhq.com/postings.json | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["data"]))'
curl -s https://SLUG.bamboohr.com/careers/list   | python3 -c 'import sys,json;print(json.load(sys.stdin)["meta"]["totalCount"])'
```

### ATS platforms surveyed but not added

Probed with real requests while adding BambooHR and Pinpoint. All three work; none is
in the source list, because each needs a tenant decision rather than a code decision:

| Platform | Endpoint | Verified | Cost of adding it |
|---|---|---|---|
| **Workday** | `POST https://<t>.wd<N>.myworkdayjobs.com/wday/cxs/<t>/<site>/jobs` body `{"searchText":"product manager","limit":20,"offset":0}` | 200, `total: 1204` on one large tenant | The big-corporate segment nothing else here reaches. But **three** unknowns per company (tenant, `wd<N>` cluster, site name), `limit` caps at 20 so it needs pagination, results are relevance-ordered not newest-first, and `postedOn` is prose (`"Posted 30+ Days Ago"`). Descriptions need a second fetch. |
| **join.com** | `https://join.com/api/public/companies/<numericId>/jobs?page=1&pageSize=5` | 200 | Reaches the DACH-SMB bracket. Two costs: the id is numeric and comes from `__NEXT_DATA__` → `initialState.company.id` (the same ritual Getro needs), and `pageSize` is capped at **5**, so a 30-posting board is 6 requests. Carries a real `createdAt` and an ISO country code, no description. |
| **Rippling** | `https://api.rippling.com/platform/api/ats/v1/board/<slug>/jobs` | 200, 736 postings on one tenant | Plain GET, no auth, no pagination. But title / department / `workLocation` only — no description, no date — and the customer base skews US. |

Probed and **not** resolved: softgarden, Jobylon, Homerun, Breezy, Factorial, Comeet,
Huntflow, Zoho Recruit, Careerpuck, HeyJobs. Each 404'd on a guessed tenant or path,
which rules out the guess, not the platform — they need a known customer URL to work
backwards from before any conclusion.

## Geography scoring — read this before re-targeting

Adding Pinpoint exposed that **both location lists were country-level while most
boards write a bare city**. Measured on one 9,720-posting corpus: **4,197 (43%) had
a location matching neither the EU nor the US pattern.** If you re-target this radar
at your own geography, re-run that census before trusting the filter.

The damage is one-sided, and it silently costs the radar its main filter:

| Fix | Postings affected |
|---|---|
| Bare US city names now trigger the −32 US-only penalty (`US_CITY`) | **1,821** were escaping it entirely |
| EU cities whose country was already listed now earn the +9 EU bonus | **515** were losing it |

"San Francisco" alone appeared 1,082 times and scored as though its location were
unknown, because `US_STATE` needs a `", CA"` suffix that those postings do not
have. In the other direction `EU_WORD` listed `germany` but not `munich`, `sweden`
but not `stockholm`, `poland` but not `warsaw`, and `\bczech\b` did not match
`Czechia`. The city vocabulary is now the same one `COLLAPSE`'s `LOC_TAG` already
carried.

Two related bugs, both the same mistake in different clothes — **reading a place out
of the description and treating it as an eligibility statement**:

- **`ANY_WORD` was tested against location + the first 400 description chars**, so a
  company blurb was enough. One board's "enabling sustainable growth for businesses
  worldwide" handed its *office-bound* roles the full +16 worldwide bonus, and a
  Prague office role the same. On a 33-posting sample, 2 of the 4 worldwide bonuses
  awarded were phantoms and one was above threshold. Now only the location field can
  claim it, plus a narrow `ANY_DESC` for phrasings a blurb does not produce
  ("work from anywhere", "anywhere in the world", "fully distributed").
- **The EU-remote bonus had the same hole, and the first fix reopened it.** An
  initial `EU_DESC` accepted "based in Europe" anywhere in the description, which
  promoted an **India-based** role to 54 with a "remote EU/EMEA" bonus off the
  sentence "…teams based in Europe…". `EU_DESC` now matches only role-eligibility
  phrasing (`remote within Europe`, `candidates must be based in Europe`,
  `eligible to work in the EU`). Anything softer falls through to plain `remote` +7 —
  the honest read of "the text does not say".

All of the above are covered by `node test_scoring.mjs` (checks 10–16), including a
guard that an EU city is never read as a US state code: `"Mannheim, DE"` is Delaware
to `US_STATE`, and only `EU_WORD` winning first prevents a −32.

## Why the threshold is 40, and what had to change first

The single most useful measurement made on this radar: **the one application that ever
produced an interview scored 39 under the code of the day before, and exactly 48 after a
geography fix.** A gate deciding your one success by a single point is measuring noise.
Three things changed together — individually, any one of them makes the radar worse.

**1. Application history reaches the scorer at all.** On the measured corpus, **65 of the
83 postings above threshold (78%) were companies already applied to or doors already
closed.** The list existed only in `hunt.mjs`, the manual triage script, and only as a
display flag, so it drifted from the application log every time an application went out.

It now lives in `build_workflow.py` (`DONE_COMPANIES` / `CLOSED_DOORS` — **replace both
with your own**) and rides on every posting as `history`, which `hunt.mjs` consumes
instead of its own copy. Deliberately an **annotation, not a filter**, and that
distinction is the lesson: a hard drop once hid the best posting of the week, because a
company-level filter cannot tell that a *new* role at a company you already applied to is
a level up. `applied` gets a `⚠ already applied` line in the notification; only `closed`
is suppressed.

`history` is kept **out of `reasons`** on purpose: `COLLAPSE`'s `eligibility()` parses
that array to choose which country clone is takeable, and a history tag in there is one
more string for it to misread.

**2. The working-method block scores.** A keyword scorer reads title and location well
and reads *working-method* requirements barely at all — so a JD asking for precisely your
rarest habit can score below a JD asking for nothing in particular. Here the signals were
daily Claude/Cursor use, spec-driven delivery, AI-first teams and agentic products, and
they had been contributing nothing beyond a generic `agents` tag. Adding `WORKING_METHOD`:
that interview posting went **48 → 70**, corpus-wide `>=48` went **83 → 100**. Retune the
list to whatever your own rare habit is.

**Gated, and the gate is the point.** Measured ungated first, it did what a content bonus
must never do — rescued postings that had already failed the location gate, promoting an
**India-based role 38 → 60** and a **Remote-U.S. one 38 → 48** on working-method words
alone. It now requires an *affirmative* eligibility reason, the same test `hunt.mjs`
already used. That cut the newly-promoted set from 24 to 17, all actually eligible.
Capped at 22 like the other buckets.

**3. Only then, the threshold: 48 → 40.** `MAX_PER_RUN` already caps what goes out per
run, so volume never needed a second guard; the threshold was deleting near-misses instead
of ranking them last. At 40 they arrive at the bottom of the batch, where a human can
still see them.

Lowering it exposed one thing the higher number had been hiding: an explicitly
**US-only** posting reached the batch (still 46 after its −32). `hunt.mjs` had always
filtered `-US-only` out of its shortlist, so the notification step now does the same.
That is the second and last suppression; everything else is annotated and ranked.

**Result on a live dry run:** 9,895 postings → 427 PM-titled → 327 distinct roles after
collapsing clones → **10 above 40**, i.e. one `MAX_PER_RUN` batch, topped by a company
that had never appeared in any previous run.

**Still open — the structural fix rather than a fifth regex.** Several of the worst bugs
found in this scorer were the same family: keyword regexes reading a place, a date or a
requirement out of free text. `WORKING_METHOD` is another regex of that family; it is
measured and it works, but the underlying limit stands. The upgrade named in
**Known limits** below — cheap scorer as a recall filter on title and geography, then an
LLM reranking the survivors — solves the class instead of one instance. It needs an API
key, which is why it is not done here.

## Known limits

- **Only EU and US geography is modelled.** The location census turned up real volume
  in places that are neither: Canada/Toronto (~75), India/Bangalore (~150), Singapore
  (132), Tokyo (116), Sydney/Australia (~95), Brazil/São Paulo (~70), Mexico, Seoul,
  Lima. None is EU-eligible, but they take the plain `remote` +7 rather than a
  penalty, because "not EU" is not the same claim as "US-only". Whether they should be
  penalised is a policy call for whoever re-targets this — deliberately left alone.
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
