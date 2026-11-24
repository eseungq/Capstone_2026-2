const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

for (const [screen, submitText] of [
  ['judgement-request-live.tsx', '관리자 판정 확인 요청'],
  ['judgement-requests-admin-live.tsx', '판정 유지 전 최종 확인'],
]) test(screen + ': submit action stays outside the scrolling fields and within the keyboard-adjusted region', () => {
  const filename = path.join(__dirname, '../src/app', screen);
  const source = ts.createSourceFile(filename, readFileSync(filename, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const buttons = [];
  const scrolls = [];

  const isType = (node, type) => node.openingElement.tagName.getText(source) === type;
  function inspect(node, ancestors = []) {
    if ((ts.isStringLiteral(node) || ts.isJsxText(node)) && node.text.trim() === submitText &&
        ancestors.some(node => isType(node, 'Pressable'))) buttons.push(ancestors);
    if (ts.isJsxElement(node)) {
      const { tagName, attributes } = node.openingElement;
      const type = tagName.getText(source);
      if (type === 'ScrollView') scrolls.push({ ancestors, attributes });
      ancestors = [...ancestors, node];
    }
    ts.forEachChild(node, child => inspect(child, ancestors));
  }
  inspect(source);
  assert.equal(buttons.length, 1, 'Render exactly one submission control');
  assert.equal(scrolls.length, 1, 'The input fields must remain scrollable');
  const region = buttons[0].find(node => isType(node, 'KeyboardAvoidingView'));
  assert.ok(region, 'The submit control must move with the keyboard');
  assert.ok(scrolls[0].ancestors.includes(region), 'The keyboard-adjusted area must also contain the scroll view');
  assert.ok(!buttons[0].some(node => isType(node, 'ScrollView')), 'Scrolling through the fields must not hide submit');
  const autoInset = scrolls[0].attributes.properties.find(prop =>
    ts.isJsxAttribute(prop) && prop.name.text === 'automaticallyAdjustKeyboardInsets');
  assert.ok(!autoInset || autoInset.initializer?.getText(source) === '{false}',
    'Only the containing region should reserve keyboard space');
});

test('other live input screens keep their text fields in a keyboard-adjusted scroll area', () => {
  for (const screen of ['app/inspection-live.tsx','app/batch-fail-live.tsx','app/policy-live.tsx',
    'app/admin-daily-live.tsx','components/HistoryLiveScreenV4.tsx']) {
    const filename=path.join(__dirname,'../src',screen);
    const source=ts.createSourceFile(filename,readFileSync(filename,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
    let inputs=0;
    function walk(node, ancestors=[]) {
      if (ts.isJsxSelfClosingElement(node) && node.tagName.getText(source)==='TextInput') {
        inputs++;
        assert.ok(ancestors.includes('ScrollView') && ancestors.includes('KeyboardAvoidingView'),screen);
      }
      if (ts.isJsxElement(node)) ancestors=[...ancestors,node.openingElement.tagName.getText(source)];
      ts.forEachChild(node,child=>walk(child,ancestors));
    }
    walk(source);
    assert.ok(inputs>0,screen);
  }
});
