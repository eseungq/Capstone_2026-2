/** Contract v4 6.9 AUTO_FAIL ADMIN policy. Unit tests only; no real server calls. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
Module._extensions['.ts']=(module,filename)=>{
  module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,
    compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,filename);
};
const root=path.join(__dirname,'../src/api/backendV4');
const {decodeAdminPolicyV4,createAdminPolicyServiceV4}=require(path.join(root,'adminPolicyServiceV4.ts'));
const {parseAutoFailPercentV4,makeAutoFailThresholdEditV4,
  ensureAutoFailToggleV4,autoFailRangeLabelV4}=require(path.join(root,'autoFailPolicyCoreV4.ts'));
const {createAutoFailPolicyServiceV4}=require(path.join(root,'autoFailPolicyServiceV4.ts'));
const base={
  policyId:'9a77d895-74cd-4b42-a7c9-1baaa91b3025', policyVersion:'example-cowl-e08',
  partCode:'COWL_COVER', modelVersion:'m',calibratorVersion:'cal',
  passThreshold:0.0163,validatedMin:0.01,validatedMax:0.025,
  autoFailEnabled:false,failThreshold:null,failValidatedMin:null,failValidatedMax:null,
  ready:true,active:true,metrics:{sampleCount:148,autoFail:{sampleCount:148,note:'AI 검증'}},
  basedOnPolicyId:null,createdAt:null,activatedAt:null,
};
const withFail={...base,failThreshold:0.9966,failValidatedMin:0.98,failValidatedMax:1};
const registered={
 ...withFail,policyId:'a4a0e6bc-e52f-4a4f-8f17-df9b48d2df2a',
 policyVersion:'example-cowl-e08-f1',basedOnPolicyId:base.policyId,
 active:false,
};
const on={...registered,policyId:'a4a0e6bc-e52f-4a4f-8f17-df9b48d2df2b',
 policyVersion:'example-cowl-e08-a1',basedOnPolicyId:registered.policyId,autoFailEnabled:true};
function transport({role='ADMIN',signedIn=true,answer=null}={}){
 const calls=[];const value={
   async restore(){return {signedIn,role,loginId:'admin'};},
   async authorizedRequest(route,opts){calls.push({route,opts});
     if(!answer)throw new Error('unexpected POST'); return answer;
   },
 };
 return {value,calls};
}
test('missing backend #52 fields are unknown, not falsely marked AUTO_FAIL enabled',()=>{
 const old={...base};delete old.autoFailEnabled;delete old.failThreshold;
 delete old.failValidatedMin;delete old.failValidatedMax;
 const p=decodeAdminPolicyV4(old);
 assert.equal(p.autoFailEnabled,null);
 assert.equal(p.failThreshold,null);
 assert.throws(()=>makeAutoFailThresholdEditV4(p,'99.66','98','100'),/서버/);
});
test('policy defaults to disabled, supports explicit false and nullable fail thresholds',()=>{
 const p=decodeAdminPolicyV4(base);
 assert.equal(p.autoFailEnabled,false);
 assert.equal(p.failValidatedMax,null);
});
test('policy rejects enabled without all fail threshold fields',()=>{
 assert.throws(()=>decodeAdminPolicyV4({...base,autoFailEnabled:true}),/필요/);
 assert.throws(()=>decodeAdminPolicyV4({...base,failThreshold:0.9}),/함께/);
});
test('policy rejects failThreshold at or below passThreshold and invalid min/max',()=>{
 assert.throws(()=>decodeAdminPolicyV4({...withFail,failThreshold:0.0163}),/관계/);
 assert.throws(()=>decodeAdminPolicyV4({...withFail,failValidatedMin:1,failValidatedMax:0.99}),/관계/);
});
test('percent input supports four percent decimals / six fractional decimals',()=>{
 assert.equal(parseAutoFailPercentV4('99.6600'),0.9966);
 assert.equal(parseAutoFailPercentV4('1.6301'),0.016301);
 assert.equal(parseAutoFailPercentV4('100'),1);
 assert.equal(parseAutoFailPercentV4('0'),0);
});
test('invalid percent formats and out-of-range values blocked',()=>{
 for(const s of ['-1','101','1.12345','1e1','abc','99,66'])
   assert.throws(()=>parseAutoFailPercentV4(s),/백분율/);
});
test('verified threshold range is inclusive and above passThreshold',()=>{
 assert.deepEqual(makeAutoFailThresholdEditV4(base,'99.66','98','100'),{
   failThreshold:0.9966,failValidatedMin:0.98,failValidatedMax:1,
 });
 assert.throws(()=>makeAutoFailThresholdEditV4(base,'1.63','1','2'),/높아야/);
 assert.throws(()=>makeAutoFailThresholdEditV4(base,'99.66','99.7','100'),/범위/);
 assert.throws(()=>makeAutoFailThresholdEditV4(base,'99.66','100','98'),/최솟값/);
});
test('inactive or unready or foreign policy cannot set fail threshold',()=>{
 for(const changes of [{active:false},{ready:false},{partCode:'UNKNOWN'}])
   assert.throws(()=>makeAutoFailThresholdEditV4({...base,...changes},'99.66','98','100'),/준비된 활성/);
});
test('toggle on requires registered threshold, rejects no-op',()=>{
 assert.throws(()=>ensureAutoFailToggleV4(base,true),/등록/);
 assert.throws(()=>ensureAutoFailToggleV4(base,false),/해당/);
 assert.doesNotThrow(()=>ensureAutoFailToggleV4(withFail,true));
});
test('toggle off permitted and does not clear threshold',()=>{
 const current={...withFail,autoFailEnabled:true};
 assert.doesNotThrow(()=>ensureAutoFailToggleV4(current,false));
});
test('threshold API POST exactly one new inactive version with no activation',async()=>{
 const {value,calls}=transport({answer:registered});
 const policy=await createAutoFailPolicyServiceV4(value).saveThreshold(base,'99.66','98','100');
 assert.equal(policy.active,false);
 assert.equal(calls.length,1);
 assert.deepEqual(calls[0],{
   route:`/admin/policies/${base.policyId}/fail-threshold`,
   opts:{method:'POST',body:{failThreshold:0.9966,failValidatedMin:0.98,failValidatedMax:1}},
 });
});
test('toggle API POST sends enabled true, expects new inactive policy',async()=>{
 const source={...withFail,policyId:'a4a0e6bc-e52f-4a4f-8f17-df9b48d2df2a'};
 const {value,calls}=transport({answer:on});
 const r=await createAutoFailPolicyServiceV4(value).saveToggle(source,true);
 assert.equal(r.active,false);assert.equal(r.autoFailEnabled,true);
 assert.deepEqual(calls[0],{
   route:`/admin/policies/${source.policyId}/auto-fail`,
   opts:{method:'POST',body:{enabled:true}},
 });
});
test('WORKER role prevents both policy POST actions',async()=>{
 const {value,calls}=transport({role:'WORKER',answer:registered});
 const svc=createAutoFailPolicyServiceV4(value);
 await assert.rejects(svc.saveThreshold(base,'99.66','98','100'),/ADMIN/);
 await assert.rejects(svc.saveToggle(withFail,true),/ADMIN/);
 assert.equal(calls.length,0);
});
test('wrong saved parent, active reply, changed toggle all rejected',async()=>{
 const t1=transport({answer:{...registered,basedOnPolicyId:'wrong'}});
 await assert.rejects(createAutoFailPolicyServiceV4(t1.value).saveThreshold(base,'99.66','98','100'),/비활성 버전/);
 const t2=transport({answer:{...registered,active:true}});
 await assert.rejects(createAutoFailPolicyServiceV4(t2.value).saveThreshold(base,'99.66','98','100'),/비활성 버전/);
 const source={...withFail,policyId:'a4a0e6bc-e52f-4a4f-8f17-df9b48d2df2a'};
 const t3=transport({answer:{...on,autoFailEnabled:false}});
 await assert.rejects(createAutoFailPolicyServiceV4(t3.value).saveToggle(source,true),/응답|새로운/);
});
test('existing admin policy GET preserves pre-V13 list and no AUTO_FAIL POST',async()=>{
 const calls=[];const svc=createAdminPolicyServiceV4({
   async restore(){return {signedIn:true,role:'ADMIN',loginId:'admin'};},
   async authorizedRequest(route,opts){calls.push({route,opts});return [base];}
 });
 const list=await svc.list();
 assert.equal(list.length,1);
 assert.equal(list[0].autoFailEnabled,false);
 assert.equal(calls[0].opts.method,'GET');
});

test('fixed 99.66% threshold and inactive version can enable AUTO_FAIL without metrics evidence',async()=>{
 const fixed={...registered,failValidatedMin:0.9966,failValidatedMax:0.9966,metrics:{sampleCount:148}};
 assert.deepEqual(makeAutoFailThresholdEditV4(base,'99.66','99.66','99.66'),{failThreshold:0.9966,failValidatedMin:0.9966,failValidatedMax:0.9966});
 const source=decodeAdminPolicyV4(fixed);
 assert.doesNotThrow(()=>ensureAutoFailToggleV4(source,true));
 const response={...fixed,policyId:on.policyId,policyVersion:on.policyVersion,basedOnPolicyId:fixed.policyId,autoFailEnabled:true};
 const {value,calls}=transport({answer:response});
 const saved=await createAutoFailPolicyServiceV4(value).saveToggle(source,true);
 assert.equal(saved.active,false);assert.equal(saved.autoFailEnabled,true);
 assert.equal(calls.length,1);assert.deepEqual(calls[0],{route:`/admin/policies/${fixed.policyId}/auto-fail`,opts:{method:'POST',body:{enabled:true}}});
});

test('equal AUTO_FAIL bounds are fixed trial values, not a validated range',()=>{
 assert.equal(autoFailRangeLabelV4(0.9966,0.9966),'검증 범위 없음(고정값)');
 assert.equal(autoFailRangeLabelV4(null,null),'미제공');
 assert.equal(autoFailRangeLabelV4(0.98,1),'98.0000% ~ 100.0000%');
});

for(const partCode of ['DOOR','FRAME']){
 test(partCode+' supports fail-threshold and toggle with same-part response validation',async()=>{
   const b={...base,partCode},f={...withFail,partCode},r={...registered,partCode};
   assert.equal(makeAutoFailThresholdEditV4(b,'99.66','98','100').failThreshold,0.9966);
   assert.doesNotThrow(()=>ensureAutoFailToggleV4(f,true));
   const h=transport({answer:r});
   assert.equal((await createAutoFailPolicyServiceV4(h.value).saveThreshold(b,'99.66','98','100')).partCode,partCode);
   const wrong=transport({answer:{...r,partCode:'COWL_COVER'}});
   await assert.rejects(createAutoFailPolicyServiceV4(wrong.value).saveThreshold(b,'99.66','98','100'),/응답/);
   const enabled={...on,partCode};
   assert.equal((await createAutoFailPolicyServiceV4(transport({answer:enabled}).value).saveToggle(r,true)).partCode,partCode);
 });
}
