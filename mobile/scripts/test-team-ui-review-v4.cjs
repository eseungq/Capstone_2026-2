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
  assert.match(code,/\{visibleDetail\.displayStateLabel\}/);
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
