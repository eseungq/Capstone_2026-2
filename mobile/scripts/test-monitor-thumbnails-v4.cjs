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

const { resolveMonitoringThumbnailUrlV4: url, monitoringThumbnailNeedsReloadV4: needsReload } =
  require(path.join(__dirname, '../src/api/backendV4/monitoringThumbnailUrlV4.ts'));

test('signed absolute thumbnail URI is passed through unmodified', () => {
  const signed = 'https://cdn.example.com/i/123.jpg?Signature=a%2Fb&Expires=88';
  assert.equal(url(signed, 'http://100.0.0.2:8080'), signed);
});

test('server-root relative thumbnail URI uses the server origin', () => {
  assert.equal(url('/images/a.jpg?token=x', 'http://100.0.0.2:8080/api'), 'http://100.0.0.2:8080/images/a.jpg?token=x');
});

test('relative thumbnail URI uses configured base path', () => {
  assert.equal(url('images/a.jpg', 'http://100.0.0.2:8080/api'), 'http://100.0.0.2:8080/api/images/a.jpg');
});

test('missing or invalid URLs render a fallback instead of a broken image', () => {
  assert.equal(url(null, 'http://100.0.0.2:8080'), null);
  assert.equal(url('', 'http://100.0.0.2:8080'), null);
  assert.equal(url('/images/a.jpg', ''), null);
  assert.equal(url('file:///private/photo.png', 'http://100.0.0.2:8080'), null);
  assert.equal(url('//untrusted.example.com/a.png', 'http://100.0.0.2:8080'), null);
  assert.equal(url('javascript:alert(1)', 'http://100.0.0.2:8080'), null);
});


test('rotating signatures for the same inspection photo do not reload every five seconds', () => {
  const now = 1_700_000_000_000;
  const current = 'https://example.test/images/pic?exp=1700000600&sig=old';
  const rotated = 'https://example.test/images/pic?exp=1700000605&sig=new';
  assert.equal(needsReload(current, rotated, now), false);
  assert.equal(needsReload(current, rotated, now + 5000), false);
});

test('thumbnail refreshes when the existing signed URL nears expiration', () => {
  const current = 'https://example.test/images/pic?exp=1700000600&sig=old';
  const newer = 'https://example.test/images/pic?exp=1700001200&sig=new';
  assert.equal(needsReload(current, newer, 1_700_000_539_000), false);
  assert.equal(needsReload(current, newer, 1_700_000_540_000), true);
  assert.equal(needsReload(current, newer, 1_700_000_601_000), true);
});

test('a different image resource loads immediately even with unexpired signature', () => {
  const current = 'https://example.test/images/old?exp=1700000600&sig=a';
  const different = 'https://example.test/images/new?exp=1700000605&sig=b';
  assert.equal(needsReload(current, different, 1_700_000_000_000), true);
});

test('stale or equal signed URL is not preferred over the displayed version', () => {
  const current = 'https://example.test/images/pic?exp=1700000600&sig=old';
  const older = 'https://example.test/images/pic?exp=1700000500&sig=older';
  assert.equal(needsReload(current, current, 1_700_000_580_000), false);
  assert.equal(needsReload(current, older, 1_700_000_580_000), false);
  assert.equal(needsReload(current, null, 1_700_000_580_000), false);
});

test('unknown URL expiry is conservative and changed URLs can reload', () => {
  const plain = 'https://example.test/images/pic?token=a';
  const rotated = 'https://example.test/images/pic?token=b';
  assert.equal(needsReload(plain, rotated, 1_700_000_000_000), true);
  assert.equal(needsReload(null, plain, 1_700_000_000_000), true);
});

test('new signature must actually extend the expiry before renewing', () => {
  const old = 'https://example.test/images/pic?exp=1700000600&sig=old';
  const soon = 'https://example.test/images/pic?exp=1700000600&sig=new';
  const newer = 'https://example.test/images/pic?exp=1700000601&sig=new';
  assert.equal(needsReload(old, soon, 1_700_000_590_000), false);
  assert.equal(needsReload(old, newer, 1_700_000_590_000), true);
});
