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

test('저장 정보 읽기에 실패해도 기기 세션 삭제 결과를 정확히 반환한다', async () => {
  let cleared = false;
  const vault = {
    async read() { throw new Error('cannot read'); },
    async write() {},
    async clear() { cleared = true; },
  };
  const auth = makeAuth(vault, async () => { throw new Error('server should not be called'); });
  assert.deepEqual(await auth.logout(), {remoteRevoked: false});
  assert.equal(cleared, true);
});

test('계정 잠금은 세션을 종료하고 일시적인 갱신 실패는 세션을 유지한다', async () => {
  for (const [status, code, signedIn] of [[423, 'AUTH_ACCOUNT_LOCKED', false], [503, 'TEMPORARY', true]]) {
    const vault = makeMemoryAuthVault();
    await vault.write(token);
    const changes = [];
    const auth = makeAuth(vault, async () => Response.json({error: {code}}, {status}));
    auth.subscribeSessionChange(() => changes.push(auth.sessionEpoch()));
    await assert.rejects(auth.refreshAccessToken(), err => err.code === code);
    assert.equal((await auth.restore()).signedIn, signedIn);
    assert.equal(changes.length, signedIn ? 0 : 1);
  }
});

test('로그인 응답에서 지원하지 않는 모바일 권한은 저장하지 않고 그 요청의 토큰만 폐기한다', async () => {
  for (const role of ['DEVICE', 'UNKNOWN', null]) {
    const vault = makeMemoryAuthVault();
    const revocations = [];
    const writes = [];
    const auth = makeAuth({ ...vault, write: async (s) => { writes.push(s); await vault.write(s); } }, async (url, options) => {
      if (url.endsWith('/auth/login')) {
        return Response.json({ data: {
          accessToken: 'issued-access', refreshToken: 'issued-refresh', user: { loginId: 'machine', role },
        } });
      }
      assert.ok(url.endsWith('/auth/logout'));
      revocations.push([options.headers.Authorization, JSON.parse(options.body).refreshToken]);
      return new Response(null, { status: 204 });
    });
    await assert.rejects(auth.login('machine', 'test'), { name: 'UnsupportedMobileRoleError' });
    assert.deepEqual(writes, []);
    assert.deepEqual(revocations, [['Bearer issued-access', 'issued-refresh']]);
    assert.equal((await auth.restore()).signedIn, false);
  }
});

test('기존 앱에 남은 DEVICE 세션은 복원·네트워크 조회에 쓰지 않고 기기에서 제거한다', async () => {
  const vault = makeMemoryAuthVault();
  const auth = makeAuth(vault, async () => assert.fail('legacy credentials must never reach the network'));
  await vault.write({ ...token, role: 'DEVICE' });
  await assert.rejects(auth.authorizedRequest('/inspections'), err => err.code === 'NOT_LOGGED_IN');
  assert.equal(await vault.read(), null);
  await vault.write({ ...token, role: null });
  assert.equal((await auth.restore()).signedIn, false);
  assert.equal(await vault.read(), null);
});

test('늦은 DEVICE 로그인 응답이 이후에 로그인한 관리자 세션을 제거하지 않는다', async () => {
  const deviceReply = deferred();
  const vault = makeMemoryAuthVault();
  const revoked = [];
  const auth = makeAuth(vault, async (url, options) => {
    if (url.endsWith('/auth/login')) {
      if (JSON.parse(options.body).loginId === 'device') return deviceReply.promise;
      return Response.json({ data: { ...token, user: { role: 'ADMIN', loginId: 'admin' } } });
    }
    revoked.push(JSON.parse(options.body).refreshToken);
    return new Response(null, { status: 204 });
  });
  const old = auth.login('device', 'test');
  await auth.login('admin', 'test');
  deviceReply.resolve(Response.json({ data: { accessToken: 'device-access', refreshToken: 'device-refresh', role: 'DEVICE' } }));
  await assert.rejects(old);
  assert.deepEqual(await auth.restore(), { signedIn: true, role: 'ADMIN', loginId: 'admin' });
  assert.deepEqual(revoked, ['device-refresh']);
});

test('갱신 응답이 DEVICE이거나 명시한 권한을 알 수 없으면 이전 작업자 권한을 재사용하지 않는다', async () => {
  for (const role of ['DEVICE', 'UNRECOGNIZED', null]) {
    const vault = makeMemoryAuthVault();
    await vault.write(token);
    const revocations = [];
    const auth = makeAuth(vault, async (url, options) => {
      if (url.endsWith('/auth/refresh')) {
        return Response.json({ data: { accessToken: 'other-access', refreshToken: 'other-refresh', user: { role } } });
      }
      revocations.push(options.headers.Authorization);
      return new Response(null, { status: 204 });
    });
    await assert.rejects(auth.refreshAccessToken(), { name: 'UnsupportedMobileRoleError' });
    assert.equal((await auth.restore()).signedIn, false);
    assert.deepEqual(revocations, ['Bearer other-access']);
  }
});

test('작업자·관리자 로그인 및 권한 필드가 생략된 갱신은 기존 호환 동작을 유지한다', async () => {
  for (const role of ['WORKER', 'ADMIN']) {
    const vault = makeMemoryAuthVault();
    const auth = makeAuth(vault, async (url) => {
      if (url.endsWith('/auth/login')) return Response.json({ data: { ...token, user: { role, loginId: 'person' } } });
      return Response.json({ data: { accessToken: 'updated' } });
    });
    assert.deepEqual(await auth.login('person', 'test'), { signedIn: true, role, loginId: 'person' });
    await auth.refreshAccessToken();
    assert.deepEqual(await auth.restore(), { signedIn: true, role, loginId: 'person' });
    assert.equal((await vault.read()).accessToken, 'updated');
  }
});
