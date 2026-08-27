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
# This was briefly lowered to 30, on the diagnosis that 48 "required AI/domain
# keyword hits on top of a senior title" and so filtered out plain "Senior Product
# Manager" roles. That diagnosis was a symptom: Greenhouse -- 34 boards, ~47% of the
# corpus -- was being fetched without `?content=true`, so those postings had NO
# description and literally could not score keyword hits. The threshold had been
# lowered to accommodate a bug. With descriptions present the distribution shifts up
# by roughly 20 points (on one 4,600-posting sample, >=50 went from 3 postings to 55),
# so 48 is restored to its original meaning.
#
# Then lowered to 40, and that was a change of *instrument* rather than of taste. The
# one application that ever produced an interview scored 39 under the code of the day
# before and exactly 48 after a geography fix -- a gate deciding your one success by a
# single point is measuring noise. MAX_PER_RUN already caps what goes out per run, so
# volume does not need a second guard; what the threshold was really doing was deleting
# the near-misses instead of ranking them last. At 40 they arrive at the bottom of the
# batch, where a human can still see them. Only survivable together with the
# application-history annotation in the score node: on one corpus 78% of everything
# above 48 was a company already applied to or a door already closed.
SCORE_THRESHOLD = 40

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
// miss entirely — an 11-person Munich ConTech firm sat in exactly this bracket.
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
// Pinpoint careers boards. `https://<tenant>.pinpointhq.com/postings.json` returns
// every open posting with the FULL job description, plus separate
// `key_responsibilities` and `skills_knowledge_expertise` blocks — the requirements
// section that the 12000-char cap exists to reach. Richer than most sources here.
// A company's own careers domain serves the identical payload, so the subdomain form
// is used and the tenant is the only thing to know.
//
// Worth adding a platform like this even for a handful of tenants: the posting that
// prompted it arrived by hand from a job link and was invisible to every one of the
// 119 endpoints already in this list, with no aggregator re-listing it either.
const pinpoint = ['improbable', 'unmind', 'quantexa', 'marshmallow'];
// BambooHR careers boards. Two public JSON endpoints, no auth, no bot protection:
// `/careers/list` (all open postings) and `/careers/{id}/detail` (full JD +
// datePosted + compensation). Only the list is fetched — one request per source is
// what Fetch Board can do — so like `workable` and `smartrecruiters` these postings
// arrive with no description and no date. Their title, department and country are
// real, which is enough for a title-and-geography gate to work on.
//
// Listed as [subdomain, display name]: the subdomain is rarely a readable company
// name, and it is the company name that goes into the notification.
// Adding a tenant is just the subdomain from any careers URL. A subdomain that is
// not a BambooHR customer answers 302 text/html, so a typo shows up as a dead board
// in STATUS.md rather than as silence.
const bamboohr = [
  ['finbourne', 'FINBOURNE'],
];
const smartrecruiters = ['DeliveryHero'];
// Getro powers the talent boards of most European VCs: one endpoint per fund
// covers its whole portfolio, which is the small-company bracket that guessing
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
for (const org of pinpoint) {
  out.push({ json: { kind: 'pinpoint', company: org,
    url: `https://${org}.pinpointhq.com/postings.json` } });
  // Second request per tenant, purely for dates. Neither Pinpoint feed is complete:
  // postings.json has structured locations but no date, /en/jobs.rss has pubDate but
  // NO location at all (and only the English postings: on one board, 49 items vs 84).
  // So the JSON supplies the postings and the RSS supplies `postedAt`, joined on the
  // job id -- the RSS <link> is `/jobs/308423` and that number is `job.id` in the
  // JSON. Measured on that board: 49 of 50 distinct job ids covered.
  //
  // This does NOT disturb Normalize's response<->source pairing, which is by array
  // index: two source entries simply get two responses, and the index map stays 1:1.
  out.push({ json: { kind: 'pinpoint-rss', company: org,
    url: `https://${org}.pinpointhq.com/en/jobs.rss` } });
}
for (const [org, label] of bamboohr) {
  out.push({ json: { kind: 'bamboohr', company: label, tenant: org,
    url: `https://${org}.bamboohr.com/careers/list` } });
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

// Pre-pass: Pinpoint dates, keyed `tenant|jobId`. Must run before the main loop
// because the RSS source sits after the JSON source for the same tenant.
const pinpointDates = {};
responses.forEach((resp, i) => {
  const src = (sources[i] && sources[i].json) || {};
  if (src.kind !== 'pinpoint-rss') return;
  const raw = resp.json.data !== undefined ? resp.json.data : resp.json;
  const xml = String(typeof raw === 'string' ? raw : '');
  (xml.match(/<item>[\s\S]*?<\/item>/g) || []).forEach((item) => {
    const link = (item.match(/<link>([\s\S]*?)<\/link>/) || [])[1] || '';
    const date = (item.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [])[1] || '';
    const id = (link.match(/\/jobs\/(\d+)/) || [])[1];
    if (id && date) pinpointDates[`${src.company}|${id}`] = date.trim();
  });
});

responses.forEach((resp, i) => {
  const src = (sources[i] && sources[i].json) || {};
  const kind = src.kind;
  const raw = resp.json.data !== undefined ? resp.json.data : resp.json;

  let parsed = raw;
  if (typeof raw === 'string' && kind !== 'wwr' && kind !== 'personio'
      && kind !== 'pinpoint-rss') {
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
    } else if (kind === 'pinpoint') {
      // Pinpoint wraps its postings in `{ data: [...] }` — the same key the unwrap
      // above uses for n8n's HTTP-response envelope, so `parsed` arrives as the bare
      // array here and `parsed.data` is `undefined`. Written first without this and it
      // silently yielded zero postings. Both shapes are accepted.
      const rows = Array.isArray(parsed) ? parsed : (parsed.data || []);
      rows.forEach((j) => {
        const l = j.location || {};
        // No country field anywhere in the payload — city + province is all there is,
        // and `province` is inconsistent (the country for Paris, a region for a German
        // city, a US state name for New York). Cost: cities outside the score node's
        // EU_WORD list lose the "EU location" bonus, 9 points each.
        //
        // Only "Fully remote" is appended, never Hybrid/Onsite — same rule as `lever`
        // and `workable`, which add 'Remote' and nothing else. Appending the work model
        // unconditionally was tried first and it made Pinpoint the only source able to
        // trigger the hybrid penalty, docking these postings another 10 points for a
        // fact its peers simply never report.
        const remote = j.workplace_type === 'remote'
          || /fully remote/i.test(j.workplace_type_text || '') ? 'Remote' : '';
        const parts = [...new Set([l.city, l.province, remote]
          .filter(Boolean).map(String))];
        push({
          title: j.title,
          url: j.url,
          location: parts.join(', '),
          // The three blocks are one JD split across three fields. Concatenated
          // because the requirements — language demands, knockout conditions —
          // live in the latter two, not in `description`.
          description: [j.description, j.key_responsibilities,
            j.skills_knowledge_expertise].filter(Boolean).join(' '),
          // Localized duplicates share one `job.id` with their English sibling, so
          // the join lands on the underlying job, which is what the posting age is a
          // property of. Postings with no English sibling stay undated and simply
          // escape the age penalty.
          postedAt: pinpointDates[`${src.company}|${j.job && j.job.id}`] || null,
        });
      });
    } else if (kind === 'pinpoint-rss') {
      // Date source only — consumed by the pre-pass above, pushes nothing.
      return;
    } else if (kind === 'bamboohr') {
      // The list response carries no description and no date; `atsLocation` is the
      // hiring country (BambooHR's own `location` object is empty on these boards).
      (parsed.result || []).forEach((j) => {
        // `province` is often just the country repeated (one board rendered Belgrade
        // as "Belgrade, Serbia, Serbia"), so the parts are deduped, not concatenated.
        const a = j.atsLocation || {};
        const parts = [...new Set([a.city, a.state || a.province, a.country]
          .filter(Boolean).map(String))];
        push({
          title: j.jobOpeningName,
          url: `https://${src.tenant}.bamboohr.com/careers/${j.id}`,
          location: parts.join(', '),
          description: '',
          postedAt: null,
        });
      });
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
// ---------------------------------------------------------- application history
// REPLACE THESE TWO LISTS WITH YOUR OWN, or leave them as-is and nothing is tagged.
//
// A radar that does not know what you have already spent will keep handing it back:
// on one measured corpus, 65 of the 83 postings above threshold (78%) were companies
// already applied to or doors already closed. Keeping the list only in the manual
// triage script means it drifts from your application log every time you apply.
//
// This is deliberately an ANNOTATION, not a filter, and that distinction is the whole
// lesson: a hard drop once hid the best posting of the week, because a company-level
// filter cannot tell that a NEW role at a company you already applied to is a level up.
// So `history` rides along on every posting and the *notification* step decides what to
// do with it. A labelled role low in the list costs one glance; a wrong drop is
// invisible, which is the worse failure.
const DONE_COMPANIES = /^(example-company|another-company)$/i;
// Closed doors: the narrow set where the evidence is in and another application buys no
// information -- e.g. three applications to one company, three different domains, zero
// visa friction, three byte-identical template rejections. These are the only ones the
// notification step suppresses. Leave the placeholder if you have none yet.
const CLOSED_DOORS = /^(a-company-you-have-stopped-applying-to)$/i;

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


// How the team works, scored as a first-class signal -- and for this profile it was the
// highest-value single addition to the scorer. The reasoning generalises: a keyword
// scorer reads TITLE and LOCATION well and reads working-method requirements barely at
// all, so a JD asking for precisely your rarest habit can score below a JD asking for
// nothing in particular. On the corpus this was built against, the one posting that
// converted into an interview had every one of these signals and scored none of them.
//
// Retune the list to whatever your own rare habit actually is. Measured effect here:
// that posting went 48 -> 70, and corpus-wide >=48 went 83 -> 100.
const WORKING_METHOD = [
  [/\b(claude code|claude|cursor|copilot|windsurf|lovable|replit|bolt\.new|\bv0\b)\b/i, 10, 'names an AI tool she uses daily'],
  [/\bai[\s-]native\b|\bai[\s-]first\b/i, 8, 'AI-native team'],
  [/(use|using|used|usage of|adopt\w*|leverag\w*|habitual\w*|fluent\w*)[\s\w]{0,24}\bai (tool|tooling|assistant)/i, 8, 'requires hands-on AI tooling'],
  [/spec[\s-]driven|openspec|prototype it yourself|build (a |your own )?prototype|vibe cod/i, 7, 'spec-driven / self-prototyping'],
  [/shipped something|built something|show us,? not tell|something you can demo/i, 7, 'show-not-tell builder bar'],
  [/agentic workflow|agentic product|agent pipeline/i, 6, 'agentic practice'],
];
// Capped like the other buckets: five of these firing is a strong signal, not five
// times a strong signal.
const WM_CAP = 22;

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

// Location vocabulary. Both lists used to be country-level while most boards write a
// bare city, and the cost is easy to under-estimate: on one 9,720-posting corpus,
// **4,197 (43%) had a location matching NEITHER pattern**. The damage was one-sided.
// ~1,700 of those were US offices escaping the -32 US-only penalty completely --
// "San Francisco" alone appeared 1,082 times, "New York"/"New York City" 380 more --
// because the state-code pattern needs ", CA" and these postings just say the city.
// Meanwhile Munich (93 incl. "München"), Stockholm (146), Milan (19), Frankfurt and
// Belgrade roles silently lost the +9 EU bonus even though EU_WORD listed their
// countries. If you re-target this radar, re-run that census on YOUR corpus.
//
// The city list is the same one COLLAPSE's LOC_TAG carries, which is where it was
// already written down once; duplicated rather than shared because these are two
// separate n8n Code nodes.
const US_STATE = /,\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b/;
const US_WORD = /\b(u\.?s\.?a?\.?|united states)\b/i;
// Bare US city names. Checked against the corpus for collisions with the EU list
// before adding: on that corpus, none of the 119 distinct US_STATE-matching
// locations was European,
// and usOnly requires !EU_WORD anyway, so an EU city that shares a US name (Berlin
// CT, Paris TX) is still protected by EU_WORD winning first.
const US_CITY = /\b(san francisco|new york|nyc\b|palo alto|mountain view|san jose|san mateo|sunnyvale|santa clara|seattle|bellevue|austin|chicago|boston|cambridge, ma|denver|boulder|atlanta|dallas|houston|miami|philadelphia|phoenix|portland, or|san diego|los angeles|\bla\b(?! ?paz)|minneapolis|detroit|pittsburgh|nashville|charlotte|raleigh|durham|salt lake city|las vegas|kansas city|st\.? louis|columbus, oh|arlington|bethesda|reston|mclean|redmond|sacramento)\b/i;
const EU_WORD = /\b(emea|europe|european|spain|madrid|barcelona|valencia|m[aá]laga|granada|sevilla|bilbao|germany|berlin|munich|m[uü]nchen|hamburg|cologne|k[oö]ln|frankfurt|stuttgart|d[uü]sseldorf|mannheim|karlsruhe|leipzig|dresden|g[oö]ttingen|heidelberg|netherlands|amsterdam|utrecht|rotterdam|eindhoven|the hague|den haag|portugal|lisbon|lisboa|porto|ireland|dublin|cork|uk|united kingdom|england|scotland|wales|london|manchester|edinburgh|glasgow|bristol|cambridge, uk|oxford|leeds|birmingham|poland|warsaw|warszawa|krak[oó]w|krakow|wroc[lł]aw|gda[nń]sk|pozna[nń]|france|paris|lyon|marseille|toulouse|bordeaux|nantes|lille|italy|italia|milan|milano|rome|roma|turin|torino|bologna|naples|napoli|sweden|stockholm|gothenburg|g[oö]teborg|malm[oö]|denmark|copenhagen|k[oø]benhavn|aarhus|austria|vienna|wien|graz|switzerland|zurich|z[uü]rich|geneva|gen[eè]ve|basel|lausanne|belgium|brussels|bruxelles|antwerp|ghent|gent|leuven|czech|czechia|prague|praha|brno|romania|bucharest|bucure[sș]ti|cluj|timi[sș]oara|bulgaria|sofia|plovdiv|greece|athens|thessaloniki|hungary|budapest|estonia|tallinn|tartu|latvia|riga|lithuania|vilnius|kaunas|croatia|zagreb|split|slovakia|bratislava|slovenia|ljubljana|finland|helsinki|espoo|tampere|norway|oslo|bergen|trondheim|luxembourg|malta|cyprus|nicosia|iceland|reykjav[ií]k|serbia|belgrade|beograd|novi sad)\b/i;
// Only the location field may claim worldwide eligibility. Tested against
// location+description at first, which meant a company blurb was enough: one
// company's "enabling sustainable growth for businesses worldwide" handed its
// office-bound roles the full +16, and a Prague office role the same. On a
// 33-posting sample, 2 of the 4 "worldwide" bonuses awarded were this -- one of
// them above the threshold. "worldwide" and "global" are marketing words in a description; they are
// eligibility statements only in a location field.
const ANY_WORD = /\b(worldwide|anywhere|global|any location)\b/i;
// The narrow exception: phrases that state location-free hiring outright, which a
// marketing blurb does not produce. These may be read from the description.
const ANY_DESC = /anywhere in the world|work from anywhere|from anywhere in|fully distributed|location.independent|no location requirement/i;
// Same principle for the EU-remote bonus, and it needed two attempts. The first
// version accepted `based in Europe` anywhere in the description, which promoted an
// India-based role to 54 with a "remote EU/EMEA" bonus off the sentence
// "...teams based in Europe...". A description mentions Europe descriptively
// far more often than it grants eligibility, so only phrasings that are *about this
// role's eligibility* count. Everything softer than these falls through to the plain
// `remote` +7, which is the honest read of "we could not tell from the text".
const EU_DESC = new RegExp([
  'remote\\s*(-|,)?\\s*(with)?in\\s+(europe|the eu\\b|emea)',
  'remote\\s+from\\s+(europe|the eu\\b|anywhere in europe)',
  'anywhere in europe',
  '(candidates?|applicants?|you)\\s+(must|need to|should)\\s+be\\s+(based|located|resident)\\s+in\\s+(europe|the eu\\b)',
  'eligible to work in the eu\\b',
  'work(ing)? authoriz(ation|ed) in the eu\\b',
].join('|'), 'i');

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

  const head = desc.slice(0, 400);
  const geo = `${loc} ${head}`;
  const isRemote = /\bremote\b|\bdistributed\b/i.test(geo);
  // The location field is the only place a *place* is asserted; the description may
  // only contribute an explicit eligibility phrase (ANY_DESC / EU_DESC). Reading
  // bare place words out of the description is what handed office-bound roles a
  // worldwide bonus -- see the ANY_WORD comment above.
  const anyWhere = ANY_WORD.test(loc) || ANY_DESC.test(head);
  const euRemote = (EU_WORD.test(loc) && isRemote) || EU_DESC.test(head);
  const usOnly = (US_STATE.test(loc) || US_WORD.test(loc) || US_CITY.test(loc))
    && !EU_WORD.test(loc) && !ANY_WORD.test(loc);
  const usHint = AGGREGATOR && /remote\s*[-–,]?\s*(usa|us\b)|united states|\bus only\b|us.based/i.test(desc);

  if (anyWhere) {
    const pts = AGGREGATOR ? 6 : 16;
    score += pts;
    reasons.push(AGGREGATOR ? 'worldwide (unverified)' : 'worldwide');
  } else if (euRemote) { score += 16; reasons.push('remote EU/EMEA'); }
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

  // Working-method bonus, gated on an AFFIRMATIVE eligibility reason rather than merely
  // the absence of a US signal. Measured ungated first, and it did exactly what a
  // content bonus must never do: rescued postings that had already failed the location
  // gate, promoting an India-based role 38 -> 60 and a Remote-U.S. one 38 -> 48 on
  // working-method words alone. Requiring a positive geography reason cut the
  // newly-promoted set from 24 to 17, all of them actually eligible.
  if (reasons.some((r) => /Spain-eligible|remote EU\/EMEA|EU location|worldwide/.test(r))) {
    let wm = 0; const wmReasons = [];
    for (const [re, pts, why] of WORKING_METHOD) {
      if (re.test(desc) || re.test(title)) { wm += pts; wmReasons.push(why); }
    }
    if (wm > 0) { score += Math.min(wm, WM_CAP); reasons.push(...wmReasons); }
  }

  score = Math.max(0, Math.min(100, Math.round(score)));
  // Kept out of `reasons` on purpose: COLLAPSE's eligibility() parses that array to
  // pick which country clone is actually takeable, and a history tag in there would be
  // one more string for it to misread.
  const co = (j.company || '').trim();
  const history = CLOSED_DOORS.test(co) ? 'closed'
    : DONE_COMPANIES.test(co) ? 'applied' : null;
  out.push({ json: { ...j, score, reasons: [...new Set(reasons)], history } });
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

  // Third-party aggregators re-list other people's postings and mislabel where the
  // job is. A company's own ATS is the employer describing its own vacancy.
  const AGGREGATORS = new Set([
    'remoteok', 'himalayas', 'wwr', 'remotive', 'jobicy', 'workingnomads',
    'arbeitnow', 'themuse',
  ]);
  const firstParty = variants.filter((v) => !AGGREGATORS.has(v.source));
  const aggSources = [...new Set(
    variants.filter((v) => AGGREGATORS.has(v.source)).map((v) => v.source),
  )];

  // When the SAME role arrives from DIFFERENT aggregators with different locations,
  // one of them is lying -- and it is reliably the optimistic one. A role that one
  // aggregator listed as "United Kingdom" and another as "Singapore" was
  // Singapore-only in the employer's own posting, and the inflated copy scored 17
  // points higher, which is enough to top a batch. Same failure as the
  // WeWorkRemotely "Anywhere in the World" mislabels documented in the README.
  // So on conflict, take the LEAST eligible read and say so, rather than letting a
  // phantom lead the run.
  //
  // The trap: that rule must NOT fire on an employer legitimately posting one role
  // in several countries on its own board. A req cloned across seven countries --
  // one of them home-country-only -- picks up an aggregator mirror of a single
  // clone, the source count goes to two, the pessimistic branch selects the
  // least-eligible clone, and a perfectly reachable high scorer drops below the
  // threshold and disappears from the run. So:
  //   - if the employer's own ATS is in the group, that IS the truth: rank among
  //     first-party variants and let the aggregator mirrors ride along as clones;
  //   - only an aggregator-only group, with two aggregators actually disagreeing,
  //     is a phantom and gets the strictest read.
  const trusted = firstParty.length ? firstParty : variants;
  const conflict = !firstParty.length
    && aggSources.length > 1
    && new Set(variants.map(eligibility)).size > 1;

  const ranked = [...trusted].sort((a, b) => (conflict
    ? eligibility(a) - eligibility(b) || a.score - b.score
    : eligibility(b) - eligibility(a) || b.score - a.score));

  const pick = ranked[0];
  // Everything not picked still has to be retired -- including the aggregator
  // mirrors held out of the ranking above, or they arrive next run looking new.
  const others = variants.filter((v) => v !== pick);
  // "also open in" should name real sibling locations, not an aggregator's
  // rendering of one already listed, so it is built from the trusted set only.
  const alts = [...new Set(
    ranked.slice(1).map((v) => v.location).filter(Boolean),
  )];

  const reasons = [...(pick.reasons || [])];
  if (conflict) {
    reasons.push(`-aggregators disagree (${aggSources.join(' vs ')}) - took the strictest`);
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
  // The two places application history and geography are allowed to REMOVE something.
  // `closed` is the narrow set where another application buys no information.
  // `applied` is NOT dropped -- it is annotated in the message instead, because a
  // company you already applied to can still post the best role of the week.
  if (item.json.history === 'closed') continue;
  // A posting the scorer already identified as US-only is not takeable from the EU, and
  // hunt.mjs always filtered these out of its shortlist. They only stayed visible here
  // because a higher threshold happened to exclude most of them; at 40 an explicitly
  // US-only posting reached the batch even after its -32.
  if ((item.json.reasons || []).some((r) => /^-US-only$|^-likely US-only$/.test(r))) continue;
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
    "{{ $json.history === 'applied' ? '⚠ already applied to this company — check your log before spending another\\n' : '' }}"
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
