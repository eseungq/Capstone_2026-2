const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const js = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  module._compile(js, filename);
};
const core = require(path.join(__dirname, '../src/api/backendV4/recheckSummaryCoreV4.ts'));
const { createRecheckSummaryServiceV4 } = require(
  path.join(__dirname, '../src/api/backendV4/recheckSummaryServiceV4.ts'));

const iso = '2026-11-18T21:00:00+09:00';
const stratum = {
  stratum: 'NEAR', autoPassCount:10, decidedCount:8, undecidedCount:2,
  sampledCount:5, completedCount:4, pendingCount:1, completionRate:0.8,
  passCount:3, failCount:1, failRateAmongCompleted:0.25,
};
const emptyStratum = stratumName => ({
  stratum:stratumName, autoPassCount:0, decidedCount:0, undecidedCount:0,
  sampledCount:0, completedCount:0, pendingCount:0, completionRate:null,
  passCount:0, failCount:0, failRateAmongCompleted:null,
});
const compare = {
  nearRate:0.5,midRate:0.3,lowRate:0.1,computable:true,
  sampledCount:2,unverifiedCount:1,passCount:1,failCount:0,
  partial:true,estimatedDefectRateInAutoPass:0,
};
const rule = {
  ruleVersion:'v1-b40-80-p100-30-10',trialName:'공동시험 1차',
  partCode:'DOOR',policyVersion:'door-e02-demo-0092',
  modelVersion:'door-e02',calibratorVersion:'cal-e02',
  nearRatio:0.8,midRatio:0.4,nearRate:1,midRate:0.3,lowRate:0.1,
  autoPassCount:10,decidedCount:8,undecidedCount:2,
  sampledCount:5,pendingCount:1,passCount:3,failCount:1,
  completionRate:0.8,partial:true,
  strata:[stratum,emptyStratum('MID'),emptyStratum('LOW')],
  estimatedDefectRateInAutoPass:0.25,compare,
};
const wait = {count:4,pendingCount:1,averageMs:45000,medianMs:32000};
const dwell = {count:4,averageMs:17000,medianMs:12000,averageOpenCount:1.25};
const summary = {
  partCode:null,from:iso,to:'2026-11-19T21:00:00+09:00',
  autoPassCount:10,decidedCount:8,undecidedCount:2,undecidedWithoutRuleCount:0,
  rules:[rule],waits:{review:wait,recheck:wait},
  dwell:{review:dwell,recheck:dwell},
};

test('summary requests explicitly bounded time range and 50·30·10 virtual comparison', () => {
  const url = core.makeRecheckSummaryPathV4({
    partCode:'DOOR',from:iso,to:'2026-11-19T21:00:00+09:00',
    compareNearRate:0.5,compareMidRate:0.3,compareLowRate:0.1,
  });
  assert.match(url,/^\/admin\/rechecks\/summary\?/);
  const u = new URL('http://test.local' + url);
  assert.equal(u.searchParams.get('partCode'),'DOOR');
  assert.equal(u.searchParams.get('compareNearRate'),'0.5');
  assert.equal(u.searchParams.get('compareMidRate'),'0.3');
  assert.equal(u.searchParams.get('compareLowRate'),'0.1');
  assert.equal(u.searchParams.get('from'),iso);
});
test('summary rejects partial compare rates, invalid part code and inverted period', () => {
  assert.throws(()=>core.makeRecheckSummaryPathV4({compareNearRate:0.5}));
  assert.throws(()=>core.makeRecheckSummaryPathV4({partCode:'INVALID'}));
  assert.throws(()=>core.makeRecheckSummaryPathV4({
    from:'2026-11-19T21:00:00+09:00',to:iso,
  }));
});
test('summary preserves original rule-policy-model-calibrator combination', () => {
  const value=core.decodeRecheckSummaryV4(summary);
  assert.equal(value.rules[0].partCode,'DOOR');
  assert.equal(value.rules[0].policyVersion,'door-e02-demo-0092');
  assert.equal(value.rules[0].modelVersion,'door-e02');
  assert.equal(value.rules[0].calibratorVersion,'cal-e02');
  assert.equal(value.rules[0].estimatedDefectRateInAutoPass,0.25);
});
test('different policy versions remain separate summary items without rate aggregation', () => {
  const other={...rule,policyVersion:'door-e02-p2',estimatedDefectRateInAutoPass:0.1};
  const value=core.decodeRecheckSummaryV4({
    ...summary,autoPassCount:20,decidedCount:16,undecidedCount:4,
    rules:[rule,other],
  });
  assert.equal(value.rules.length,2);
  assert.notEqual(value.rules[0].policyVersion,value.rules[1].policyVersion);
  assert.deepEqual(value.rules.map(r=>r.estimatedDefectRateInAutoPass),[0.25,0.1]);
});
test('completion copy shows 4/5 (80%) and zero samples as em dash', () => {
  assert.equal(core.formatRecheckCompletionV4(4,5,0.8),'완료 4/5건 (80.0%)');
  assert.equal(core.formatRecheckCompletionV4(0,0,null),'완료 0/0건 (—)');
});
test('AUTO_PASS estimate has its own label and null never becomes 0%', () => {
  assert.equal(core.formatRecheckRateV4(0.021),'2.10%');
  assert.equal(core.formatRecheckRateV4(0),'0.00%');
  assert.equal(core.formatRecheckRateV4(null),'완료된 재확인이 없는 구간이 있어 추정하지 않음');
});
test('no completed sample keeps null estimate, separate from partial', () => {
  const pending={...rule,
    sampledCount:2,pendingCount:2,passCount:0,failCount:0,
    completionRate:0,partial:true,estimatedDefectRateInAutoPass:null,
    strata:[{...stratum,sampledCount:2,completedCount:0,pendingCount:2,
      passCount:0,failCount:0,completionRate:0,failRateAmongCompleted:null},
      emptyStratum('MID'),emptyStratum('LOW')],
  };
  const decoded=core.decodeRecheckSummaryV4({...summary,rules:[pending]});
  assert.equal(decoded.rules[0].estimatedDefectRateInAutoPass,null);
  assert.equal(decoded.rules[0].partial,true);
  assert.equal(decoded.rules[0].strata[0].failRateAmongCompleted,null);
});
test('virtual comparison reports own rates, sampled, unknown and partial', () => {
  const actual=core.decodeRecheckSummaryV4(summary).rules[0];
  assert.equal(core.formatRecheckCompareTitleV4(actual.compare),'가상 비교 (50·30·10%)');
  assert.equal(actual.compare.partial,true);
  assert.equal(actual.compare.unverifiedCount,1);
  assert.equal(actual.passCount,3); // actual, not hypothetical PASS=1
  assert.equal(actual.compare.passCount,1);
});
test('noncomputable comparison permits null metrics and is not mistaken for a real estimate', () => {
  const uncomputable={...compare,computable:false,sampledCount:null,
    unverifiedCount:null,passCount:null,failCount:null,partial:null,
    estimatedDefectRateInAutoPass:null};
  const v=core.decodeRecheckSummaryV4({...summary,rules:[{...rule,compare:uncomputable}]});
  assert.equal(v.rules[0].compare.computable,false);
  assert.throws(()=>core.decodeRecheckSummaryV4({
    ...summary,rules:[{...rule,compare:{...uncomputable,passCount:3}}],
  }));
});
test('wrong or absent completionRate is rejected, not made up on the frontend', () => {
  assert.throws(()=>core.decodeRecheckSummaryV4({
    ...summary,rules:[{...rule,strata:[{...stratum,completionRate:undefined},emptyStratum('MID'),emptyStratum('LOW')]}],
  }));
  assert.throws(()=>core.decodeRecheckSummaryV4({
    ...summary,rules:[{...rule,completionRate:undefined}],
  }));
});
test('inconsistent sampled/completed/pending counts are rejected', () => {
  assert.throws(()=>core.decodeRecheckSummaryV4({
    ...summary,rules:[{...rule,strata:[{...stratum,pendingCount:3},emptyStratum('MID'),emptyStratum('LOW')]}],
  }));
});
test('READ-ONLY summary service calls only GET and decodes response (already unwrapped data)', async () => {
  const calls=[];
  const service=createRecheckSummaryServiceV4({
    authorizedRequest: async (p,options) => {calls.push({path:p,options});return summary;},
  });
  const value=await service.get({
    from:iso,to:'2026-11-19T21:00:00+09:00',
    compareNearRate:0.5,compareMidRate:0.3,compareLowRate:0.1,
  });
  assert.equal(calls.length,1);
  assert.equal(calls[0].options.method,'GET');
  assert.equal(value.rules[0].strata[0].completedCount,4);
});
