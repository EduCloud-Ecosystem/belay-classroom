// SPDX-License-Identifier: AGPL-3.0-only
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const {webcrypto,createHash}=require('node:crypto');
const nonce='a'.repeat(64),origin='https://notebook.invalid',source="print('synthetic snapshot')\n";
function setup(change={},demo={source,expires_at:Date.now()/1000+300}) {
  const states=[],messages=[],handlers={};
  const opener={postMessage:(value,target)=>messages.push({value,target})};
  const window={location:{href:origin+'/belay/#belay-notebook='+nonce},opener,
    BELAY_SESSION_PROXY:true,BELAY_NOTEBOOK_CONTEXT:{version:1,origin},crypto:webcrypto,
    addEventListener:(name,handler)=>handlers[name]=handler,...change};
  const ctx=vm.createContext({window,URL,TextEncoder,Uint8Array,Date});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../notebook-context.js'),'utf8'),ctx);
  let capture=true;
  window.BelayNotebookContext.mount({demo,onState:value=>states.push(value),canCapture:()=>capture});
  const data={type:'belay-notebook-snapshot',version:1,nonce,source,dirty:true};
  return {window,opener,states,messages,handlers,data,lock:()=>capture=false,
    send:async(value=data,extra={})=>handlers.message?.({origin,source:opener,data:value,...extra})};
}
test('strict ready handshake and captured source hash/unsaved preview; no network or storage interface',async()=>{
  const env=setup();
  assert.deepEqual(JSON.parse(JSON.stringify(env.messages)),[{value:{type:'belay-notebook-ready',version:1,nonce},target:origin}]);
  await env.send();
  const state=env.states.at(-1);
  assert.equal(state.valid,true);assert.equal(state.source,source);assert.equal(state.dirty,true);
  assert.equal(state.sha256,createHash('sha256').update(source).digest('hex'));
  assert.match(state.message,/Unsaved.*does not save or submit/);
  await env.send({...env.data,dirty:false});
  assert.match(env.states.at(-1).message,/reports no unsaved changes/);
});
test('foreign origins/windows and wrong nonce cannot import or change existing capture',async()=>{
  const env=setup();
  for(const extra of [{origin:'https://attacker.invalid'},{source:{}},{data:{...env.data,nonce:'b'.repeat(64)}}]) await env.send(env.data,extra);
  assert.equal(env.states.at(-1).valid,false);
  await env.send();const state=env.states.at(-1);
  await env.send({...env.data,nonce:'b'.repeat(64)});assert.equal(env.states.at(-1),state);
});
test('malformed, extra identity fields, oversized UTF-8 and unapproved source invalidate capture',async()=>{
  for(const data of [{dirty:'true'}, {learner_id:'edu:1'}, {source:'different'}, {version:2}, {source:'é'.repeat(4097)}]) {
    const env=setup();await env.send();await env.send({...env.data,...data});
    assert.equal(env.states.at(-1).valid,false);assert.equal(env.states.at(-1).source,undefined);
  }
});
test('missing opener, nonce, finite demo or trusted origin/configuration fails closed',()=>{
  for(const change of [{opener:null},{location:{href:origin+'/belay/'}},
    {location:{href:origin+'/belay/#belay-notebook=bad'}},{BELAY_NOTEBOOK_CONTEXT:{version:1,origin:'https://other.invalid'}},
    {BELAY_NOTEBOOK_CONTEXT:{version:1,origin,extra:true}},{BELAY_SESSION_PROXY:false},{crypto:{}}]) {
    const env=setup(change);assert.equal(env.messages.length,0);assert.equal(env.states.at(-1).valid,false);
  }
});
test('in-flight/completed lock refuses new captures without changing original preview',async()=>{
  const env=setup();await env.send();const state=env.states.at(-1);env.lock();
  await env.send({...env.data,source:'different'});assert.equal(env.states.at(-1),state);
});
test('expired/missing live demo, hash failure and identity changes never retain a valid snapshot',async()=>{
  for(const demo of [null,{source,expires_at:NaN},{source,expires_at:Date.now()/1000-1}]) {
    const env=setup({},demo);assert.equal(env.messages.length,0);assert.equal(env.states.at(-1).valid,false);
  }
  const unavailable=setup({crypto:{subtle:{digest:async()=>{throw Error('unavailable');}}}});
  await unavailable.send();assert.equal(unavailable.states.at(-1).valid,false);
  const env=setup();await env.send();env.handlers['belay-auth-changed']();
  assert.equal(env.states.at(-1).valid,false);assert.equal(env.states.at(-1).source,undefined);
});
