const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require('typescript');
Module._extensions['.ts'] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename, compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
  }).outputText, filename);
};
const {requestApiV4} = require('../src/api/backendV4/httpCore.ts');
const {createAuthV4, makeMemoryAuthVault} = require('../src/api/backendV4/authCore.ts');
const base = 'https://example.invalid/api/v1';
const session = {accessToken:'old-access',refreshToken:'old-refresh',role:'WORKER',loginId:'worker-a'};
const json = data => new Response(JSON.stringify({data}), {status:200});
const unauthorized = () => new Response(JSON.stringify({error:{code:'AUTH_EXPIRED',message:'expired'}}),{status:401});
const never = () => new Promise(() => {});

test('request timeout bounds a stalled connection even if the transport does not settle on abort', async () => {
  let signal;
  await assert.rejects(requestApiV4(base,{path:'/inspections',timeoutMs:10,fetchImpl:(_url,opts)=>{signal=opts.signal;return never();}}),
    e=>e.code==='REQUEST_TIMEOUT');
  assert.equal(signal.aborted,true);
});
test('request timeout includes a stalled response body, not just headers', async () => {
  await assert.rejects(requestApiV4(base,{path:'/inspections',timeoutMs:10,fetchImpl:async()=>({headers:new Headers(),status:200,ok:true,text:never})}),
    e=>e.code==='REQUEST_TIMEOUT');
});
test('timed out write is sent once and is not automatically refreshed or retried', async () => {
  const vault=makeMemoryAuthVault();await vault.write(session);
  let calls=0;
  const auth=createAuthV4({baseUrl:base,vault,timeoutMs:10,refreshBody:t=>({refreshToken:t}),fetchImpl:()=>{calls++;return never();}});
  await assert.rejects(auth.authorizedRequest('/inspections/confirm',{method:'POST'}),e=>e.code==='REQUEST_TIMEOUT'&&/저장 여부/.test(e.message));
  assert.equal(calls,1);
});
test('external cancellation aborts transport and is not reported as a timeout',async()=>{
  const controller=new AbortController();let signal;
  const pending=requestApiV4(base,{path:'/inspections',signal:controller.signal,fetchImpl:(_u,o)=>{signal=o.signal;return never();}});
  controller.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(signal.aborted,true);
  let calls=0;await assert.rejects(requestApiV4(base,{path:'/inspections',signal:controller.signal,fetchImpl:()=>{calls++;return never();}}),{name:'AbortError'});
  assert.equal(calls,0);
});
test('refresh changing login ID or role clears the old session without retrying its write',async()=>{
  for(const mismatch of [{loginId:'worker-b'},{role:'ADMIN'}]){
    const vault=makeMemoryAuthVault();await vault.write(session);const calls=[];
    const auth=createAuthV4({baseUrl:base,vault,refreshBody:t=>({refreshToken:t}),fetchImpl:async(url,opts)=>{
      calls.push([url,opts.method]);return url.endsWith('/auth/refresh')?json({...session,accessToken:'new-access',...mismatch}):unauthorized();
    }});
    await assert.rejects(auth.authorizedRequest('/inspections/confirm',{method:'POST'}),e=>e.httpStatus===401);
    assert.equal(calls.length,2);assert.equal(await vault.read(),null);assert.equal((await auth.restore()).signedIn,false);
  }
});
test('a matching refresh retries exactly once with the refreshed access token',async()=>{
  const vault=makeMemoryAuthVault();await vault.write(session);const calls=[];
  const auth=createAuthV4({baseUrl:base,vault,refreshBody:t=>({refreshToken:t}),fetchImpl:async(url,opts)=>{
    calls.push([url,opts.headers.Authorization]);return url.endsWith('/auth/refresh')?json({accessToken:'new-access',refreshToken:'new-refresh'}):opts.headers.Authorization==='Bearer old-access'?unauthorized():json('ok');
  }});
  assert.equal(await auth.authorizedRequest('/inspections'),'ok');assert.equal(calls.length,3);assert.equal(calls[2][1],'Bearer new-access');
});
