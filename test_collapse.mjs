// Unit-tests the "Collapse Role Clones" node. No network needed.
//   node test_collapse.mjs
import fs from 'node:fs';
const wf = JSON.parse(fs.readFileSync(new URL('./jobs-radar.workflow.json', import.meta.url),'utf8'));
const src = wf.nodes.find(n=>n.name==='Collapse Role Clones').parameters.jsCode;
const collapse = (items) => new Function('$input','$','$getWorkflowStaticData',src)({all:()=>items});

const j = (o) => ({json:o});
let fail = 0;
const check = (name, cond, extra='') => { console.log((cond?'PASS  ':'FAIL  ')+name+(cond?'':'  <- '+extra)); if(!cond) fail++; };

// --- 1. One role published across ten countries by one employer --------------
const clones = ['Spain','Poland','Portugal','Ireland','Greece','Switzerland','Israel','Canada','United Kingdom','United States']
  .map((loc,i)=>j({
    source:'greenhouse', company:'example-corp',
    title:'Principal Product Manager (Platform) - Security',
    location:loc, url:`https://boards.example.com/jobs?id=${1000+i}`,
    score: loc==='Spain'?52:(['Poland','Portugal','Ireland','Greece'].includes(loc)?45:36),
    reasons: loc==='Spain'
      ? ['lead/staff title','platform in title','EU location','Spain-eligible']
      : (['Poland','Portugal','Ireland','Greece'].includes(loc)
          ? ['lead/staff title','platform in title','EU location']
          : ['lead/staff title','platform in title']),
  }));
let out = collapse(clones);
check('10 country clones -> 1 notification', out.length===1, `got ${out.length}`);
check('kept the eligible (home-country) clone', out[0]?.json.location==='Spain', out[0]?.json.location);
check('9 sibling URLs carried so dedup can retire the group', out[0]?.json.cloneUrls.length===9, out[0]?.json.cloneUrls.length);
check('other locations kept for the message', (out[0]?.json.alsoOpenIn||[]).length===9);
check('reasons announce the collapse',
  out[0]?.json.reasons.some(r=>/\+9 other locations/.test(r)), out[0]?.json.reasons.join(' · '));
check('no false source-conflict flag on a single-source group',
  !out[0]?.json.reasons.some(r=>/sources disagree/.test(r)));

// --- 2. Two aggregators, one role, contradicting locations -------------------
const conflicting = [
  j({source:'arbeitnow', company:'example-ai', title:'Senior Technical Product Manager, AI Agents',
     location:'United Kingdom', url:'https://aggregator-a.example/x', score:72,
     reasons:['PM title','AI role','AI in title','agents in title','EU location']}),
  j({source:'himalayas', company:'example-ai', title:'Senior Technical Product Manager, AI Agents',
     location:'Singapore', url:'https://aggregator-b.example/y', score:55,
     reasons:['PM title','AI role','AI in title','agents in title']}),
];
out = collapse(conflicting);
check('conflicting sources -> 1 notification', out.length===1, `got ${out.length}`);
check('took the strict read, not the higher-scoring phantom',
  out[0]?.json.location==='Singapore' && out[0]?.json.score===55,
  `${out[0]?.json.location} @ ${out[0]?.json.score}`);
check('the disagreement is stated in the message',
  out[0]?.json.reasons.some(r=>/sources disagree/.test(r)), out[0]?.json.reasons.join(' · '));

// --- 3. Equal scores: eligibility must break the tie ------------------------
out = collapse([
  j({source:'greenhouse', company:'example-saas', title:'Senior Product Manager - Agents',
     location:'Bulgaria', url:'gh/1', score:41, reasons:['senior title','EU location']}),
  j({source:'greenhouse', company:'example-saas', title:'Senior Product Manager - Agents',
     location:'Poland', url:'gh/2', score:41, reasons:['senior title','EU location']}),
  j({source:'greenhouse', company:'example-saas', title:'Senior Product Manager - Agents',
     location:'Spain', url:'gh/3', score:41, reasons:['senior title','EU location','Spain-eligible']}),
]);
check('score tie -> the reachable clone wins', out[0]?.json.location==='Spain', out[0]?.json.location);

// --- 4. A lone posting is untouched -----------------------------------------
out = collapse([j({source:'ashby', company:'example-health', title:'AI Senior Product Manager',
  location:'Barcelona', url:'ashby/1', score:60, reasons:['senior title','AI in title','Spain-eligible']})]);
check('single posting passes through unchanged',
  out.length===1 && out[0].json.cloneUrls===undefined && out[0].json.url==='ashby/1');

// --- 5. Different roles at one employer stay separate -----------------------
out = collapse([...clones.slice(0,3), ...clones.slice(0,3).map(x=>j({...x.json,
  title:'Principal Product Manager (Detection) - Security', url:x.json.url+'-b'}))]);
check('two different titles at one employer -> 2 notifications', out.length===2, `got ${out.length}`);
check('output stays sorted by score desc',
  out.every((x,i,a)=>i===0||a[i-1].json.score>=x.json.score));

// --- 6. Location baked into the TITLE ---------------------------------------
out = collapse([
  j({source:'ashby', company:'example-health',
     title:'AI Senior Product Manager, Patient Engagement (100% Remote within Spain)',
     location:'Barcelona', url:'ashby/es', score:60,
     reasons:['senior title','AI in title','remote EU/EMEA','Spain-eligible']}),
  j({source:'ashby', company:'example-health',
     title:'AI Senior Product Manager, Patient Engagement (100% Remote within Poland)',
     location:'Warsaw', url:'ashby/pl', score:53,
     reasons:['senior title','AI in title','remote EU/EMEA']}),
]);
check('title-embedded location: variants collapse', out.length===1, `got ${out.length}`);
check('title-embedded location: kept the reachable one', out[0]?.json.location==='Barcelona', out[0]?.json.location);

out = collapse([
  j({source:'ashby', company:'example-health', title:'Senior Clinical Product Lead | 100% Remote within Europe',
     location:'Barcelona', url:'p/1', score:40, reasons:['senior title','EU location']}),
  j({source:'ashby', company:'example-health', title:'Senior Clinical Product Lead | 100% Remote within Poland',
     location:'Warsaw', url:'p/2', score:33, reasons:['senior title','EU location']}),
]);
check('pipe-tail location qualifier collapses too', out.length===1, `got ${out.length}`);

out = collapse([
  j({source:'arbeitnow', company:'example-energy', title:'Senior Product Manager Service Cockpit (m/w/d)',
     location:'Berlin', url:'a/1', score:33, reasons:['senior title','EU location']}),
  j({source:'personio', company:'example-energy', title:'Senior Product Manager Service Cockpit (f/m/x)',
     location:'Berlin', url:'a/2', score:33, reasons:['senior title','EU location']}),
]);
check('gendered job-tag variants collapse', out.length===1, `got ${out.length}`);

// CRITICAL guard: a MEANINGFUL parenthetical must NOT be stripped.
out = collapse([
  j({source:'greenhouse', company:'example-corp', title:'Principal Product Manager (XDR & Exposure Management) - Security Solutions',
     location:'Spain', url:'g/1', score:52, reasons:['lead/staff title','Spain-eligible']}),
  j({source:'greenhouse', company:'example-corp', title:'Principal Product Manager (Strategic Account Interactions) - Security Solutions',
     location:'Spain', url:'g/2', score:52, reasons:['lead/staff title','Spain-eligible']}),
]);
check('meaningful parenthetical is NOT stripped -> stays 2 roles', out.length===2, `got ${out.length}`);

out = collapse([
  j({source:'greenhouse', company:'example-corp', title:'Product Manager - Core AI',
     location:'Utrecht', url:'g/3', score:42, reasons:['PM title','EU location']}),
  j({source:'greenhouse', company:'example-corp', title:'Product Manager - Billing',
     location:'Utrecht', url:'g/4', score:40, reasons:['PM title','EU location']}),
]);
check('meaningful trailing dash segment survives -> stays 2 roles', out.length===2, `got ${out.length}`);

console.log(fail? `\n${fail} FAILURE(S)` : '\nall checks passed');
process.exit(fail?1:0);
