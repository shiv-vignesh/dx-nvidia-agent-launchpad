// Conservative phrase matching for fictional Bed 7 chart fixtures, not clinical inference.
const fixtures = [
  ['line', 'Peripheral line placed', '23:00 · Peripheral line placed', /\b(peripheral|piv|iv line)\b/i, /\b(placed|new|inserted)\b/i],
  ['restraints', 'Restraints removed', '00:00 · Restraints removed', /\brestraints?\b/i, /\b(removed|off|discontinued)\b/i],
  ['peep', 'PEEP increased from 5 to 8', '03:40 · Ventilator PEEP 5 → 8', /\bpeep\b/i, /\b(5|five)\s+(?:to|up to)\s+(8|eight)\b/i],
  ['potassium', 'Potassium 2.9', '02:10 · Potassium 2.9 mmol/L', /\bpotassium\b/i, /\b(2\.9|two point nine)\b/i],
  ['kcl', 'KCl replacement order', '05:00 · KCl 40 mEq IV over 4 hours', /\b(kcl|potassium chloride)\b/i, /\b(40|forty)\b/i],
  ['norepinephrine', 'Norepinephrine increased', '04:50 · Increased to 0.08 mcg/kg/min', /\b(norepinephrine|noradrenaline|levophed)\b/i, /\b(increased|up|titrated up)\b/i],
  ['family', 'Family updated', '02:00 · Family update documented', /\b(family|daughter)\b/i, /\b(updated|called|spoke|informed)\b/i],
];
const bedNames = {seven:'7', nine:'9', eleven:'11', twelve:'12'};
function wrongBeds(text, patient) {
  return [...text.matchAll(/\bbed\s*(?:number\s*)?(0?\d+|seven|nine|eleven|twelve)\b/gi)]
    .map(m => bedNames[m[1].toLowerCase()] || String(Number(m[1])))
    .filter(id => id !== String(Number(patient)));
}
function evidence(text, topic, detail) {
  // Keep clauses short: a detail elsewhere in a long dictation must not count.
  const chunks = text.split(/(?<!\d)[.!?;\n]+|[.!?;\n]+(?!\d)|\b(?:but|however|then)\b/i).filter(Boolean);
  for (const chunk of chunks) {
    const index = chunk.search(topic);
    if (index < 0) continue;
    const excerpt = chunk.slice(Math.max(0,index-65),index+150).trim();
    const uncertain = /\b(no|not|never|without|wasn't|weren't|didn't|don't|unsure|maybe|possibly|uncertain)\b/i.test(excerpt);
    if (!uncertain && detail.test(excerpt)) return {status:'Mentioned', excerpt};
  }
  const chunk = chunks.find(c=>topic.test(c));
  return chunk ? {status:'Needs clarification',excerpt:chunk.trim().slice(0,215)} : null;
}
export function chartCoverage(patient, finalText = '', interim = '') {
  const mismatches = [...new Set(wrongBeds(`${finalText} ${interim}`,patient))];
  const items = String(Number(patient)) === '7' ? fixtures.map(([id,title,source,topic,detail])=>{
    const match = evidence(finalText,topic,detail);
    const draft = !match && evidence(interim,topic,detail);
    return {id,title,source,status:mismatches.length ? 'Check patient' : match?.status || (draft ? 'Hearing…' : 'Not yet mentioned'),excerpt:match?.excerpt || draft?.excerpt || ''};
  }) : [];
  return {items,mismatches,mentioned:items.filter(i=>i.status==='Mentioned').length};
}
