const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const read = (file) => fs.readFileSync(path.join(__dirname, '../src', file), 'utf8');
function parse(file) {
  const code = read(file);
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  assert.equal(source.parseDiagnostics.length, 0);
  return {code,source};
}
function elementsByTestID(source, id) {
  const found=[];
  const walk=(node,ancestors=[])=>{
    if(ts.isJsxElement(node)||ts.isJsxSelfClosingElement(node)){
      const opening=ts.isJsxElement(node)?node.openingElement:node;
      const attr=opening.attributes.properties.find(p=>ts.isJsxAttribute(p)&&p.name.getText(source)==='testID');
      if(attr&&attr.initializer?.text===id)found.push({opening,ancestors});
      if(ts.isJsxElement(node))ancestors=[...ancestors,opening.tagName.getText(source)];
    }
    ts.forEachChild(node,child=>walk(child,ancestors));
  };
  walk(source);
  return found;
}
test('REVIEW decision controls are fixed within the keyboard-adjusted area, outside the scroll view',()=>{
  const {code,source}=parse('app/inspection-live.tsx');
  for(const [id,decision] of [['inspection-confirm-pass','PASS'],['inspection-confirm-fail','FAIL']]){
    const found=elementsByTestID(source,id);
    assert.equal(found.length,1);
    assert.ok(found[0].ancestors.includes('KeyboardAvoidingView'));
    assert.ok(!found[0].ancestors.includes('ScrollView'));
    assert.ok(found[0].opening.getText(source).includes("requestConfirm('"+decision+"')"));
    assert.match(found[0].opening.getText(source),/disabled=\{submitting !== null\}/);
  }
  assert.match(code,/const canShowConfirm = !roleLoading && role === 'WORKER' && visibleDetail\?\.canOfferConfirm === true/);
  assert.match(code,/\{canShowConfirm && \(\s*<View style=\{styles\.confirmFooter\}/);
  assert.match(code,/Alert\.alert\(\s*'실제 서버 최종 판정'/);
  assert.match(code,/buttonRow: \{ flexDirection: 'row', gap: 12 \}/);
});
test('inspection detail keeps state, trace data, and all memo labels without duplicate decision buttons',()=>{
  const {code,source}=parse('app/inspection-live.tsx');
  assert.match(code,/<Text style=\{styles.title\}>검사 상세<\/Text>/);
  assert.match(code,/visibleDetail\.displayState === 'REVIEW_PENDING' \? '판정 대기' : visibleDetail\.displayStateLabel/);
  assert.match(code,/field: \{ flexDirection: 'row'/);
  assert.match(code,/최초 판정 주체/);
  assert.match(code,/최초 판정 시각/);
  assert.match(code,/판단 근거 이미지는 결함 위치를 확정하는 좌표나 마스크가 아닙니다/);
  for(const id of ['inspection-review-memo','inspection-recheck-memo','inspection-acknowledge-memo']){
    const found=elementsByTestID(source,id);
    assert.equal(found.length,1);
    assert.ok(found[0].ancestors.includes('ScrollView'));
    assert.match(found[0].opening.getText(source),/accessibilityLabel=/);
  }
});

test('history and monitor keep actual part codes while using readable labels and status-aware accessible rows',()=>{
  const {code:h,source}=parse('components/HistoryLiveScreenV4.tsx');
  const m=parse('components/MonitoringLiveDashboardV4.tsx').code;
  for(const [code,label] of [['DOOR','도어'],['FRAME','프레임'],['COWL_COVER','카울커버']]){
    assert.ok(h.includes("value: '"+code+"', label: '"+label+"'"));
    assert.ok(read('components/partLabelV4.ts').includes("case '"+code+"': return '"+label+"'"));
  }
  assert.match(h,/accessibilityLabel=\{\x60\$\{item\.inspectionNo.*stateLabels\[item\.displayState\].*partLabelV4\(item\.partCode\)/);
  assert.doesNotMatch(h,/<Text style=\{styles\.itemTitle\} numberOfLines=/);
  assert.match(h,/<Text style=\{styles\.itemState\}>\{partLabelV4\(item\.partCode\)\}/);
  assert.match(m,/statusLabel\(item\.displayState\)/);
  assert.match(m,/\{partLabelV4\(code\)\}/);
  assert.match(m,/setPartCode\(code\)/);
});
test('batch checked state and date input labels are explicit',()=>{
  const {code:b,source:bs}=parse('app/batch-fail-live.tsx');
  const {code:d,source:ds}=parse('app/admin-daily-live.tsx');
  const checkbox=elementsByTestID(bs,'batch-ai-defect-filter')[0];
  assert.ok(checkbox);
  assert.match(checkbox.opening.getText(bs),/aria-checked=\{filters\.aiDefectOnly\}/);
  assert.match(checkbox.opening.getText(bs),/accessibilityState=\{\{checked:filters\.aiDefectOnly/);
  for(const id of ['daily-start-date','daily-end-inclusive-date','daily-threshold-band']){
    const fields=elementsByTestID(ds,id);
    assert.equal(fields.length,1);
    assert.match(fields[0].opening.getText(ds),/accessibilityLabel=/);
  }
});
test('unchanged or duplicate policy values use neutral help, actual invalid edits use error style',()=>{
  const {code}=parse('app/policy-live.tsx');
  assert.match(code,/validInput\?s\.hint:invalidPassInput\?s\.errorText:s\.muted/);
  assert.match(code,/failEditValid\?s\.hint:invalidFailInput\?s\.errorText:s\.muted/);
  assert.match(code,/validationText = errorText\(cause\);\s*invalidPassInput = true;/);
  assert.match(code,/failEditHint=errorText\(cause\);invalidFailInput=true;/);
  assert.match(code,/disabled=\{!canWrite \|\| !validInput\}/);
  assert.match(code,/disabled=\{!canWrite\|\|!failEditValid\}/);
});
test('control colors retain text and non-text contrast with neutral card backgrounds',()=>{
  const luminance=hex=>hex.match(/[0-9a-f]{2}/gi).map(v=>parseInt(v,16)/255)
    .map(v=>v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4)
    .reduce((sum,v,i)=>sum+v*[0.2126,0.7152,0.0722][i],0);
  const contrast=(a,b)=>{const v=[luminance(a),luminance(b)].sort((x,y)=>y-x);return (v[0]+0.05)/(v[1]+0.05);};
  for(const bg of ['#FFFFFF','#F5F7FB','#F8FAFC','#EEF2F8']){
    assert.ok(contrast('#475569',bg)>=4.5);
    assert.ok(contrast('#64748B',bg)>=3);
  }
  assert.ok(contrast('#FFFFFF','#1E293B')>=4.5);
  for(const file of ['components/HistoryLiveScreenV4.tsx','components/MonitoringLiveDashboardV4.tsx','app/batch-fail-live.tsx','app/policy-live.tsx','app/admin-daily-live.tsx']){
    const {code}=parse(file);
    for(const color of ['#475569','#64748B','#1E293B'])assert.ok(code.includes(color),file+': '+color);
  }
});

test('management navigation is ADMIN-only and uses verified roles and a dedicated live route',()=>{
  const n=parse('components/LiveBottomNavV4.tsx').code;
  const m=parse('app/manage-live.tsx').code;
  const settings=parse('app/settings.tsx').code;
  assert.match(n,/tabs\.filter\(tab=>tab\.key!=='manage'\|\|role==='ADMIN'\)/);
  assert.match(n,/accessibilityState=\{\{selected:active===tab\.key\}\}/);
  assert.match(m,/role!=='ADMIN'/);
  for(const route of ['/judgement-requests-admin-live','/policy-live','/admin-daily-live','/rechecks-live'])assert.ok(m.includes(route));
  assert.match(settings,/mode === 'live' \? <LiveBottomNavV4/);
  assert.doesNotMatch(settings,/router\.push\('\/rechecks-live'\)/);
  assert.match(settings,/performLiveLogout\(origin\)/);
  assert.match(read('components/useVerifiedRoleV4.ts'),/epoch !== authV4\.sessionEpoch\(\)/);
});

test('worker recheck entry uses a verified session and a server count, never a fabricated zero',()=>{
  const {code}=parse('components/MonitoringLiveDashboardV4.tsx');
  assert.match(code,/session\.role!=='WORKER'\)return/);
  assert.match(code,/recheckReader\.list\(\{status:'PENDING',page:0,size:1\}\)/);
  assert.match(code,/if\(stillCurrent\(\)\)setRecheckCount\(result\.totalElements\)/);
  assert.match(code,/recheckCount===null\?\(recheckError\?'조회 실패/);
  assert.match(code,/isAuthenticatedWorker && <Pressable testID="monitor-recheck-entry"/);
  assert.match(code,/router\.push\('\/rechecks-live'\)/);
  assert.match(code,/vm\.part\?\.pendingReviewCount !== 0/);
  assert.match(code,/queueItems\.some\(item => item\.displayState === 'REVIEW_PENDING'\)/);
});
test('monitor counts route to exact history filters, which remain accessible in a compact disclosure',()=>{
  const {code:m}=parse('components/MonitoringLiveDashboardV4.tsx');
  const {code:h}=parse('components/HistoryLiveScreenV4.tsx');
  assert.match(m,/params:\{mode:'live',role:verifiedRole,partCode,displayState\}/);
  assert.match(m,/openFilteredHistory\('REVIEW_PENDING'\)/);
  assert.match(m,/openFilteredHistory\('FAILED'\)/);
  assert.match(h,/parts\.find\(option=>option\.value===params\.partCode\)/);
  assert.match(h,/states\.find\(option=>option\.value===params\.displayState\)/);
  assert.match(h,/useState\(false\);\s*const \[period/);
  assert.match(h,/accessibilityState=\{\{expanded:filtersExpanded\}\}/);
  assert.match(h,/\{filtersExpanded&&<>/);
  assert.match(h,/<RefreshControl/);
});

test('daily date selection is inclusive on screen but sends the next exclusive day to the existing reader',()=>{
  const {code}=parse('app/admin-daily-live.tsx');
  const calendar=parse('components/DailyDateCalendarV4.tsx').code;
  assert.match(code,/const \[to,setTo\]=useState\(today\)/);
  assert.match(code,/reads\.loadRows\(part,from,plusDaysV4\(to,1\)\)/);
  assert.match(code,/disabled=\{loading\|\|from>to\}/);
  assert.match(code,/<DailyDateCalendarV4/);
  assert.match(calendar,/getUTCDay\(\)/);
  assert.match(calendar,/plusDaysV4\(month,index-offset\)/);
  assert.match(calendar,/onPress=\{\(\)=>onSelect\(day\)\}/);
});

test('policy and inspection input focus is measured inside the existing keyboard-adjusted scroll area',()=>{
  for(const [file,ids] of [
    ['app/inspection-live.tsx',['inspection-review-memo','inspection-recheck-memo','inspection-acknowledge-memo']],
    ['app/policy-live.tsx',['policy-pass-input','policy-fail-input','policy-fail-min-input','policy-fail-max-input']],
  ]){
    const {code,source}=parse(file);
    assert.match(code,/useRevealFocusedInputV4\(scrollRef,getFocusedField\)/);
    assert.match(code,/onLayout=\{revealInput\}/);
    for(const id of ids){
      const input=elementsByTestID(source,id);
      assert.equal(input.length,1);
      assert.ok(input[0].ancestors.includes('KeyboardAvoidingView'));
      assert.ok(input[0].ancestors.includes('ScrollView'));
      assert.match(input[0].opening.getText(source),/onFocus=\{revealInput\}/);
    }
  }
  const hook=read('components/useRevealFocusedInputV4.ts');
  assert.match(hook,/Keyboard\.addListener\('keyboardDidShow',reveal\)/);
  assert.match(hook,/field\.measureLayout\(content,/);
  assert.match(hook,/subscription\?\.remove\(\)/);
});
test('inspection trace information is disclosed on demand, not deleted',()=>{
  const {code}=parse('app/inspection-live.tsx');
  assert.match(code,/accessibilityState=\{\{expanded:showTrace\}\}/);
  const trace=code.slice(code.indexOf('{showTrace&&'),code.indexOf('{visibleDetail.errorCode &&',code.indexOf('{showTrace&&'))<0?undefined:code.indexOf('{visibleDetail.errorCode &&',code.indexOf('{showTrace&&')));
  for(const field of ['partCode','judgedBy','confirmedBy','confirmedAt','modelVersion','policyVersion'])assert.ok(trace.includes('visibleDetail.'+field),field);
  assert.match(code,/setShowTrace\(false\)/);
});

test('read-only refresh gestures preserve explicit recovery and detail image refresh budgets',()=>{
  for(const file of ['app/inspection-live.tsx','app/policy-live.tsx','app/admin-daily-live.tsx','app/rechecks-live.tsx','app/recheck-summary-live.tsx','components/HistoryLiveScreenV4.tsx']){
    assert.match(parse(file).code,/<RefreshControl/);
  }
  const {code}=parse('app/inspection-live.tsx');
  const refresh=code.slice(code.indexOf('const refreshDetail='),code.indexOf('const canShowConfirm ='));
  for(const guard of ['loading||refreshing||submitting!==null','imageErrorBudget.current.reset()','failedImageUrls.current.clear()','void load(false)'])assert.ok(refresh.includes(guard),guard);
  assert.match(code,/onPress=\{refreshDetail\}/);
  assert.match(code,/판단 근거 이미지는 결함 위치를 확정하는 좌표나 마스크가 아닙니다/);
});

test('team feedback keeps request history in a vertical layout and removes review reason and empty Grad-CAM card',()=>{
  const {code}=parse('app/inspection-live.tsx');
  assert.match(code,/key=\{request.requestId\} style=\{styles.requestHistory\}/);
  assert.doesNotMatch(code,/label="확인 필요 사유"/);
  assert.match(code,/\{visibleDetail\.gradcamImageUrl && <ImagePanel embedded/);
  assert.match(code,/params: \{ inspectionId: id, kind: 'gradcam' \}/);
});
test('claim colors differ by judgement, and monitoring AI filter is a checkbox',()=>{
  const q=parse('app/judgement-request-live.tsx').code;
  const m=parse('components/MonitoringLiveDashboardV4.tsx').code;
  assert.match(q,/claim===value&&\(value==='PASS'\?s.choicePass:s.choiceFail\)/);
  assert.match(q,/choicePass:\{backgroundColor:'#2054D8'/);
  assert.match(q,/choiceFail:\{backgroundColor:'#B42318'/);
  assert.match(m,/testID="monitor-ai-defect-checkbox"\s*accessibilityRole="checkbox"\s*accessibilityState=\{\{ checked: aiDefectOnly \}\}/);
  assert.match(m,/<Text style=\{styles.priorityHint\}>판정 대기<\/Text>/);
});
