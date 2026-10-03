import test from 'node:test';
import assert from 'node:assert/strict';
import {chartCoverage} from '../src/coverage.js';
const item = (text,id,interim='')=>chartCoverage('7',text,interim).items.find(i=>i.id===id);
test('matching is isolated to patients with chart fixtures',()=>{
 assert.equal(chartCoverage('12','Restraints removed').items.length,0);
 assert.equal(item('Restraints removed','restraints').status,'Mentioned');
});
test('interim evidence is provisional, then counted after finalization',()=>{
 assert.equal(item('','restraints','Restraints removed').status,'Hearing…');
 assert.equal(chartCoverage('7','','Restraints removed').mentioned,0);
 assert.equal(chartCoverage('7','Restraints removed').mentioned,1);
});
test('missing, incomplete and negated phrases never get a mention check',()=>{
 assert.equal(item('','restraints').status,'Not yet mentioned');
 assert.equal(item('Restraints are on','restraints').status,'Needs clarification');
 assert.equal(item('Restraints were not removed','restraints').status,'Needs clarification');
 assert.equal(item('Potassium was 3.9','potassium').status,'Needs clarification');
});
test('explicit patient mismatch blocks coverage and does not switch charts',()=>{
 const r=chartCoverage('7','Bed 12. Restraints removed.');
 assert.deepEqual(r.mismatches,['12']);assert.equal(r.mentioned,0);
 assert.equal(chartCoverage('7','Bed 07. Restraints removed').mentioned,1);
});
test('recognizes spoken values and preserves source evidence',()=>{
 const r=chartCoverage('7','PEEP increased from five to eight. Potassium two point nine.');
 assert.equal(r.mentioned,2);assert.match(r.items.find(i=>i.id==='peep').excerpt,/five to eight/);
 assert.equal(item('Potassium 2.9','potassium').status,'Mentioned');
});
