/**
 * 실제 authCore 소스를 사용한 서버 로그아웃/로컬 토큰 폐기 회귀 테스트.
 * 실제 네트워크나 iPhone 보안 저장소는 사용하지 않습니다.
 */
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

const { createAuthV4, makeMemoryAuthVault } = require(
  path.join(__dirname, '../src/api/backendV4/authCore.ts')
);

const token = {
  accessToken: 'test-access',
  refreshToken: 'test-refresh',
  role: 'WORKER',
  loginId: 'worker-demo',
};

function makeAuth(vault, fetchImpl) {
  return createAuthV4({
    baseUrl: 'https://test.invalid/api/v1',
    vault,
    fetchImpl,
    refreshBody: (refreshToken) => ({ refreshToken }),
    logoutBody: (refreshToken) => ({ refreshToken }),
  });
}

test('logout calls the backend once with refresh token then clears local session', async () => {
  const vault = makeMemoryAuthVault();
  await vault.write(token);
  const calls = [];
  const auth = makeAuth(vault, async (url, options) => {
    calls.push({ url, options });
    return new Response(null, { status: 204 });
  });
  assert.deepEqual(await auth.logout(), { remoteRevoked: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://test.invalid/api/v1/auth/logout');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer test-access');
  assert.deepEqual(JSON.parse(calls[0].options.body), { refreshToken: 'test-refresh' });
  assert.equal(await vault.read(), null);
  assert.deepEqual(await auth.restore(), { signedIn: false, role: null, loginId: null });
  await assert.rejects(() => auth.authorizedRequest('/inspections'), (err) => err.code === 'NOT_LOGGED_IN');
});

test('logout still clears device session when backend returns 500, without claiming remote revoke', async () => {
  const vault = makeMemoryAuthVault();
  await vault.write(token);
  const auth = makeAuth(vault, async () => new Response(
    JSON.stringify({ error: { code: 'SERVER_ERROR', message: 'failed' } }),
    { status: 500, headers: { 'Content-Type': 'application/json' } }
  ));
  assert.deepEqual(await auth.logout(), { remoteRevoked: false });
  assert.equal(await vault.read(), null);
});

test('logout still clears device session if network request fails', async () => {
  const vault = makeMemoryAuthVault();
  await vault.write(token);
  const auth = makeAuth(vault, async () => { throw new Error('network unreachable'); });
  assert.deepEqual(await auth.logout(), { remoteRevoked: false });
  assert.equal(await vault.read(), null);
});

test('logout without a stored session skips backend and remains logged out', async () => {
  const vault = makeMemoryAuthVault();
  let count = 0;
  const auth = makeAuth(vault, async () => {
    count += 1;
    throw new Error('should not request');
  });
  assert.deepEqual(await auth.logout(), { remoteRevoked: false });
  assert.equal(count, 0);
  assert.equal(await vault.read(), null);
});

test('failure to clear local secure tokens must not be reported as completed logout', async () => {
  const vault = {
    async read() { return { ...token }; },
    async write() {},
    async clear() { throw new Error('storage failure'); },
  };
  const auth = makeAuth(vault, async () => new Response(null, { status: 204 }));
  await assert.rejects(() => auth.logout(), /storage failure/);
});
