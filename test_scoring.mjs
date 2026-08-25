// Unit-tests the scarce-credential group in "Score vs Profile". No network.
//   node test_scoring.mjs
import fs from 'node:fs';
const wf = JSON.parse(fs.readFileSync(new URL('./jobs-radar.workflow.json', import.meta.url),'utf8'));
const src = wf.nodes.find(n=>n.name==='Score vs Profile').parameters.jsCode;
const score = (items) => new Function('$input','$','$getWorkflowStaticData',src)({all:()=>items});

const post = (o) => ({json:{source:'greenhouse', company:'x', location:'Spain (Remote)', description:'', postedAt:null, ...o}});
const one = (o) => { const r = score([post(o)]); return r.length ? r[0].json : null; };
let fail = 0;
const check = (name, cond, extra='') => { console.log((cond?'PASS  ':'FAIL  ')+name+(cond?'':'  <- '+extra)); if(!cond) fail++; };

// Baseline: a generic senior PM role in Spain, no scarce signal.
const base = one({title:'Senior Product Manager', description:'You will own the roadmap for our B2B SaaS product.'});
console.log(`baseline generic Senior PM in Spain: ${base.score}`);

// 1. A medtech-regulatory JD must clearly outrank the generic one.
const mdr = one({title:'Senior Product Manager',
  description:'You will own regulatory documentation for our medical device software against EU MDR 2017/745, ISO 14971 and IEC 62304, working with clinical validation and FDA submission requirements.'});
check('medtech-regulatory JD outranks generic', mdr.score > base.score + 15, `${mdr.score} vs ${base.score}`);
check('medtech reasons are named', mdr.reasons.some(r=>/medical-device regulation/.test(r)) && mdr.reasons.some(r=>/medtech standards/.test(r)), mdr.reasons.join(' · '));

// 2. It must be able to clear the threshold on that signal even without an AI title.
check('medtech-regulatory role clears the 30 threshold', mdr.score >= 30, String(mdr.score));

// 3. GDPR/HIPAA boilerplate must NOT inflate anything -- it sits in the privacy
//    notice of half the postings in Europe.
const boiler = one({title:'Senior Product Manager',
  description:'You will own the roadmap for our B2B SaaS product. We process your application data in accordance with GDPR. HIPAA compliance training provided.'});
check('GDPR/HIPAA boilerplate does not inflate the score', boiler.score === base.score, `${boiler.score} vs ${base.score}`);

// 4. Health in the TITLE is worth more than health only in the description.
const titleHealth = one({title:'Senior Product Manager, Patient Experience', description:'Own the roadmap.'});
const descHealth  = one({title:'Senior Product Manager', description:'Own the roadmap for patient-facing journeys in our clinic product.'});
check('health in title scores above health in description only',
  titleHealth.score > descHealth.score, `${titleHealth.score} vs ${descHealth.score}`);

// 5. Public-sector / sovereign signal is picked up.
const gov = one({title:'Senior Product Manager', description:'Our platform serves public sector buyers and critical infrastructure operators, deployed as a sovereign, self-hosted system for smart city programmes.'});
check('public sector / sovereign signal scores', gov.score > base.score && gov.reasons.some(r=>/public sector/.test(r)), `${gov.score} — ${gov.reasons.join(' · ')}`);

// 6. The scarce bucket is capped -- it must not saturate the whole score.
const everything = one({title:'Senior Product Manager, Clinical',
  description:'EU MDR 2017/745, IVDR, ISO 14971, IEC 62366, IEC 62304, ISO 13485, 510(k), FDA clearance, medical device, clinical validation, regulatory affairs, patient, clinician, EHR, practice management, digital health, public sector, government, sovereign, smart city, critical infrastructure, EU AI Act, regulated data, auditability, traceability.'});
check('scarce bucket is capped, not saturating', everything.score <= 100 && everything.score - base.score <= 24 + 10, `delta ${everything.score - base.score}`);

// 7. The generic domain bucket must no longer double-count medtech/govtech.
check('medtech no longer also fires the generic domain-match bucket',
  !mdr.reasons.includes('domain match'), mdr.reasons.join(' · '));

// 8. Guard: an unrelated fintech role is unaffected by this change.
const fin = one({title:'Senior Product Manager', description:'Own our fintech payments product for enterprise SaaS customers.'});
check('unrelated fintech role still scores on domain match',
  fin.reasons.includes('domain match') && fin.score > base.score, `${fin.score} — ${fin.reasons.join(' · ')}`);

// 9. The health boost must not promote roles needing a clinical credential.
const clinician = one({title:'Senior Clinical Product Lead',
  description:'You will shape our clinical product. We are looking for a medical degree and meaningful experience practising medicine, with a strong understanding of clinicians day-to-day work.'});
const aiHealthPm = one({title:'AI Senior Product Manager, Patient Engagement',
  description:'Build AI-native patient engagement experiences with LLM-powered conversational interfaces for our clinic and EHR product.'});
check('clinician-credential role is penalised', clinician.reasons.includes('-clinical credential required'), clinician.reasons.join(' · '));
check('a reachable AI health PM role outranks the clinician-only one',
  aiHealthPm.score > clinician.score, `${aiHealthPm.score} vs ${clinician.score}`);

console.log(fail? `\n${fail} FAILURE(S)` : '\nall checks passed');
process.exit(fail?1:0);
