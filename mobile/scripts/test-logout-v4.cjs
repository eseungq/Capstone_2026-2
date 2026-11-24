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

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}

for (const status of [200, 401]) {
  test('계정 전환 전 시작한 조회의 응답과 재시도를 폐기한다: HTTP ' + status, async () => {
    const firstRead = deferred();
    const response = deferred();
    let reads = 0;
    const vault = makeMemoryAuthVault();
    await vault.write(token);
    const auth = makeAuth(vault, async url => {
      if (url.endsWith('/auth/login')) {
        return Response.json({data: {...token, loginId: 'second', accessToken: 'new-access'}});
      }
      reads++;
      firstRead.resolve();
      return response.promise;
    });
    const oldRead = auth.authorizedRequest('/inspections');
    await firstRead.promise;
    await auth.login('second', 'test-only');
    response.resolve(status === 200 ? Response.json({data: []}) : new Response(null, {status}));
    await assert.rejects(oldRead, err => err.code === 'SESSION_CHANGED');
    assert.equal(reads, 1);
    assert.equal((await auth.restore()).loginId, 'second');
  });
}

test('서버 응답 전에 로컬 로그아웃을 알리고 다음 로그인 세션을 보존한다', async () => {
  const reachedServer = deferred();
  const remote = deferred();
  const vault = makeMemoryAuthVault();
  await vault.write(token);
  const auth = makeAuth(vault, async url => {
    if (url.endsWith('/auth/logout')) { reachedServer.resolve(); return remote.promise; }
    if (url.endsWith('/auth/login')) return Response.json({data: {...token, loginId: 'next'}});
    throw new Error('unexpected request');
  });
  const seen = [];
  const off = auth.subscribeSessionChange(() => seen.push(auth.sessionEpoch()));
  const logout = auth.logout();
  await reachedServer.promise;
  assert.equal((await auth.restore()).signedIn, false);
  assert.equal(seen.length, 1);
  await auth.login('next', 'test-only');
  remote.resolve(new Response(null, {status: 204}));
  assert.deepEqual(await logout, {remoteRevoked: true});
  assert.equal((await auth.restore()).loginId, 'next');
  assert.equal(seen.length, 2);
  off();
});

test('같은 세션의 동시 조회는 토큰을 한 번만 갱신한다', async () => {
  const firstRefresh = deferred();
  const refresh = deferred();
  const vault = makeMemoryAuthVault();
  await vault.write(token);
  let refreshCount = 0;
  const auth = makeAuth(vault, async (url, options) => {
    if (url.endsWith('/auth/refresh')) {
      refreshCount++;
      firstRefresh.resolve();
      return refresh.promise;
    }
    return options.headers.Authorization === 'Bearer renewed'
      ? Response.json({data: 'ok'}) : new Response(null, {status: 401});
  });
  const pending = Promise.all([auth.authorizedRequest('/a'), auth.authorizedRequest('/b')]);
  await firstRefresh.promise;
  refresh.resolve(Response.json({data: {...token, accessToken: 'renewed'}}));
  assert.deepEqual(await pending, ['ok', 'ok']);
  assert.equal(refreshCount, 1);
});
