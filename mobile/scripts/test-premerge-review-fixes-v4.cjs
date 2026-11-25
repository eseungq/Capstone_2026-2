const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
Module._extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{fileName:f,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,f);
const {createAuthV4}=require('../src/api/backendV4/authCore.ts');
const {makeRecheckSubmitBodyV4}=require('../src/api/backendV4/recheckCoreV4.ts');
const {judgementRequestStatusLabelV4}=require('../src/api/backendV4/judgementRequestCoreV4.ts');
const flush=()=>new Promise(r=>setImmediate(r));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const session=id=>({accessToken:'test-'+id,refreshToken:'test-refresh-'+id,role:'WORKER',loginId:id});

test('KEPT preserves the current judgement, including after a prior correction',()=>{
  assert.equal(judgementRequestStatusLabelV4('KEPT'),'현재 판정 유지');
  assert.equal(judgementRequestStatusLabelV4('OPEN'),'확인 대기');
  assert.equal(judgementRequestStatusLabelV4('CORRECTED'),'정정 완료');
});
test('untrusted timing fields cannot override the recheck result or comment',()=>{
  const timing={screenDwellMs:3000,firstOpenedAt:'2026-11-25T13:00:00Z',openCount:1,result:'PASS',comment:'injected',extra:1};
  assert.deepEqual(makeRecheckSubmitBodyV4('FAIL','reviewed',timing),{
    result:'FAIL',comment:'reviewed',screenDwellMs:3000,firstOpenedAt:timing.firstOpenedAt,openCount:1,
  });
  assert.equal(timing.result,'PASS');
});
for(const previous of [null,session('existing')]){
  for(const secondSucceeds of [false,true]){
    test(`cancelled login storage is rolled back before readers (prior=${previous?.loginId??'none'}, newer=${secondSucceeds})`,async()=>{
      let stored=previous;
      const started=deferred(),release=deferred();
      const vault={async read(){return stored;},async clear(){stored=null;},async write(value){
        if(value.loginId==='A'){started.resolve();await release.promise;}stored=value;
      }};
      const auth=createAuthV4({baseUrl:'https://test.invalid/api/v1',vault,fetchImpl:async(_url,opts)=>{
        const id=JSON.parse(opts.body).loginId;
        return id==='A'||secondSucceeds?Response.json({data:session(id)}):Response.json({error:{code:'AUTH_INVALID_CREDENTIALS'}},{status:401});
      }});
      const a=auth.login('A','test').then(()=>true,()=>false);
      await started.promise;
      const b=auth.login('B','test').then(()=>true,()=>false);
      await flush();
      const reader=auth.restore();
      release.resolve();
      assert.equal(await a,false);assert.equal(await b,secondSucceeds);
      const during=await reader;assert.notEqual(during.loginId,'A');
      const restored=await auth.restore();
      assert.equal(restored.loginId,secondSucceeds?'B':previous?.loginId??null);
      assert.equal(restored.signedIn,secondSucceeds||previous!==null);
    });
  }
}
test('an uncontested login still saves and restores its own account',async()=>{
  let stored=null;
  const auth=createAuthV4({baseUrl:'https://test.invalid/api/v1',vault:{async read(){return stored},async write(s){stored=s},async clear(){stored=null}},fetchImpl:async()=>Response.json({data:session('A')})});
  assert.equal((await auth.login('A','test')).loginId,'A');
  assert.equal((await auth.restore()).loginId,'A');
});

// Execute the production screen functions with controllable hooks and services.
// Native pixel layout is outside this harness; event handlers/state are exercised.
function screenHarness(filename,overrides={}){
  const slots=[];let cursor=0,focusEffect,tree;
  const effects=[];
  const slot=init=>{const i=cursor++;if(!slots[i])slots[i]={current:init()};return slots[i];};
  const hooks={
    useRef:initial=>slot(()=>initial),useCallback:fn=>fn,
    useState(initial){const s=slot(()=>typeof initial==='function'?initial():initial);return [s.current,value=>{s.current=typeof value==='function'?value(s.current):value;}];},
    useEffect(fn,deps){const s=slot(()=>({deps:undefined}));if(!s.current.deps||!deps||deps.some((d,i)=>d!==s.current.deps[i])){s.current.deps=deps;effects.push(fn);}},
  };
  const native=Object.fromEntries(['ActivityIndicator','Image','KeyboardAvoidingView','Pressable','RefreshControl','ScrollView','Text','TextInput','View'].map(x=>[x,x]));
  Object.assign(native,{StyleSheet:{create:x=>x,hairlineWidth:1},Platform:{OS:'ios'},Alert:{alert(){}},AppState:{currentState:'active',addEventListener(){return {remove(){}};}}});
  const mocks={react:hooks,'react-native':native,'react-native-safe-area-context':{SafeAreaView:'SafeAreaView'},
    'expo-router':{Stack:{Screen:'Screen'},router:{back(){},push(){}},useLocalSearchParams:()=>({inspectionId:'inspection-test'}),useFocusEffect:fn=>{focusEffect=fn;}},
    '../components/useRevealFocusedInputV4':{useRevealFocusedInputV4:()=>()=>{}},...overrides};
  const file=path.join(__dirname,'../src/app',filename),screen=new Module(file,module);
  screen.filename=file;
  screen.paths=Module._nodeModulePaths(path.dirname(file));
  screen.require=id=>Object.hasOwn(mocks,id)?mocks[id]:Module.prototype.require.call(screen,id);
  screen._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{fileName:file,compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText,file);
  const render=()=>{cursor=0;tree=screen.exports.default();return tree;};
  const find=(predicate,node=tree)=>{
    if(Array.isArray(node)){for(const child of node){const found=find(predicate,child??null);if(found)return found;}return;}
    if(!node?.props)return;if(predicate(node))return node;return find(predicate,node.props.children??null);
  };
  return {render,find,focus:()=>focusEffect(),effects:()=>{for(const fn of effects.splice(0))fn();}};
}
test('inspection retry restores the failed role check and only starts dwell after detail arrives',async()=>{
  let restores=0,reads=0,dwells=0;
  const detail=deferred();
  const auth={sessionEpoch:()=>1,restore:async()=>{if(++restores===1)throw Error('temporary role read');return {signedIn:true,role:'WORKER',loginId:'worker'};}};
  const h=screenHarness('inspection-live.tsx',{
    '../api/backendV4/authRuntime':{authV4:auth},
    '../api/backendV4/inspectionReadService':{createInspectionReadServiceV4:()=>({detail:async()=>{reads++;return detail.promise;}})},
    '../api/backendV4/inspectionWriteService':{createInspectionWriteServiceV4:()=>({})},
    '../api/backendV4/recheckServiceV4':{createRecheckServiceV4:()=>({})},
    '../api/backendV4/inspectionDwellV4':{inspectionDwellForSessionV4:()=>({focus(){dwells++},blur(){}})},
  });
  h.render();const blur=h.focus();await flush();h.render();
  const retry=h.find(n=>n.type==='Pressable'&&n.props.children?.props?.children==='다시 조회');
  assert.ok(retry);retry.props.onPress();await flush();
  assert.equal(restores,2);assert.equal(reads,1);assert.equal(dwells,0);
  detail.resolve({source:'SERVER',value:{inspectionId:'inspection-test',inspectionNo:'INS-TEST',partCode:'DOOR',displayState:'REVIEW_PENDING',receivedAt:'2026-11-25T13:00:00Z',canOfferConfirm:true,calibratedDefectProbability:null,judgementRequests:[],gradcamStatus:'NOT_REQUIRED'}});
  await flush();h.render();
  assert.ok(h.find(n=>n.props.testID==='inspection-confirm-pass'));assert.equal(dwells,1);blur();
});
for(const outcome of ['resolved','error']){
 test(`admin refresh immediately clears selected request and stale confirmation (${outcome})`,async()=>{
  let lists=0,resolveCalls=0;const reload=deferred(),alerts=[];
  const entry={requestId:'request-A',inspectionId:'inspection-A',inspectionNo:'INS-A',partCode:'DOOR',status:'OPEN',originalJudgement:'PASS',currentJudgement:'PASS',claimedJudgement:'FAIL'};
  const h=screenHarness('judgement-requests-admin-live.tsx',{
   '../api/backendV4/authRuntime':{authV4:{sessionEpoch:()=>1,restore:async()=>({signedIn:true,role:'ADMIN'})}},
   '../api/backendV4/judgementRequestServiceV4':{createJudgementRequestServiceV4:()=>({list:async()=>++lists===1?{items:[entry],page:0,size:20,totalElements:1,totalPages:1}:reload.promise,resolve:async()=>{resolveCalls++;}})},
  });
  h.render();h.effects();await flush();h.render();h.effects();await flush();h.render();
  const entryButton=h.find(n=>n.type==='Pressable'&&Array.isArray(n.props.children)&&n.props.children.some(c=>c?.props?.children==='내용 검토 ›'));
  assert.ok(entryButton);entryButton.props.onPress();h.render();
  assert.ok(h.find(n=>n.type==='TextInput'));
  const refresh=h.find(n=>n.type==='Pressable'&&n.props.children?.props?.children==='요청 목록 새로고침');
  refresh.props.onPress();h.render();
  assert.equal(h.find(n=>n.type==='TextInput'),undefined);
  assert.equal(h.find(n=>n.props.children?.props?.children==='판정 유지 전 최종 확인'),undefined);
  if(outcome==='error')reload.resolve(Promise.reject(Error('offline')));
  else reload.resolve({items:[{...entry,status:'KEPT'}],page:0,size:20,totalElements:1,totalPages:1});
  await flush();h.render();assert.equal(h.find(n=>n.type==='TextInput'),undefined);assert.equal(resolveCalls,0);
 });
}
test('README starts the current demo with a real account and archives the old Mock path',()=>{
  const readme=fs.readFileSync(path.join(__dirname,'../README.md'),'utf8');
  const steps=readme.split('## 현재 iPhone 시연 절차')[1].split('## 과거 독립 Mock')[0];
  assert.match(steps,/실제 관리자 계정으로 로그인/);
  assert.doesNotMatch(steps,/Mock ADMIN\*\* →/);
});
