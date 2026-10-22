// SPDX-License-Identifier: AGPL-3.0-only
// Offline DOM fixtures; browser/layout/accessibility acceptance remains separate.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag) { this.tag=tag; this.children=[]; this.listeners={}; this.text=''; }
  set textContent(value) { this.text=value; this.children=[]; }
  get textContent() { return this.text + this.children.map(x=>x.textContent).join(' '); }
  setAttribute(name,value) { this[name]=value; }
  replaceChildren(...items) { this.text=''; this.children=items; }
  appendChild(item) { this.children.push(item); }
  querySelectorAll(tag) { return this.children.flatMap(x=>[...(x.tag===tag?[x]:[]), ...x.querySelectorAll(tag)]); }
  addEventListener(name,fn) { this.listeners[name]=fn; }
  async click() { await this.listeners.click?.(); }
}
function setup() {
  const calls=[], container=new Element('section');
  let serial=0, retries=0;
  let context={exercise_id:'info511-lab3-q4-synthetic',exercise_version:'info511-lab3-q4-synthetic-v1',learner_id:'edu:1'};
  let state={monitor:'off',checkpoint:false,declaration:null,revision:0,notice:'Private tracking notice',notice_version:'info511-private-guidance-v1',alerts:{},guidance:{hints_only:'Hints only'}};
  let delay=null, failNext=false;
  const window={BelayAuth:{headers:async()=>({Authorization:'Bearer synthetic'})}};
  const fetch=async(url,options)=>{
    calls.push({url,options});
    const captured=JSON.parse(JSON.stringify(state)), fail=failNext; failNext=false;
    if(delay) await delay;
    if(fail) throw new Error("synthetic lost response");
    if(options.body) {
      const body=JSON.parse(options.body);
      assert.equal(body.expected_revision,state.revision);
      state={...state,revision:state.revision+1};
      if(body.action==='enable') state.monitor='active';
      if(body.action==='checkpoint') state.checkpoint=true;
      if(body.action==='revoke') state={...state,monitor:'revoked',alerts:{}};
    }
    return {ok:true,json:async()=>options.body ? state : captured};
  };
  const sandbox={window,document:{createElement:tag=>new Element(tag)},fetch,crypto:{randomUUID:()=>String(++serial).padStart(32,'0')}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../classroom-guidance.js'),'utf8'),sandbox);
  const panel=window.BelayClassroom.mount({container,base:()=>'https://belay.invalid',context:()=>context,onRetry:()=>{retries++;}});
  return {panel,container,calls,button:text=>container.querySelectorAll('button').find(x=>x.textContent===text),
    setContext:value=>{context=value;},setState:value=>{state={...state,...value};},setDelay:value=>{delay=value;},failNext:()=>{failNext=true;},retries:()=>retries};
}

test('mount does not opt in or poll; checkpoint works with monitoring off',async()=>{
  const e=setup(); assert.equal(e.calls.length,0);
  await e.panel.refresh();
  assert.match(e.container.textContent,/monitoring: off/);
  await e.button('I wrote my schema and observational-unit prediction').click();
  assert.equal(JSON.parse(e.calls[1].options.body).action,'checkpoint');
  assert.match(e.container.textContent,/Prediction checkpoint recorded/);
  assert.match(e.container.textContent,/monitoring: off/);
  assert.equal(e.calls.length,2);
});

test('NHANES guidance stays private and requires its exact registered assignment version',async()=>{
  const e=setup();
  e.setContext({exercise_id:'info511-nhanes-wrangling',exercise_version:'info511-nhanes-wrangling-v1',learner_id:'edu:2'});
  await e.panel.refresh();
  assert.ok(e.calls[0].url.endsWith('/api/classroom/info511-nhanes-wrangling/info511-nhanes-wrangling-v1'));
  await e.button('I wrote my schema and observational-unit prediction').click();
  assert.equal(JSON.parse(e.calls[1].options.body).action,'checkpoint');
  const before=e.calls.length;
  e.setContext({exercise_id:'info511-nhanes-wrangling',exercise_version:'unknown',learner_id:'edu:2'});
  await e.panel.refresh();
  assert.equal(e.calls.length,before);
  assert.equal(e.container.hidden,true);
});

test('challenge and retry are explicit private actions, not inference',async()=>{
  const e=setup();
  e.setState({monitor:'active',alerts:{['a'.repeat(32)]:{rule:'hints_only',state:'open'}}});
  await e.panel.refresh();
  await e.button('Challenge this alert').click();
  assert.equal(JSON.parse(e.calls[1].options.body).action,'challenge');
  await e.button('I will retry with permitted hints').click();
  assert.equal(e.retries(),1);
  assert.ok(e.calls.every(x=>x.url.includes('/api/classroom/')));
});

test('late private response is discarded after learner context changes',async()=>{
  const e=setup(); let release;
  e.setDelay(new Promise(resolve=>{release=resolve;}));
  const pending=e.panel.refresh();
  await Promise.resolve(); await Promise.resolve();
  e.setContext(null); e.panel.clear(); release(); await pending;
  assert.equal(e.container.hidden,true);
  assert.equal(e.container.textContent.trim(),'Private classroom guidance');
});


for (const outcome of ['old response', 'old error']) {
  test(`late GET ${outcome} cannot replace a successful revoke`,async()=>{
    const e=setup(), alert='a'.repeat(32);
    e.setState({monitor:'active',revision:1,alerts:{[alert]:{rule:'hints_only',state:'open'}}});
    await e.panel.refresh();
    let release;
    e.setDelay(new Promise(resolve=>{release=resolve;}));
    if(outcome==='old error') e.failNext();
    const old=e.panel.refresh();
    for(let i=0;i<10 && e.calls.length<2;i++) await Promise.resolve();
    assert.equal(e.calls.length,2); e.setDelay(null);
    await e.button('Revoke optional tracking and clear its records').click();
    assert.match(e.container.textContent,/monitoring: revoked/);
    release(); await old;
    assert.match(e.container.textContent,/monitoring: revoked/);
    assert.doesNotMatch(e.container.textContent,/Private guidance:/);
    assert.doesNotMatch(e.container.textContent,/guidance unavailable/);
  });
}
