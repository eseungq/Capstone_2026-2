const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

// Verify the presentation rules without simulating native pixel or touch behavior.
const rules = [
  {
    "path": "app/judgement-request-live.tsx",
    "buttons": [
      "choice",
      "outline",
      "submit",
      "backTouch"
    ],
    "fonts": {
      "link": 14,
      "strong": 14,
      "muted": 13,
      "input": 14,
      "submitText": 14
    }
  },
  {
    "path": "app/judgement-requests-admin-live.tsx",
    "buttons": [
      "filter",
      "part",
      "outline",
      "submit",
      "backTouch"
    ],
    "fonts": {
      "link": 14,
      "strong": 14,
      "muted": 13,
      "error": 13,
      "success": 13,
      "filterText": 12,
      "input": 14,
      "submitText": 14
    }
  },
  {
    "path": "app/batch-fail-live.tsx",
    "buttons": [
      "outline",
      "action",
      "danger",
      "modalBackButton",
      "backTouch",
      "removeTouch"
    ],
    "fonts": {
      "back": 14,
      "strong": 14,
      "muted": 13,
      "error": 13,
      "outlineText": 13,
      "actionText": 14,
      "remove": 13,
      "input": 14
    }
  },
  {
    "path": "app/inspection-live.tsx",
    "buttons": [
      "backTouch",
      "button",
      "secondaryButton"
    ],
    "fonts": {
      "back": 14,
      "label": 13,
      "muted": 13,
      "imageOpenText": 12,
      "buttonText": 14,
      "secondaryButtonText": 14,
      "staleText": 13
    }
  },
  {
    "path": "app/admin-daily-live.tsx",
    "buttons": [
      "chip",
      "primary",
      "outline",
      "backTouch"
    ],
    "fonts": {
      "strong": 14,
      "muted": 13,
      "chipText": 12,
      "input": 14,
      "primaryText": 14,
      "link": 13,
      "lineLabel": 13,
      "lineValue": 13
    }
  },
  {
    "path": "app/policy-live.tsx",
    "buttons": [
      "button",
      "backTouch"
    ],
    "fonts": {
      "back": 14,
      "subtitle": 13,
      "label": 13,
      "value": 13,
      "muted": 13,
      "hint": 13,
      "buttonText": 14,
      "noticeText": 13,
      "errorText": 13,
      "successText": 13,
      "footer": 12
    }
  },
  {
    "path": "components/HistoryLiveScreenV4.tsx",
    "buttons": [
      "chip",
      "refreshButton",
      "retryButton",
      "pageButton"
    ],
    "fonts": {
      "subtitle": 13,
      "filterTitle": 13,
      "chipText": 12,
      "caption": 13,
      "refreshText": 13,
      "itemTitle": 14,
      "detailLink": 13,
      "itemState": 13,
      "pageButtonText": 13
    }
  },
  {
    "path": "app/rechecks-live.tsx",
    "buttons": [
      "filter",
      "secondaryButton",
      "backTouch"
    ],
    "fonts": {
      "sub": 13,
      "noticeText": 13,
      "filterText": 12,
      "itemTitle": 14,
      "muted": 13,
      "link": 14
    }
  },
  {
    "path": "app/recheck-summary-live.tsx",
    "buttons": [
      "filter",
      "backTouch"
    ],
    "fonts": {
      "filterLabel": 13,
      "fieldLabel": 13,
      "fieldValue": 13,
      "muted": 13,
      "link": 14,
      "metricTitle": 12,
      "strong": 13
    }
  }
];
for (const rule of rules) test('UI size rules: ' + rule.path, () => {
  const file = path.join(__dirname, '../src', rule.path);
  const code = fs.readFileSync(file, 'utf8');
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  assert.equal(source.parseDiagnostics.length, 0, 'Valid TSX');
  let styles;
  function walk(node) {
    if (ts.isCallExpression(node) && node.expression.getText(source) === 'StyleSheet.create' &&
        ts.isObjectLiteralExpression(node.arguments[0])) styles = node.arguments[0];
    ts.forEachChild(node, walk);
  }
  walk(source);
  assert.ok(styles);
  function size(name, key) {
    const item = styles.properties.find(p => p.name?.getText(source) === name);
    assert.ok(item && ts.isPropertyAssignment(item) && ts.isObjectLiteralExpression(item.initializer), name);
    const prop = item.initializer.properties.find(p => p.name?.getText(source) === key);
    assert.ok(prop && ts.isPropertyAssignment(prop) && ts.isNumericLiteral(prop.initializer), name + '.' + key);
    return Number(prop.initializer.text);
  }
  for (const name of rule.buttons) assert.ok(size(name, 'minHeight') >= 44, name);
  for (const [name, font] of Object.entries(rule.fonts)) assert.ok(size(name, 'fontSize') >= font, name);
});

test('worker monitoring puts the pending queue before recent inspections without changing admin order', () => {
  const code = fs.readFileSync(path.join(__dirname, '../src/components/MonitoringLiveDashboardV4.tsx'), 'utf8');
  const source = ts.createSourceFile('MonitoringLiveDashboardV4.tsx', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  assert.equal(source.parseDiagnostics.length, 0);
  assert.match(code, /isAuthenticatedWorker \? \[queueCard, recentCard\] : \[recentCard, queueCard\]/);
  assert.match(code, /key="recent"/);
  assert.match(code, /key="queue"/);
  const queue = code.slice(code.indexOf('const queueCard ='), code.indexOf('return (\n    <View style={styles.container}>'));
  assert.ok(queue.indexOf('queueItems.slice(0, visibleQueueCount).map') >= 0);
  assert.ok(queue.indexOf('queueItems.slice(0, visibleQueueCount).map') < queue.indexOf("pathname: '/batch-fail-live'"));
  assert.match(queue, /\{canOpenBatch && \(/);
  assert.match(code, /const canOpenBatch = isAuthenticatedWorker/);
  assert.match(queue, /params: \{partCode, sort: queueSort, aiDefectOnly: String\(aiDefectOnly\)\}/);
});

test('policy screen defaults to pass editing and separates fail editing and version management', () => {
  const code = fs.readFileSync(path.join(__dirname, '../src/app/policy-live.tsx'), 'utf8');
  const source = ts.createSourceFile('policy-live.tsx', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  assert.equal(source.parseDiagnostics.length, 0);
  assert.match(code, /useState<PolicySection>\('pass'\)/);
  assert.match(code, /\{access === 'admin' && !loading && \(/);
  assert.match(code, /accessibilityState=\{\{selected:section===item.value,disabled:writing!==null\}\}/);
  assert.match(code, /onPress=\{\(\)=>selectSection\(item.value\)\}/);
  assert.match(code, /Keyboard\.dismiss\(\);/);
  const ui = code.slice(code.indexOf('<Card title="현재 적용 중인 정책">'));
  const pass = ui.indexOf("{section === 'pass' && (");
  const fail = ui.indexOf("{section === 'fail' && (");
  const versions = ui.indexOf("{section === 'versions' && (");
  assert.ok(pass > 0 && fail > pass && versions > fail);
  assert.match(ui.slice(0,pass), /정책 버전/);
  assert.match(ui.slice(0,pass), /자동 통과 기준/);
  assert.match(ui.slice(0,pass), /통과 검증 범위/);
  assert.match(ui.slice(pass,fail), /onPress=\{confirmSave\}/);
  assert.match(ui.slice(fail,versions), /onPress=\{confirmSaveFail\}/);
  assert.match(ui.slice(fail,versions), /confirmAutoFailToggle\(true\)/);
  assert.match(ui.slice(fail,versions), /팀 승인 시험 범위/);
  assert.match(ui.slice(versions), /confirmActivate\(currentSaved\)/);
  assert.match(ui.slice(versions), /confirmActivate\(policy\)/);
  assert.match(ui.slice(versions), /원래 정책으로 복귀/);
});

test('policy save feedback stays visible and successful writes only switch to version management', () => {
  const code = fs.readFileSync(path.join(__dirname, '../src/app/policy-live.tsx'), 'utf8');
  const start = code.indexOf('const confirmedWrite =');
  const end = code.indexOf('const confirmSave =',start);
  const wrapper = code.slice(start,end);
  assert.match(wrapper, /await operation\(visit\);/);
  assert.match(wrapper, /if \(visit\.isCurrent\(\)\) selectSection\('versions'\);/);
  assert.doesNotMatch(wrapper, /\.activate\(|confirmActivate\(/);
  const ui = code.slice(code.indexOf('<Card title="현재 적용 중인 정책">'));
  const first = ui.indexOf("{section === 'pass' && (");
  assert.ok(ui.indexOf('{actionNotice &&') > 0 && ui.indexOf('{actionNotice &&') < first);
  assert.ok(ui.indexOf('{actionError &&') > 0 && ui.indexOf('{actionError &&') < first);
  assert.match(ui, /disabled=\{!canWrite \|\| !validInput\}/);
  assert.match(ui, /disabled=\{!canWrite\|\|!failEditValid\}/);
});

test('inspection detail keeps identity in the header and preserves the receipt time and manual label', () => {
  const code=fs.readFileSync(path.join(__dirname, '../src/app/inspection-live.tsx'),'utf8');
  const source=ts.createSourceFile('inspection-live.tsx',code,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  assert.equal(source.parseDiagnostics.length,0);
  const ui=code.slice(code.lastIndexOf('return (\n    <SafeAreaView'));
  assert.match(ui,/partLabelV4\(visibleDetail\.partCode\) \+ ' · ' \+ visibleDetail\.inspectionNo/);
  assert.match(ui,/visibleDetail\.displayStateLabel/);
  assert.doesNotMatch(ui,/<Field label="부품 · 검사번호"/);
  assert.doesNotMatch(ui,/<Field label="상태" value=\{visibleDetail\.displayStateLabel\}/);
  assert.match(ui,/formatTime\(visibleDetail\.receivedAt\)/);
  assert.match(ui,/visibleDetail\.source === 'MANUAL' && <Text style=\{styles\.receiptValue\}>수동 판정/);
});

test('inspection photo layout uses side-by-side panels only for two available URLs and keeps missing reasons', () => {
  const code=fs.readFileSync(path.join(__dirname,'../src/app/inspection-live.tsx'),'utf8');
  assert.match(code,/visibleDetail\.originalImageUrl && visibleDetail\.gradcamImageUrl \? styles\.imageRow : styles\.imageStack/);
  assert.equal((code.match(/compact=\{!!visibleDetail\.originalImageUrl && !!visibleDetail\.gradcamImageUrl\}/g)||[]).length,2);
  assert.match(code,/!url && styles\.missingImageCard/);
  assert.match(code,/<Text style=\{styles\.muted\}>\{missingText\}<\/Text>/);
  assert.match(code,/missingText=\{gradcamMissing\}/);
  assert.match(code,/resizeMode="contain"/);
  assert.match(code,/onError=\{\(\) => onLoadError\(url\)\}/);
  assert.match(code,/params: \{ inspectionId: id, kind: 'gradcam' \}/);
  assert.match(code,/params: \{ inspectionId: id, kind: 'original' \}/);
});

test('daily history emphasizes original per-row totals without aggregating or losing manual and failure notes', () => {
  const code=fs.readFileSync(path.join(__dirname,'../src/app/admin-daily-live.tsx'),'utf8');
  const source=ts.createSourceFile('admin-daily-live.tsx',code,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  assert.equal(source.parseDiagnostics.length,0);
  const card=code.slice(code.indexOf('function DailyRowCard'),code.indexOf('export default function AdminDailyLiveScreen'));
  for(const expression of ['{row.total}건','{row.autoPass}건','{row.autoFail}건','{row.review.total}건'])assert.ok(card.includes(expression),expression);
  assert.ok(card.includes('수동 전환 (작업자 확인에 포함)'));
  assert.ok(card.includes('AI 분석 실패 (집계 제외)'));
  assert.match(card,/oppositeEvidenceTextV4\(row\)/);
  assert.match(card,/dailyAiReviewRateV4\(row\)/);
  assert.match(card,/\{expanded&&<View style=\{s\.detailStats\}>/);
  assert.match(card,/row\.confirmedOpposite\.autoPassThenFail/);
  assert.match(card,/row\.confirmedOpposite\.autoFailThenPass/);
  assert.match(card,/row\.openRequests/);
  assert.match(code,/rows\.map\(\(row,index\)=>\(/);
  assert.doesNotMatch(card,/\.reduce\(/);
});
test('daily threshold detail is placed under the selected policy row and retains the same read controls',()=>{
  const code=fs.readFileSync(path.join(__dirname,'../src/app/admin-daily-live.tsx'),'utf8');
  const rows=code.slice(code.indexOf('{rows.map((row,index)=>('),code.indexOf('통계의 \'판정 완료\''));
  assert.match(rows,/<DailyRowCard/);
  assert.match(rows,/\{selected===row&&<View style=\{s\.detailCard\}>/);
  assert.ok(rows.indexOf('기준 상세')<rows.indexOf('</DailyRowCard>'));
  assert.match(rows,/onPress=\{\(\)=>\{void viewDetail\(selected\);\}\}/);
  assert.match(rows,/reads\.resetDetail\(\);setBand\(x\)/);
  assert.match(code,/reads\.loadDetail\(part,row\.date,row\.policyId,band\)/);
  assert.match(rows,/band=\{detail\.passBand\}/);
  assert.match(rows,/band=\{detail\.failBand\}/);
});

test('history part filter offers only current part codes plus all without a keyboard or apply button', () => {
  const code=fs.readFileSync(path.join(__dirname,'../src/components/HistoryLiveScreenV4.tsx'),'utf8');
  const source=ts.createSourceFile('HistoryLiveScreenV4.tsx',code,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  assert.equal(source.parseDiagnostics.length,0);
  const options=code.slice(code.indexOf('const parts:'),code.indexOf('const stateLabels:'));
  assert.deepEqual([...options.matchAll(/value: '([^']*)', label: /g)].map(match=>match[1]),['','DOOR','FRAME','COWL_COVER']);
  assert.match(code,/useState<PartFilter>\(\(\)=>parts\.find\(option=>option\.value===params\.partCode\)\?\.value\?\?''\)/);
  const ui=code.slice(code.indexOf('>부품 선택</Text>'),code.indexOf('<View style={styles.resultsCard}>'));
  assert.match(ui,/parts\.map\(\(option\) =>/);
  assert.match(ui,/styles\.chip, partCode === option\.value && styles\.chipActive/);
  assert.match(ui,/onPress=\{\(\) => selectPart\(option\.value\)\}/);
  assert.match(ui,/accessibilityState=\{\{ selected: partCode === option\.value \}\}/);
  assert.doesNotMatch(code,/TextInput|KeyboardAvoidingView|partDraft|applyPart/);
});
test('history filter changes preserve other query options and reject stale reads while resetting the page',()=>{
  const code=fs.readFileSync(path.join(__dirname,'../src/components/HistoryLiveScreenV4.tsx'),'utf8');
  const reset=code.slice(code.indexOf('const resetForFilter ='),code.indexOf('const setStatus ='));
  for(const statement of ['requestSerial.current += 1;','setPage(0);','setData(null);','setError(null);','setLoading(true);','setRefreshing(false);'])assert.ok(reset.includes(statement),statement);
  const select=code.slice(code.indexOf('const selectPart ='),code.indexOf('const toMonitor ='));
  assert.match(select,/if \(next === partCode\) return;/);
  assert.match(select,/resetForFilter\(\);\s*setPartCode\(next\);/);
  assert.doesNotMatch(select,/setStateFilter|setPeriod|load\(/);
  const status=code.slice(code.indexOf('const setStatus ='),code.indexOf('const selectPart ='));
  assert.equal((status.match(/resetForFilter\(\);/g)||[]).length,2);
  assert.match(code,/\.\.\.\(partCode \? \{ partCode \} : \{\}\)/);
  assert.match(code,/\.\.\.\(stateFilter !== 'ALL' \? \{ displayState: stateFilter \} : \{\}\)/);
  assert.match(code,/\.\.\.\(from \? \{ from \} : \{\}\)/);
  assert.match(code,/\}, \[page, partCode, stateFilter, period\]\)/);
  assert.match(code,/if \(requestSerial\.current !== serial\) return;/);
  assert.match(code,/void load\(true\);/);
});
