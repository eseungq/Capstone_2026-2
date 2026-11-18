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

const { resolveMonitoringThumbnailUrlV4: url } =
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
