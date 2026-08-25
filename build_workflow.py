#!/usr/bin/env python3
"""Builds the n8n 'Jobs Radar' workflow JSON.

Keeping the node JavaScript in readable Python strings and dumping via json.dump
avoids hand-escaping newlines/quotes inside the workflow JSON.
"""
import json
import pathlib

import os

# Secrets come from the environment. Never commit the real values.
#   export TELEGRAM_TOKEN=...   export TELEGRAM_CHAT_ID=...
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TELEGRAM_TOKEN_PLACEHOLDER")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID_PLACEHOLDER")
# 48 required AI/domain keyword hits on top of a senior title; that filtered out
# plain "Senior Product Manager" roles entirely. 30 = senior title (24) + any
# positive geo signal (>=7), while a non-senior "Product Manager" (12) still
# cannot pass on title + geo alone.
SCORE_THRESHOLD = 48

# ---------------------------------------------------------------- source list
BUILD_SOURCES = r"""
// Curated, verified-live job sources. Add/remove freely.
// Greenhouse + Ashby expose official public JSON job boards.
const greenhouse = [
  'appfire', 'gitlab', 'elastic', 'vercel', 'cockroachlabs', 'anthropic',
  'datadog', 'twilio', 'cloudflare', 'figma', 'airtable', 'contentful',
  'typeform', 'mongodb',
  // EU fintech / B2B SaaS, added after the first day (all verified live)
  'make', 'remotecom', 'monzo', 'wise', 'adyen', 'amplitude', 'mixpanel',
  'bird', 'sumup', 'n26',
  // Spain scaleups + EU enterprise SaaS + conversational AI (verified live)
  'cabify', 'wallapop', 'celonis', 'polyai', 'parloa', 'gympass',
  // Added 2026-08-19 (verified live): EU fintech/devtools + London AI labs
  'gocardless', 'intercom', 'grafanalabs', 'deepmind',
];
const ashby = [
  'n8n', 'linear', 'ramp', 'openai', 'perplexity', 'langchain', 'replit',
  'supabase', 'posthog', 'browserbase', 'cohere', 'elevenlabs', 'writer',
  'sierra', 'decagon', 'vanta',
  // AI-native and EU companies, added after the first day (all verified live)
  'cursor', 'lovable', 'harvey', 'qonto', 'gorgias', 'photoroom', 'alan',
  'doctolib', 'pennylane', 'ledger', 'sifflet',
  // AI infra / eval tooling / EU AI (verified live). langfuse and braintrust are
  // LLM-evaluation companies — included because they matched this profile's specialism.
  'modal', 'baseten', 'weaviate', 'langfuse', 'braintrust', 'nabla', 'owkin',
  'poolside', 'synthesia', 'legora', 'tacto', 'granola', 'attio',
  // Added 2026-08-19 (verified live): Paris agents (dust), Berlin AI B2B (choco)
  'dust', 'choco',
];
const recruitee = ['hostaway', 'channable', 'bunq'];
// Teamtailor public JSON Feed. Nordic/EU mid-market. Caveat: the feed returns
// only the ~10 most recent postings per board and ignores ?page=, which suits a
// radar looking for new roles but means it is not a full board listing.
const teamtailor = [
  'tibber', 'anyfin', 'templafy', 'podimo', 'lunar', 'instabee',
  'tacton', 'doconomy',
];
// Personio XML boards — the DACH startup ATS, the segment the big-brand boards
// miss entirely (alago, the 08-20 Munich match, sits in exactly this bracket).
// Caveat: <jobDescriptions> is often empty, so scoring falls back to title +
// office. Personio rate-limits hard: 429s appear when requests are not spaced.
const personio = [
  'userlane', 'alasco', 'capmo', 'building-radar', 'koppla', 'celus',
  'adverity', '1komma5grad', 'ottonova', 'personio',
];
// Lever public postings API. Verified live 2026-08-19; mistral exists but
// publishes 0 postings through the API, so it is not listed.
const lever = ['pigment', 'contentsquare', 'aircall'];
// Workable widget API (v1 GET; the v3 endpoint needs POST which Fetch Board
// cannot do). No description in the list response — title/location only.
const workable = ['huggingface'];
// SmartRecruiters public postings API. Full-text q filter with an exact phrase
// keeps Delivery Hero's 1000+ postings down to a fetchable page; the score
// node's title gate drops the non-PM remainder.
const smartrecruiters = ['DeliveryHero'];
// Getro powers the talent boards of most European VCs: one endpoint per fund
// covers its whole portfolio, which is the alago-sized bracket that guessing
// individual ATS tenants keeps missing. Ids come from the board's own
// __NEXT_DATA__ (props.pageProps.network.id) — see README for how to add a fund.
// This is the only POST source: the API is POST-only (GET 404s) and it insists
// on exactly `accept: application/json` — `*/*` returns 406.
// The default ordering is already newest-first, so page 0 is what a radar wants.
const getro = [
  ['Point Nine', 1680], ['Atomico', 36986], ['Cherry Ventures', 44081],
  ['Earlybird', 617], ['Dawn Capital', 3063], ['Firstminute Capital', 178],
  ['HV Capital', 234], ['Seedcamp', 4186],
];

const out = [];
for (const org of greenhouse) {
  // `?content=true` is not optional: without it Greenhouse's list endpoint omits the
  // `content` key altogether, so every posting from these boards arrives with NO
  // description and can only score on title and location. Cost: a large board's
  // response goes from ~330 KB to ~5 MB.
  out.push({ json: { kind: 'greenhouse', company: org,
    url: `https://boards-api.greenhouse.io/v1/boards/${org}/jobs?content=true` } });
}
for (const org of ashby) {
  out.push({ json: { kind: 'ashby', company: org,
    url: `https://api.ashbyhq.com/posting-api/job-board/${org}` } });
}
for (const org of recruitee) {
  out.push({ json: { kind: 'recruitee', company: org,
    url: `https://${org}.recruitee.com/api/offers/` } });
}
for (const org of lever) {
  out.push({ json: { kind: 'lever', company: org,
    url: `https://api.lever.co/v0/postings/${org}?mode=json` } });
}
for (const org of workable) {
  out.push({ json: { kind: 'workable', company: org,
    url: `https://apply.workable.com/api/v1/widget/accounts/${org}` } });
}
for (const org of teamtailor) {
  out.push({ json: { kind: 'teamtailor', company: org,
    url: `https://${org}.teamtailor.com/jobs.json` } });
}
for (const org of personio) {
  out.push({ json: { kind: 'personio', company: org,
    url: `https://${org}.jobs.personio.de/xml` } });
}
for (const [fund, id] of getro) {
  out.push({ json: {
    kind: 'getro', company: fund,
    url: `https://api.getro.com/api/v2/collections/${id}/search/jobs`,
    method: 'POST',
    headers: { accept: 'application/json', 'content-type': 'application/json' },
    body: JSON.stringify({ query: 'product manager', page: 0 }),
    // All eight funds hit the same host, and Datadog bot protection 403s the
    // burst if they follow each other at the normal 200 ms spacing.
    delayMs: 4000,
  } });
}
for (const org of smartrecruiters) {
  out.push({ json: { kind: 'smartrecruiters', company: org,
    url: `https://api.smartrecruiters.com/v1/companies/${org}/postings?q=%22product%20manager%22&limit=100` } });
}
out.push({ json: { kind: 'remoteok', company: 'RemoteOK',
  url: 'https://remoteok.com/api' } });
out.push({ json: { kind: 'himalayas', company: 'Himalayas',
  url: 'https://himalayas.app/jobs/api?limit=100' } });
out.push({ json: { kind: 'wwr', company: 'WeWorkRemotely',
  url: 'https://weworkremotely.com/categories/remote-product-jobs.rss' } });

// Aggregators added after the first day. Remotive and Jobicy are the useful ones:
// they expose a real location field (candidate_required_location / jobGeo) rather
// than WeWorkRemotely's optimistic "Anywhere in the World".
out.push({ json: { kind: 'remotive', company: 'Remotive',
  url: 'https://remotive.com/api/remote-jobs?category=product&limit=100' } });
out.push({ json: { kind: 'jobicy', company: 'Jobicy',
  url: 'https://jobicy.com/api/v2/remote-jobs?count=100' } });
out.push({ json: { kind: 'workingnomads', company: 'WorkingNomads',
  url: 'https://www.workingnomads.com/api/exposed_jobs/' } });
out.push({ json: { kind: 'arbeitnow', company: 'Arbeitnow',
  url: 'https://www.arbeitnow.com/api/job-board-api' } });
for (const page of [1, 2]) {
  out.push({ json: { kind: 'themuse', company: 'TheMuse',
    url: `https://www.themuse.com/api/public/jobs?category=Product%20Management&page=${page}` } });
}

return out;
"""

# ----------------------------------------------------------------- normalize
NORMALIZE = r"""
// Pair each HTTP response back to its source (item order is preserved).
const sources = $('Build Source List').all();
const responses = $input.all();

const strip = (s) => String(s || '')
  .replace(/<[^>]*>/g, ' ')
  .replace(/&[a-z]+;/gi, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const jobs = [];

responses.forEach((resp, i) => {
  const src = (sources[i] && sources[i].json) || {};
  const kind = src.kind;
  const raw = resp.json.data !== undefined ? resp.json.data : resp.json;

  let parsed = raw;
  if (typeof raw === 'string' && kind !== 'wwr' && kind !== 'personio') {
    try { parsed = JSON.parse(raw); } catch (e) { return; }
  }

  const push = (o) => {
    if (!o.title || !o.url) return;
    jobs.push({
      source: kind,
      company: o.company || src.company,
      title: strip(o.title),
      location: strip(o.location) || 'n/a',
      url: o.url,
      // 2500 cuts most postings off inside their "About us" section, so the
      // requirements -- where standards, language demands and knockout conditions live
      // -- are never read. Measured on one board: 37/37 descriptions were longer than
      // 2500, median 8,188.
      description: strip(o.description).slice(0, 12000),
      postedAt: o.postedAt || null,
    });
  };

  try {
    if (kind === 'greenhouse') {
      (parsed.jobs || []).forEach((j) => push({
        title: j.title,
        url: j.absolute_url,
        location: j.location && j.location.name,
        description: j.content,
        // first_published, not updated_at: a stale posting "bumped" by an edit
        // must still look stale (a role open 6+ weeks may already be filled).
        postedAt: j.first_published || j.updated_at,
      }));
    } else if (kind === 'ashby') {
      (parsed.jobs || []).forEach((j) => push({
        title: j.title,
        url: j.jobUrl || j.applyUrl,
        location: j.location || (j.address && j.address.postalAddress
          && j.address.postalAddress.addressRegion),
        description: j.descriptionPlain || j.descriptionHtml,
        postedAt: j.publishedAt,
      }));
    } else if (kind === 'recruitee') {
      (parsed.offers || []).forEach((j) => push({
        title: j.title,
        url: j.careers_url || j.url,
        location: [j.city, j.country].filter(Boolean).join(', '),
        description: j.description,
        postedAt: j.published_at,
      }));
    } else if (kind === 'lever') {
      (Array.isArray(parsed) ? parsed : []).forEach((j) => push({
        title: j.text,
        url: j.hostedUrl || j.applyUrl,
        location: [
          j.categories && j.categories.location,
          j.workplaceType === 'remote' ? 'Remote' : '',
        ].filter(Boolean).join(', '),
        description: j.descriptionPlain || j.description,
        // Lever createdAt is epoch milliseconds, not a date string.
        postedAt: j.createdAt ? new Date(j.createdAt).toISOString() : null,
      }));
    } else if (kind === 'workable') {
      (parsed.jobs || []).forEach((j) => push({
        title: j.title,
        url: j.url || j.application_url,
        location: [j.city, j.country, j.telecommuting ? 'Remote' : '']
          .filter(Boolean).join(', '),
        description: j.description,
        postedAt: j.published_on,
      }));
    } else if (kind === 'teamtailor') {
      (parsed.items || []).forEach((j) => {
        // Location lives in the embedded schema.org JobPosting, not the feed item.
        const jp = j._jobposting || {};
        const place = Array.isArray(jp.jobLocation) ? jp.jobLocation[0] : jp.jobLocation;
        const addr = (place && place.address) || {};
        push({
          title: j.title,
          url: j.url,
          location: [addr.addressLocality, addr.addressCountry].filter(Boolean).join(', '),
          description: j.content_html || jp.description,
          postedAt: j.date_published || jp.datePosted,
        });
      });
    } else if (kind === 'personio') {
      // XML, and the feed carries no job URL — it has to be built from the id.
      const xml = String(raw);
      (xml.match(/<position>[\s\S]*?<\/position>/g) || []).forEach((chunk) => {
        const grab = (tag) => {
          const m = chunk.match(new RegExp('<' + tag + '>([\\s\\S]*?)<\\/' + tag + '>'));
          return m ? m[1].replace(/^<!\[CDATA\[/, '').replace(/\]\]>$/, '').trim() : '';
        };
        const id = grab('id');
        if (!id) return;
        const offices = [grab('office')]
          .concat((chunk.match(/<additionalOffices>[\s\S]*?<\/additionalOffices>/) || [''])[0]
            .match(/<office>([\s\S]*?)<\/office>/g) || [])
          .map((o) => String(o).replace(/<\/?office>/g, '').trim())
          .filter(Boolean);
        push({
          title: grab('name'),
          url: `https://${src.company}.jobs.personio.de/job/${id}`,
          location: [...new Set(offices)].join(', '),
          description: grab('jobDescriptions'),
          postedAt: grab('createdAt'),
        });
      });
    } else if (kind === 'getro') {
      // company is the portfolio company, not the fund; url already points at
      // the company's own ATS, so a job also seen on a directly-monitored board
      // dedupes on URL by itself. The search API returns description: null.
      ((parsed.results && parsed.results.jobs) || []).forEach((j) => push({
        title: j.title,
        company: (j.organization && j.organization.name) || src.company,
        url: j.url,
        location: (j.locations || []).slice(0, 3).join(', '),
        description: '',
        postedAt: j.created_at ? new Date(j.created_at * 1000).toISOString() : null,
      }));
    } else if (kind === 'smartrecruiters') {
      (parsed.content || []).forEach((j) => push({
        title: j.name,
        company: (j.company && j.company.name) || src.company,
        url: `https://jobs.smartrecruiters.com/${(j.company && j.company.identifier) || src.company}/${j.id}`,
        location: j.location ? [
          j.location.city,
          j.location.country,
          j.location.remote ? 'Remote' : '',
        ].filter(Boolean).join(', ') : 'n/a',
        description: '',
        postedAt: j.releasedDate,
      }));
    } else if (kind === 'remoteok') {
      const arr = Array.isArray(parsed) ? parsed.slice(1) : [];
      arr.forEach((j) => push({
        title: j.position,
        company: j.company,
        url: j.url || j.apply_url,
        location: j.location || 'Remote',
        description: j.description,
        postedAt: j.date,
      }));
    } else if (kind === 'himalayas') {
      (parsed.jobs || []).forEach((j) => push({
        title: j.title,
        company: j.companyName,
        url: j.applicationLink || j.guid,
        location: (j.locationRestrictions || []).join(', ') || 'Remote',
        description: j.excerpt || j.description,
        postedAt: j.pubDate,
      }));
    } else if (kind === 'remotive') {
      (parsed.jobs || []).forEach((j) => push({
        title: j.title,
        company: j.company_name,
        url: j.url,
        location: j.candidate_required_location || 'Remote',
        description: j.description,
        postedAt: j.publication_date,
      }));
    } else if (kind === 'jobicy') {
      (parsed.jobs || []).forEach((j) => push({
        title: j.jobTitle,
        company: j.companyName,
        url: j.url,
        location: Array.isArray(j.jobGeo) ? j.jobGeo.join(', ') : (j.jobGeo || 'Remote'),
        description: j.jobDescription || j.jobExcerpt,
        postedAt: j.pubDate,
      }));
    } else if (kind === 'workingnomads') {
      (Array.isArray(parsed) ? parsed : []).forEach((j) => push({
        title: j.title,
        company: j.company_name,
        url: j.url,
        location: j.location || 'Remote',
        description: j.description,
        postedAt: j.pub_date,
      }));
    } else if (kind === 'arbeitnow') {
      (parsed.data || []).forEach((j) => push({
        title: j.title,
        company: j.company_name,
        url: j.slug ? `https://www.arbeitnow.com/view/${j.slug}` : j.url,
        location: [j.location, j.remote ? 'Remote' : ''].filter(Boolean).join(', '),
        description: j.description,
        postedAt: j.created_at,
      }));
    } else if (kind === 'themuse') {
      (parsed.results || []).forEach((j) => push({
        title: j.name,
        company: j.company && j.company.name,
        url: j.refs && j.refs.landing_page,
        location: (j.locations || []).map((l) => l.name).join(', '),
        description: j.contents,
        postedAt: j.publication_date,
      }));
    } else if (kind === 'wwr') {
      const xml = String(raw);
      const items = xml.split('<item>').slice(1);
      items.forEach((chunk) => {
        const grab = (tag) => {
          const m = chunk.match(new RegExp('<' + tag + '>([\\s\\S]*?)<\\/' + tag + '>'));
          if (!m) return '';
          return m[1].replace(/^<!\[CDATA\[/, '').replace(/\]\]>$/, '');
        };
        push({
          title: grab('title'),
          company: grab('company') || 'WeWorkRemotely',
          url: grab('link'),
          location: grab('region') || 'Remote',
          description: grab('description'),
          postedAt: grab('pubDate'),
        });
      });
    }
  } catch (e) {
    // A single malformed board must not kill the whole run.
  }
});

return jobs.map((j) => ({ json: j }));
"""

# --------------------------------------------------------------------- score
SCORE = r"""
// EXAMPLE relevance profile — REPLACE THIS WITH YOUR OWN.
// The keyword lists, seniority weights, geography bonuses and language gates below
// encode one candidate's search (senior/lead PM, B2B SaaS + AI products, EU-based).
// Everything from TITLE_LEAD down to the language penalties is configuration, not logic.
//
// Design note: signal lives in the TITLE and the LOCATION field. Almost every
// tech job description name-drops "AI", so description keywords are scored
// weakly and capped — otherwise everything saturates at 100.

const TITLE_LEAD = [
  'staff product manager', 'principal product manager', 'lead product manager',
  'group product manager', 'head of product', 'product lead', 'product director',
  'director of product', 'director, product', 'director product management',
  'vp product', 'vp of product', 'chief product',
];
const TITLE_SENIOR = ['senior product manager', 'sr product manager', 'sr. product manager'];
const TITLE_BASE = ['product manager', 'product owner', 'product management'];
const TITLE_AI = [
  'ai product', 'product manager - ai', 'product manager, ai', 'ai pm',
  'genai product', 'llm product', 'agent product',
];
const TITLE_PLATFORM = [
  'platform product manager', 'technical product manager',
  'product manager, platform', 'product manager - platform',
  'product manager, ai platform',
];

// Description keywords: weak individually, capped in aggregate.
const KW = [
  [/\bagent(ic|s)?\b/i, 5, 'agents'],
  [/\bllm|large language model|genai|gen ai\b/i, 4, 'LLM'],
  [/\beval(s|uation)? (set|suite|harness)|benchmark/i, 5, 'evals'],
  [/orchestrat/i, 4, 'orchestration'],
  [/\brag\b|retrieval.augmented/i, 3, 'RAG'],
  [/developer tool|devtool|developer experience|developer platform/i, 4, 'devtools'],
  [/governance|guardrail|observability|finops|audit trail/i, 4, 'governance'],
  [/\bb2b\b|enterprise saas/i, 3, 'B2B SaaS'],
  [/open ?source/i, 3, 'open source'],
  [/fintech|insurtech|crypto|hospitality|proptech|govtech|geospatial|medtech/i, 3, 'domain match'],
  [/pricing|monetiz|go-to-market/i, 2, 'commercial'],
  // Non-AI signals that still map to real CV evidence. Without these, a strong
  // growth/PLG role scores on title alone and falls under the threshold — which is
  // exactly what happened to one strong PLG role (scored 44, missed) even though it
  // was the closest fit found all day.
  [/product.led growth|\bplg\b/i, 5, 'PLG'],
  [/activation|onboarding|retention|churn/i, 4, 'activation/retention'],
  [/\ba\/b test|experimentation|experiment/i, 4, 'experimentation'],
  [/funnel|cohort|\bsql\b/i, 3, 'analytics'],
  [/coach|mentor|lead a team|managing product managers|line manage/i, 3, 'people leadership'],
  [/pre.sales|rfp|tender|procurement/i, 3, 'pre-sales'],
];
const KW_CAP = 26;

// Credentials that are genuinely SCARCE in the PM pool, scored OUTSIDE KW_CAP for the
// same reason the title bonuses are: these are not name-dropped. Every tech posting
// says "AI" somewhere, which is why description keywords are capped — but a JD that
// says "EU MDR" or "ISO 14971" is naming something almost no product manager can
// answer, and the few who can are worth more than a keyword match. If the
// configured profile holds a scarce credential, keep it OUT of the capped bucket, or
// the roles that specifically ask for the rarest thing on the CV will rank
// no higher than the roles that ask for nothing in particular.
// EXAMPLE GROUP -- replace these terms with whatever is scarce about your own profile.
//
// Deliberately absent: GDPR and HIPAA. They appear in the privacy notice at the
// bottom of half the postings in Europe, so they measure boilerplate, not the role.
const SCARCE = [
  [/eu mdr|mdr 2017\/745|\bivdr\b/i, 12, 'medical-device regulation'],
  [/iso ?14971|iec ?62366|iec ?62304|iso ?13485|510\(k\)|fda (submission|clearance|approval|requirement)/i, 12, 'medtech standards'],
  [/medical device|clinical (software|workflow|documentation|safety|validation)|regulatory (documentation|submission|affairs|compliance)/i, 8, 'regulated medtech'],
  [/\bpatient|clinician|\bdoctor|\bclinic\b|\behr\b|\bemr\b|practice management|health ?tech|digital health/i, 5, 'healthcare domain'],
  [/public sector|govtech|\bgovernment\b|sovereign|smart city|critical infrastructure|defence|defense/i, 6, 'public sector / sovereign'],
  [/eu ai act|regulated (environment|industry|data)|audit(ability|able)|traceability/i, 5, 'regulated environment'],
];
// Capped too, just far higher than the boilerplate bucket: a genuine medtech-regulatory
// JD should be able to clear the threshold on this signal alone, but not saturate.
const SCARCE_CAP = 24;


// Title-level topic bonuses (these are real signal, not boilerplate).
const TITLE_KW = [
  [/\bai\b|artificial intelligence|genai|\bllm\b/i, 18, 'AI in title'],
  [/\bagent(ic|s)?\b/i, 14, 'agents in title'],
  [/\bplatform\b|infrastructure/i, 10, 'platform in title'],
  [/governance|compliance|trust|security/i, 8, 'governance in title'],
  [/\bapi(s)?\b|integration(s)?\b|ecosystem/i, 7, 'API/ecosystem in title'],
  // Same reasoning as SCARCE below: a health or public-sector title is a much stronger
  // match for a health / public-sector profile than a generic one, and it is never boilerplate in a title.
  [/health|clinical|medical|patient|care\b|\bmedtech\b/i, 10, 'health in title'],
  [/public sector|government|govtech|sovereign|defence|defense/i, 8, 'public sector in title'],
];

// Titles that are PM-shaped but off-track for the configured profile.
const TITLE_BLOCK = [
  [/\bintern(ship)?\b|graduate|junior|entry.level|working student|apprentice|trainee/i, 'junior'],
  [/\bengineer(ing)?\b|\bdeveloper\b|\bsre\b|data scientist|\bdesigner\b|\barchitect\b/i, 'eng/design'],
  [/\bcounsel\b|attorney|paralegal|\blegal\b/i, 'legal'],
  [/account executive|\bsales\b|recruiter|customer success|support engineer|solutions engineer/i, 'non-PM'],
  [/marketing|growth marketing|brand|content strateg/i, 'marketing'],
  [/\bintern\b|contract recruiter|localization/i, 'other'],
  // "Staff AI Product Analyst, Product Management" cleared the PM gate on the trailing
  // words and scored 70 once descriptions were switched on. An analyst title ending in the words
  // "Product Management" is still not a PM role.
  [/product analyst|data analyst|business analyst|analytics engineer/i, 'analyst'],
  [/\bintern\b|contract recruiter|localization/i, 'other'],
];

const US_STATE = /,\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b/;
const US_WORD = /\b(u\.?s\.?a?\.?|united states)\b/i;
const EU_WORD = /\b(emea|europe|european|spain|madrid|barcelona|germany|berlin|netherlands|amsterdam|portugal|lisbon|ireland|dublin|uk|united kingdom|london|poland|france|paris|italy|sweden|denmark|austria|belgium|czech|romania|bulgaria|greece|hungary|estonia|latvia|lithuania|croatia|serbia|slovakia|slovenia|finland|norway)\b/i;
const ANY_WORD = /\b(worldwide|anywhere|global|any location)\b/i;

const out = [];

for (const item of $input.all()) {
  const j = item.json;
  const title = (j.title || '').toLowerCase();
  const loc = j.location || '';
  const desc = j.description || '';

  // Gate 1: must be a product-management title.
  const isLead = TITLE_LEAD.some((t) => title.includes(t));
  const isSenior = TITLE_SENIOR.some((t) => title.includes(t));
  const isAi = TITLE_AI.some((t) => title.includes(t));
  const isPlatform = TITLE_PLATFORM.some((t) => title.includes(t));
  const isPm = isLead || isSenior || isAi || isPlatform
    || TITLE_BASE.some((t) => title.includes(t));
  if (!isPm) continue;

  // Gate 2: PM-shaped but wrong track.
  if (TITLE_BLOCK.some(([re]) => re.test(title))) continue;

  let score = 0;
  const reasons = [];

  // Seniority. Tune to your level: for a 10+ year candidate a plain PM role is a step down.
  if (isLead) { score += 28; reasons.push('lead/staff title'); }
  else if (isSenior) { score += 24; reasons.push('senior title'); }
  else { score += 12; reasons.push('PM title'); }

  if (isAi) { score += 6; reasons.push('AI role'); }
  if (isPlatform) { score += 5; reasons.push('platform role'); }

  for (const [re, pts, label] of TITLE_KW) {
    if (re.test(title)) { score += pts; reasons.push(label); }
  }

  let kw = 0;
  const kwHits = [];
  for (const [re, pts, label] of KW) {
    if (re.test(desc)) { kw += pts; kwHits.push(label); }
  }
  if (kw > 0) {
    score += Math.min(kw, KW_CAP);
    reasons.push(...kwHits);
  }

  // Scarce credentials: own bucket, own cap, checked against title AND description so
  // a role is not missed just because the standard is named in the requirements list.
  let scarce = 0;
  const scarceHits = [];
  for (const [re, pts, label] of SCARCE) {
    if (re.test(desc) || re.test(title)) { scarce += pts; scarceHits.push(label); }
  }
  if (scarce > 0) {
    score += Math.min(scarce, SCARCE_CAP);
    reasons.push(...scarceHits);
  }


  // Geography, judged on the location field only.
  //
  // WeWorkRemotely is not trustworthy here: it labels Coinbase and Stripe roles
  // "Anywhere in the World" while those companies' own ATS says "Remote - USA".
  // On a live run that put three phantom US-only roles in the top six. So for the
  // aggregator sources, a worldwide claim earns a small bonus instead of a big one,
  // and any US signal anywhere in the posting is treated as a likely restriction.
  const AGGREGATOR = ['wwr','remoteok','himalayas','remotive','jobicy','workingnomads','arbeitnow','themuse'].includes(j.source);

  const geo = `${loc} ${desc.slice(0, 400)}`;
  const isRemote = /\bremote\b|\bdistributed\b/i.test(geo);
  const usOnly = (US_STATE.test(loc) || US_WORD.test(loc)) && !EU_WORD.test(loc) && !ANY_WORD.test(loc);
  const usHint = AGGREGATOR && /remote\s*[-–,]?\s*(usa|us\b)|united states|\bus only\b|us.based/i.test(desc);

  if (ANY_WORD.test(geo)) {
    const pts = AGGREGATOR ? 6 : 16;
    score += pts;
    reasons.push(AGGREGATOR ? 'worldwide (unverified)' : 'worldwide');
  } else if (EU_WORD.test(geo) && isRemote) { score += 16; reasons.push('remote EU/EMEA'); }
  else if (EU_WORD.test(loc)) { score += 9; reasons.push('EU location'); }
  else if (isRemote && !usOnly) { score += 7; reasons.push('remote'); }

  if (usOnly) { score -= 32; reasons.push('-US-only'); }
  else if (usHint) { score -= 20; reasons.push('-likely US-only'); }

  // A role that names Spain is worth more than a generic EU one: no visa friction,
  // no relocation conversation, no employment-structure question.
  if (/\bspain\b|madrid|barcelona|m[aá]laga|granada|valencia/i.test(loc)) {
    score += 7; reasons.push('Spain-eligible');
  }
  if (/\bhybrid\b/i.test(loc)) { score -= 10; reasons.push('-hybrid'); }
  if (/\bon.?site\b/i.test(loc)) { score -= 12; reasons.push('-onsite'); }

  // Language gates. Penalise roles run in a language you do not work in; adjust to your own.
  if (/\b(se requiere|imprescindible|espa[nñ]ol|castellano)\b/i.test(desc)) {
    score -= 25; reasons.push('-Spanish-language');
  }
  if (/fluent (in )?(german|deutsch|french|dutch|italian)|native (german|french)/i.test(desc)) {
    score -= 18; reasons.push('-other language');
  }

  // -40, not a smaller number, because it has to survive the health boost that put the
  // role near the top in the first place: a Clinical Product Lead scored 94 raw
  // (health in title +10, medical-device regulation +12, regulated medtech +8,
  // healthcare domain +5) while asking for a medical degree. Deliberately a penalty and
  // not a drop -- "licensed clinicians" appears in plenty of JDs that do not require one
  // of the candidate, and a wrong drop is invisible, which is the failure mode this repo
  // most wants to avoid. A labelled role low in the list costs one glance.
  if (/medical degree|practi[sc]ing medicine|active licensure|clinical licensure|registered nurse/i.test(desc)) {
    score -= 40; reasons.push('-clinical credential required');
  }


  // Posting age. One application went to a role that had been open for six weeks and came back
  // "position filled" two days later — a posting live for 6+ weeks is
  // likely already in final rounds, so applying is racing a nearly-done pipeline.
  // Penalty-only: no freshness bonus, so borderline roles are not pushed above
  // the threshold just for being new. Missing/unparseable dates cost nothing.
  if (j.postedAt) {
    const t = Date.parse(j.postedAt);
    if (!Number.isNaN(t)) {
      const ageDays = Math.round((Date.now() - t) / 86400000);
      if (ageDays > 45) { score -= 12; reasons.push(`-stale ${ageDays}d`); }
      else if (ageDays > 30) { score -= 6; reasons.push(`-aging ${ageDays}d`); }
    }
  }

  score = Math.max(0, Math.min(100, Math.round(score)));
  out.push({ json: { ...j, score, reasons: [...new Set(reasons)] } });
}

out.sort((a, b) => b.json.score - a.json.score);
return out;
"""

# ------------------------------------------------------------------ collapse
# One employer posting one role across ten countries is one decision, not ten
# notifications. This is common and it is expensive: a single employer publishing
# two roles as 19 country clones can fill a whole MAX_PER_RUN batch, pushing
# everything else to the next run -- silently, because the cap does not announce
# itself.
#
# The naive fix -- keep the best-scoring clone, drop the rest -- is wrong. Clones
# are frequently NOT interchangeable: the same role is often country-locked with a
# different salary band per country, and sometimes only one clone is reachable
# without a work-authorisation fight. Dropping the wrong ones can hide the only
# clone worth applying to. So this collapses the *notification*, not the
# information: it picks the reachable variant and names the others in the message.
COLLAPSE = r"""
// Group scored postings into one entry per real role.
const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

// Plenty of employers bake the location into the title, which defeats grouping on
// the title alone -- "Senior Product Manager (100% Remote within Spain)" and
// "... (100% Remote within Poland)" are one role and two strings, and they will go
// out as two messages unless the qualifier is removed first.
//
// So drop bracketed / pipe / trailing-dash segments that only qualify WHERE or HOW
// the job is done -- but ONLY those. A meaningful parenthetical must survive, or
// this causes the opposite failure: "(XDR & Exposure Management)" and "(Strategic
// Account Interactions)" would merge into one role.
const LOC_TAG = new RegExp([
  'remote|hybrid|on.?site|onsite|within|relocation|\\d+ ?%',
  '[mfwdx](?:\\s*\\/\\s*[mfwdx]){1,2}',            // (m/w/d), (f/m/x), (d/f/m)
  'emea|apac|latam|europe|european|worldwide|anywhere|global',
  'spain|poland|portugal|ireland|greece|germany|france|italy|netherlands|belgium',
  'sweden|denmark|norway|finland|switzerland|austria|czech|romania|bulgaria',
  'hungary|estonia|latvia|lithuania|croatia|serbia|slovakia|slovenia|turkey',
  'united kingdom|england|scotland|wales|\\buk\\b|\\bus\\b|\\busa\\b',
  'united states|canada|israel|singapore|india|brazil|mexico|japan|australia',
  'madrid|barcelona|valencia|malaga|warsaw|krakow|berlin|munich|hamburg|cologne',
  'frankfurt|paris|london|manchester|dublin|amsterdam|utrecht|rotterdam|lisbon',
  'porto|milan|rome|turin|vienna|zurich|geneva|stockholm|copenhagen|oslo',
  'helsinki|prague|budapest|bucharest|athens|sofia|tallinn|riga|vilnius|zagreb',
].join('|'), 'i');

const stripLocationTags = (title) => {
  let t = (title || '');
  // Bracketed segments: keep unless the segment is only a location/work-model tag.
  t = t.replace(/[([]([^)\]]*)[)\]]/g, (m, inner) => (LOC_TAG.test(inner) ? ' ' : m));
  // Pipe-separated tail segments, e.g. "Role | 100% Remote within Europe".
  const pipes = t.split('|');
  if (pipes.length > 1) {
    t = [pipes[0], ...pipes.slice(1).filter((seg) => !LOC_TAG.test(seg))].join(' ');
  }
  // A trailing dash segment, and only the trailing one -- "- Security Solutions"
  // has to survive while "- Berlin" does not.
  t = t.replace(/\s[-\u2013\u2014]\s([^-\u2013\u2014]*)$/, (m, tail) => (LOC_TAG.test(tail) ? ' ' : m));
  return t;
};

// Rank by what the configured profile can actually take, not by raw score: an
// eligible clone at 45 beats an unreachable clone at 45, which score alone cannot
// express. EXAMPLE TIERS -- these strings must match the reasons your own
// "Score vs Profile" geography rules emit. Edit alongside that profile.
const eligibility = (j) => {
  const r = (j.reasons || []).join(' ');
  if (/Spain named|Spain-eligible/.test(r)) return 4;   // your home country
  if (/remote EU\/EMEA/.test(r)) return 3;
  if (/EU location/.test(r)) return 2;
  if (/worldwide/.test(r)) return 1;
  return 0;
};

const groups = new Map();
for (const item of $input.all()) {
  const j = item.json;
  const key = norm(j.company) + '|' + norm(stripLocationTags(j.title));
  if (!groups.has(key)) groups.set(key, []);
  groups.get(key).push(j);
}

const out = [];
for (const variants of groups.values()) {
  if (variants.length === 1) { out.push({ json: variants[0] }); continue; }

  const sources = [...new Set(variants.map((v) => v.source).filter(Boolean))];

  // When the SAME role arrives from DIFFERENT sources with different locations,
  // one source is lying -- and it is reliably the optimistic one. A role that one
  // aggregator listed as "United Kingdom" and another as "Singapore" was
  // Singapore-only in the employer's own posting, and the inflated copy scored 17
  // points higher, which is enough to top a batch. Same failure as the
  // WeWorkRemotely "Anywhere in the World" mislabels documented in the README.
  // So on conflict, take the LEAST eligible read and say so, rather than letting a
  // phantom lead the run.
  const conflict = sources.length > 1
    && new Set(variants.map(eligibility)).size > 1;

  const ranked = [...variants].sort((a, b) => (conflict
    ? eligibility(a) - eligibility(b) || a.score - b.score
    : eligibility(b) - eligibility(a) || b.score - a.score));

  const pick = ranked[0];
  const others = ranked.slice(1);
  const alts = [...new Set(others.map((v) => v.location).filter(Boolean))];

  const reasons = [...(pick.reasons || [])];
  if (conflict) {
    reasons.push(`-sources disagree (${sources.join(' vs ')}) - took the strictest`);
  }
  if (alts.length) reasons.push(`+${alts.length} other location${alts.length > 1 ? 's' : ''}`);

  out.push({ json: {
    ...pick,
    reasons: [...new Set(reasons)],
    // Carried so the message can name them, and so dedup can retire the whole
    // group at once -- otherwise the sibling URLs arrive on the next run looking
    // like new roles.
    alsoOpenIn: alts,
    cloneUrls: others.map((v) => v.url).filter(Boolean),
  } });
}

out.sort((a, b) => b.json.score - a.json.score);
return out;
"""

# --------------------------------------------------------------------- dedup
DEDUP = r"""
// Remember what we already pushed so repeat runs stay quiet.
const store = $getWorkflowStaticData('global');
store.seen = store.seen || {};

const now = Date.now();
const TTL = 45 * 24 * 60 * 60 * 1000; // forget after 45 days

for (const k of Object.keys(store.seen)) {
  if (now - store.seen[k] > TTL) delete store.seen[k];
}

const fresh = [];
for (const item of $input.all()) {
  const key = item.json.url;
  if (!key || store.seen[key]) continue;
  fresh.push(item);
}

// Cap one run's notifications so a first run does not flood Telegram.
const batch = fresh.slice(0, 12);

// Mark ONLY what actually goes out. Marking everything examined and then slicing
// records the overflow as "sent", so anything past the cap is never announced at
// all -- the opposite of "it waits for the next run".
for (const item of batch) {
  store.seen[item.json.url] = now;
  // Retire the sibling country clones with it, or the rest of the group arrives
  // one run later as if the role were new.
  for (const u of item.json.cloneUrls || []) store.seen[u] = now;
}

return batch;
"""

# ------------------------------------------------------------------ telegram
TELEGRAM_TEXT = (
    "={{ '*' + $json.score + '/100* — ' + $json.title }}\n"
    "{{ $json.company }} · {{ $json.location }}\n"
    "{{ $json.reasons.join(' · ') }}\n\n"
    "{{ $json.url }}"
)


def node(name, ntype, tv, pos, params, **extra):
    n = {
        "parameters": params,
        "id": name.lower().replace(" ", "-").replace("(", "").replace(")", "")
                  .replace("?", "").replace(",", ""),
        "name": name,
        "type": ntype,
        "typeVersion": tv,
        "position": pos,
    }
    n.update(extra)
    return n


nodes = [
    node("Every 4 hours", "n8n-nodes-base.scheduleTrigger", 1.2, [-620, 300], {
        "rule": {"interval": [{"field": "hours", "hoursInterval": 4}]}
    }),
    node("Run manually", "n8n-nodes-base.manualTrigger", 1, [-620, 460], {}),
    node("Build Source List", "n8n-nodes-base.code", 2, [-400, 300], {
        "mode": "runOnceForAllItems", "jsCode": BUILD_SOURCES.strip()
    }),
    node("Fetch Board", "n8n-nodes-base.httpRequest", 4.2, [-180, 300], {
        # Every source but Getro is a plain GET. Getro's collection search is
        # POST-only, so method/headers/body are driven off the source item.
        # NOTE: this POST path is exercised by radar.mjs in CI; the n8n copy is
        # deactivated (see README), so it has not been run here.
        "method": "={{ $json.method || 'GET' }}",
        "url": "={{ $json.url }}",
        "sendHeaders": "={{ !!$json.headers }}",
        "specifyHeaders": "json",
        "jsonHeaders": "={{ JSON.stringify($json.headers || {}) }}",
        "sendBody": "={{ !!$json.body }}",
        "contentType": "raw",
        "rawContentType": "application/json",
        "body": "={{ $json.body || '' }}",
        "options": {
            "timeout": 20000,
            "response": {"response": {"responseFormat": "text", "neverError": True}},
            "batching": {"batch": {"batchSize": 1, "batchInterval": 1200}},
        },
    }, onError="continueRegularOutput", alwaysOutputData=True),
    node("Normalize Jobs", "n8n-nodes-base.code", 2, [40, 300], {
        "mode": "runOnceForAllItems", "jsCode": NORMALIZE.strip()
    }),
    node("Score vs Profile", "n8n-nodes-base.code", 2, [260, 300], {
        "mode": "runOnceForAllItems", "jsCode": SCORE.strip()
    }),
    node("Collapse Role Clones", "n8n-nodes-base.code", 2, [480, 300], {
        "mode": "runOnceForAllItems", "jsCode": COLLAPSE.strip()
    }),
    node("Drop Already Sent", "n8n-nodes-base.code", 2, [920, 300], {
        "mode": "runOnceForAllItems", "jsCode": DEDUP.strip()
    }),
    node("Relevant enough?", "n8n-nodes-base.if", 2, [700, 300], {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "version": 2, "typeValidation": "loose"},
            "combinator": "and",
            "conditions": [{
                "id": "score-gate",
                "operator": {"type": "number", "operation": "gte"},
                "leftValue": "={{ $json.score }}",
                "rightValue": SCORE_THRESHOLD,
            }],
        },
        "options": {},
    }),
    node("Send to Telegram", "n8n-nodes-base.httpRequest", 4.2, [1140, 220], {
        "method": "POST",
        "url": f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": (
            "={{ JSON.stringify({"
            f" chat_id: '{TELEGRAM_CHAT_ID}',"
            " disable_web_page_preview: false,"
            " text: $json.score + '/100  ' + $json.title"
            " + '\\n' + $json.company + '  ·  ' + $json.location"
            " + '\\n' + $json.reasons.join(' · ')"
            " + (($json.alsoOpenIn || []).length"
            "    ? '\\nalso open in: ' + $json.alsoOpenIn.join(', ') : '')"
            " + '\\n' + $json.url"
            " }) }}"
        ),
        "options": {
            "batching": {"batch": {"batchSize": 1, "batchInterval": 1500}},
        },
    }, onError="continueRegularOutput"),
    node("Below threshold (no-op)", "n8n-nodes-base.noOp", 1, [920, 460], {}),
]

connections = {
    "Every 4 hours": {"main": [[{"node": "Build Source List", "type": "main", "index": 0}]]},
    "Run manually": {"main": [[{"node": "Build Source List", "type": "main", "index": 0}]]},
    "Build Source List": {"main": [[{"node": "Fetch Board", "type": "main", "index": 0}]]},
    "Fetch Board": {"main": [[{"node": "Normalize Jobs", "type": "main", "index": 0}]]},
    "Normalize Jobs": {"main": [[{"node": "Score vs Profile", "type": "main", "index": 0}]]},
    "Score vs Profile": {"main": [[{"node": "Collapse Role Clones", "type": "main", "index": 0}]]},
    "Collapse Role Clones": {"main": [[{"node": "Relevant enough?", "type": "main", "index": 0}]]},
    # The threshold gate precedes dedup, so a below-threshold posting is never
    # recorded as "sent" and can still be announced if a later tuning lifts it.
    "Drop Already Sent": {"main": [[{"node": "Send to Telegram", "type": "main", "index": 0}]]},
    "Relevant enough?": {"main": [
        [{"node": "Drop Already Sent", "type": "main", "index": 0}],
        [{"node": "Below threshold (no-op)", "type": "main", "index": 0}],
    ]},
}

workflow = {
    "id": "jobsradar0000001",
    "name": "Jobs Radar — PM/AI roles → Telegram",
    "active": False,
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
    "versionId": "00000000-0000-4000-8000-000000000001",
}

out = pathlib.Path(__file__).with_name("jobs-radar.workflow.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False))
print(f"wrote {out} ({out.stat().st_size} bytes, {len(nodes)} nodes)")
