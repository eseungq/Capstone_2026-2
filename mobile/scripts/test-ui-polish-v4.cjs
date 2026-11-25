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
      "applyButton",
      "refreshButton",
      "retryButton",
      "pageButton"
    ],
    "fonts": {
      "subtitle": 13,
      "filterTitle": 13,
      "chipText": 12,
      "applyButtonText": 13,
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
  assert.match(queue, /\{isAuthenticatedWorker && \(/);
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
