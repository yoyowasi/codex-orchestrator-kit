import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import {normalizeOwned,scopesOverlap,TeamControl,parseModels,teamModels,modelSettings,coordinatorModel,
  coordinatorInstructions,teamTools,flagValue,startOptions,Rpc,TeamLink,DEFAULT_TEAM_MODELS,serveMcp} from './codex-team.mjs';
import {PassThrough} from 'node:stream';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

// Keep the tests independent of the caller's launcher configuration.
delete process.env.CODEX_TEAM_MODELS;
delete process.env.CODEX_TEAM_COORDINATOR_MODEL;

// A temporary directory that is removed when the test ends.
function tempDir(t,prefix){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),prefix));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  return dir;
}

test('file ownership rejects escapes and distinguishes siblings',()=>{
  const root=path.join(os.tmpdir(),'codex-team-scope-test');
  assert.deepEqual(normalizeOwned(root,['src/pages','src/pages/']),['src/pages']);
  assert.throws(()=>normalizeOwned(root,['../other']));
  assert.throws(()=>normalizeOwned(root,['.']));
  assert.throws(()=>normalizeOwned(root,['src/*']));
  assert.equal(scopesOverlap('src','src/pages'),true);
  assert.equal(scopesOverlap('src/pages','src/pages-other'),false);
});

test('dispatcher refuses conflicting writes before starting a worker turn',async t=>{
  const dir=tempDir(t,'codex-team-unit-');
  const manifest=path.join(dir,'team.json');
  fs.writeFileSync(manifest,JSON.stringify({project:dir,members:{
    frontend_developer:{role:'frontend_developer',threadId:'front',ownedPaths:[]},
    backend_developer:{role:'backend_developer',threadId:'back',ownedPaths:['src/shared']}
  }}));
  let starts=0;
  const rpc={call:async(method,p)=>{
    if(method==='turn/start'){starts++;return {turn:{id:'new',status:'inProgress'}};}
    return {thread:{status:{type:p.threadId==='back'?'active':'idle'},turns:[]}};
  }};
  const ctl=new TeamControl(manifest,rpc);
  await assert.rejects(()=>ctl.dispatch({role:'frontend_developer',task:'Change shared file',owned_paths:['src/shared/types.ts']}),/ownership conflict/);
  assert.equal(starts,0);
});

test('read-only dispatch sends a readOnly policy and no write reservation',async t=>{
  const dir=tempDir(t,'codex-team-unit-');
  const manifest=path.join(dir,'team.json');
  fs.writeFileSync(manifest,JSON.stringify({project:dir,members:{reviewer:{role:'reviewer',threadId:'review',readOnly:true}}}));
  let started;
  const rpc={call:async(method,p)=>{
    if(method==='turn/start'){started=p;return {turn:{id:'r1',status:'inProgress'}};}
    return {thread:{status:{type:'idle'},turns:[]}};
  }};
  await new TeamControl(manifest,rpc).dispatch({role:'reviewer',task:'Review'});
  assert.equal(started.sandboxPolicy.type,'readOnly');
  assert.equal(started.model,'gpt-6-sol');
  assert.equal(started.effort,'medium');
  assert.deepEqual(JSON.parse(fs.readFileSync(manifest)).members.reviewer.ownedPaths,[]);
});

test('same worker can use Astra for analysis and Sol for a later simple task',async t=>{
  const dir=tempDir(t,'codex-team-routing-');
  const manifest=path.join(dir,'team.json');
  fs.writeFileSync(manifest,JSON.stringify({project:dir,members:{backend_developer:{role:'backend_developer',threadId:'back'}}}));
  const starts=[];
  const rpc={call:async(method,p)=>{
    if(method==='turn/start'){starts.push(p);return {turn:{id:`t${starts.length}`,status:'completed'}};}
    return {thread:{status:{type:'idle'},turns:[]}};
  }};
  const ctl=new TeamControl(manifest,rpc);
  await ctl.dispatch({role:'backend_developer',task:'Diagnose race condition',read_only:true,model:'gpt-6-astra',model_reason:'concurrency root-cause analysis'});
  await ctl.dispatch({role:'backend_developer',task:'Implement agreed fix',owned_paths:['src/api'],model:'gpt-6-sol',model_reason:'fix with a known cause'});
  assert.deepEqual(starts.map(p=>[p.model,p.effort]),[['gpt-6-astra','high'],['gpt-6-sol','medium']]);
  const state=JSON.parse(fs.readFileSync(manifest)).members.backend_developer;
  assert.equal(state.model,'gpt-6-sol');
  assert.equal(state.reasoningEffort,'medium');
  assert.equal(state.modelReason,'fix with a known cause');
  await assert.rejects(()=>ctl.dispatch({role:'backend_developer',task:'x',read_only:true,model:'not-a-model'}),/Team model must be one of: gpt-6-sol\/medium, gpt-6-astra\/high/);
  assert.equal(starts.length,2);
});

test('team models parse model:effort lists in order',()=>{
  assert.deepEqual(parseModels(DEFAULT_TEAM_MODELS),[{model:'gpt-6-sol',effort:'medium'},{model:'gpt-6-astra',effort:'high'}]);
  assert.deepEqual(parseModels(' fast-model : low , deep-model:xhigh '),[{model:'fast-model',effort:'low'},{model:'deep-model',effort:'xhigh'}]);
  assert.deepEqual(parseModels('only-model:medium'),[{model:'only-model',effort:'medium'}]);
  for(const bad of ['','  ','gpt-6-sol','gpt-6-sol:','gpt-6-sol:medium,','a:low,,b:high','a b:low','a:low,a:high'])
    assert.throws(()=>parseModels(bad),undefined,bad);
});

test('flag or environment configures team models; unset keeps the defaults',()=>{
  assert.deepEqual(teamModels(),parseModels(DEFAULT_TEAM_MODELS));
  assert.deepEqual(teamModels(''),parseModels(DEFAULT_TEAM_MODELS));
  assert.deepEqual(teamModels('m1:low,m2:high'),[{model:'m1',effort:'low'},{model:'m2',effort:'high'}]);
  process.env.CODEX_TEAM_MODELS='env-model:medium';
  try{assert.deepEqual(teamModels(),[{model:'env-model',effort:'medium'}]);}
  finally{delete process.env.CODEX_TEAM_MODELS;}
});

test('first model is the worker default and last is the coordinator default',()=>{
  const models=parseModels('m1:low,m2:medium,m3:high');
  assert.deepEqual(modelSettings(undefined,models),{model:'m1',effort:'low'});
  assert.deepEqual(modelSettings('m2',models),{model:'m2',effort:'medium'});
  assert.throws(()=>modelSettings('gpt-6-sol',models),/m1\/low, m2\/medium, m3\/high/);
  assert.deepEqual(modelSettings(),{model:'gpt-6-sol',effort:'medium'});
  assert.deepEqual(coordinatorModel(models,undefined),{model:'m3',effort:'high'});
  assert.deepEqual(coordinatorModel(models,'m2'),{model:'m2',effort:'medium'});
  assert.deepEqual(coordinatorModel(models,'lead-model:xhigh'),{model:'lead-model',effort:'xhigh'});
  assert.throws(()=>coordinatorModel(models,'unknown'),/Team model must be one of/);
  assert.throws(()=>coordinatorModel(models,'a:low,b:high'),/one model/);
  assert.deepEqual(coordinatorModel(parseModels(DEFAULT_TEAM_MODELS),''),{model:'gpt-6-astra',effort:'high'});
});

test('dispatch, tools and coordinator prompt follow the team model configuration',async t=>{
  const dir=tempDir(t,'codex-team-models-');
  const manifest=path.join(dir,'team.json');
  const models=parseModels('m1:low,m2:high');
  fs.writeFileSync(manifest,JSON.stringify({project:dir,models,members:{reviewer:{role:'reviewer',threadId:'review',readOnly:true}}}));
  const starts=[];
  const rpc={call:async(method,p)=>{
    if(method==='turn/start'){starts.push(p);return {turn:{id:`t${starts.length}`,status:'completed'}};}
    return {thread:{status:{type:'idle'},turns:[]}};
  }};
  const ctl=new TeamControl(manifest,rpc);
  await ctl.dispatch({role:'reviewer',task:'Review'});
  await ctl.dispatch({role:'reviewer',task:'Deep review',model:'m2',model_reason:'hard'});
  await assert.rejects(()=>ctl.dispatch({role:'reviewer',task:'x',model:'gpt-6-astra'}),/m1\/low, m2\/high/);
  assert.deepEqual(starts.map(p=>[p.model,p.effort]),[['m1','low'],['m2','high']]);
  const dispatch=teamTools(ctl.models()).find(tool=>tool.name==='team_dispatch');
  assert.deepEqual(dispatch.inputSchema.properties.model.enum,['m1','m2']);
  const prompt=coordinatorInstructions({developer_instructions:'base'},{project:dir,members:{reviewer:{}},models});
  assert.match(prompt,/m1\/low, m2\/high/);
  assert.doesNotMatch(prompt,/gpt-6/);
});

test('flags need a value that is not another flag',()=>{
  assert.equal(flagValue(['start','.'],'--roles','a,b'),undefined);
  assert.equal(flagValue(['--roles','a,b'],'--roles','a,b'),'a,b');
  for(const args of [['--roles'],['--roles',''],['--roles','--headless']])
    assert.throws(()=>flagValue(args,'--roles','a,b'),/--roles needs a value such as a,b/);
});

test('start takes the project only from a leading non-flag argument',()=>{
  const cwd=path.join(os.tmpdir(),'codex-team-cwd');
  assert.deepEqual(startOptions([],cwd),{project:cwd,roles:['frontend_developer','backend_developer','qa_engineer'],windows:true,models:undefined});
  assert.equal(startOptions(['C:\\work\\app','--headless'],cwd).project,'C:\\work\\app');
  const headless=startOptions(['--headless','--roles','researcher,reviewer'],cwd);
  assert.equal(headless.project,cwd);
  assert.equal(headless.windows,false);
  assert.deepEqual(headless.roles,['researcher','reviewer']);
  assert.equal(startOptions(['--models','m1:low'],cwd).models,'m1:low');
  assert.equal(startOptions(['app','--roles','a,b','--models','m1:low','--headless'],cwd).project,'app');
  for(const args of [['--headless','C:\\app'],['app','other'],['--roles','a,b','app']])
    assert.throws(()=>startOptions(args,cwd),/Put the project path first/,args.join(' '));
});

test('an unknown command prints help and exits non-zero',()=>{
  const cli=path.join(path.dirname(fileURLToPath(import.meta.url)),'codex-team.mjs');
  const typo=spawnSync(process.execPath,[cli,'strt'],{encoding:'utf8'});
  assert.equal(typo.status,1);
  assert.match(typo.stderr,/Unknown command: strt/);
  assert.match(typo.stdout,/codex-team start/);
  const help=spawnSync(process.execPath,[cli,'help'],{encoding:'utf8'});
  assert.equal(help.status,0);
  assert.equal(help.stderr,'');
});

test('a timed-out turn/start keeps its file scope reserved; a refused one releases it',async t=>{
  const dir=tempDir(t,'codex-team-reserve-');
  const manifest=path.join(dir,'team.json');
  const members=()=>({frontend_developer:{role:'frontend_developer',threadId:'front',ownedPaths:[]},
    backend_developer:{role:'backend_developer',threadId:'back',ownedPaths:[]}});
  for(const [name,failure,reserved] of [
    ['timeout',new Error('turn/start: no response in time.'),['src']],
    ['refused',Object.assign(new Error('{"code":-1}'),{rpcError:{code:-1}}),[]],
    ['not sent',Object.assign(new Error('The local server connection is closed.'),{notSent:true}),[]]]){
    await t.test(name,async()=>{
      fs.writeFileSync(manifest,JSON.stringify({project:dir,members:members()}));
      let frontStarted=false;
      const rpc={call:async(method,p)=>{
        if(method==='turn/start'){
          if(p.threadId==='front'){
            // The overlap check must already see the scope while the request is in flight.
            assert.deepEqual(JSON.parse(fs.readFileSync(manifest)).members.frontend_developer.ownedPaths,['src']);
            frontStarted=!failure.rpcError&&!failure.notSent;throw failure;
          }
          return {turn:{id:'b1',status:'inProgress'}};
        }
        // A timed-out request may still have started the turn.
        return {thread:{status:{type:p.threadId==='front'&&frontStarted?'active':'idle'},turns:[]}};
      }};
      const ctl=new TeamControl(manifest,rpc);
      await assert.rejects(()=>ctl.dispatch({role:'frontend_developer',task:'Change src',owned_paths:['src']}));
      assert.deepEqual(JSON.parse(fs.readFileSync(manifest)).members.frontend_developer.ownedPaths,reserved);
      const second=ctl.dispatch({role:'backend_developer',task:'Change src/x',owned_paths:['src/x']});
      if(name==='timeout')await assert.rejects(()=>second,/ownership conflict/);
      else assert.equal((await second).turnId,'b1');
    });
  }
});

test('a call on a closed connection fails at once without sending',async()=>{
  const rpc=new Rpc('ws://127.0.0.1:9');
  let sent=false;
  rpc.ws={readyState:WebSocket.CLOSED,send:()=>{sent=true;},close(){}};
  const started=Date.now();
  await assert.rejects(()=>rpc.call('thread/read',{},20000),error=>error.notSent===true&&/closed/.test(error.message));
  assert.ok(Date.now()-started<1000);
  assert.equal(sent,false);
  assert.equal(rpc.pending.size,0);
});

test('the team link reopens a dropped connection once, and does not retry the failed call',async()=>{
  const opened=[];
  const link=new TeamLink(async()=>{
    const rpc={closed:false,calls:[],close(){this.closed=true;},
      call:async function(method){this.calls.push(method);if(method==='fail')throw new Error('lost');return method;}};
    opened.push(rpc);return rpc;
  });
  assert.equal(await link.call('a'),'a');
  await assert.rejects(()=>link.call('fail'),/lost/);
  opened[0].closed=true;
  // Concurrent calls after a drop share one reconnection.
  assert.deepEqual(await Promise.all([link.call('b'),link.call('c')]),['b','c']);
  assert.equal(opened.length,2);
  assert.deepEqual(opened[0].calls,['a','fail']);
  assert.deepEqual(opened[1].calls,['b','c']);
});

// A manifest with the given thread ids, and a fake clock: sleeping advances it instantly.
function waitFixture(t,roles){
  const dir=tempDir(t,'codex-team-wait-');
  const manifest=path.join(dir,'team.json');
  fs.writeFileSync(manifest,JSON.stringify({project:dir,members:Object.fromEntries(roles.map(r=>[r,{role:r,threadId:r}]))}));
  const clock={t:0,sleeps:0};
  const opts={now:()=>clock.t,sleep:async ms=>{if(++clock.sleeps>200)throw new Error('wait never ended');clock.t+=ms;}};
  return {dir,manifest,clock,opts};
}
const thread=(type,turnStatus='inProgress',activeFlags)=>({thread:{status:{type,...(activeFlags?{activeFlags}:{})},turns:turnStatus?[{id:'t1',status:turnStatus,items:[]}]:[]}});

test('team_wait with a non-numeric seconds falls back to 30 and still times out',async t=>{
  const {manifest,clock,opts}=waitFixture(t,['a']);
  const ctl=new TeamControl(manifest,{call:async()=>thread('active')},opts);
  for(const bad of ['abc',NaN,{},undefined]){
    clock.t=0;clock.sleeps=0;
    const r=await ctl.wait({seconds:bad});
    assert.equal(r.timedOut,true);
    assert.equal(clock.t,30000);
  }
  clock.t=0;
  await ctl.wait({seconds:500});
  assert.equal(clock.t,45000);
});

test('team_wait ignores a worker that was already waiting and reports it',async t=>{
  const {manifest,clock,opts}=waitFixture(t,['a','b']);
  let reads=0;
  const rpc={call:async(m,p)=>{
    if(p.threadId==='a')return thread('active','inProgress',['waitingOnApproval']);
    reads++;
    return reads>3?thread('idle','completed'):thread('active');
  }};
  const r=await new TeamControl(manifest,rpc,opts).wait({});
  assert.ok(reads>3);
  assert.equal(r.timedOut,false);
  assert.deepEqual(r.waiting,['a']);
  assert.equal(r.needsInput,true);
  assert.ok(clock.t>=6000);
});

test('team_wait returns at once when a worker starts waiting during the call',async t=>{
  const {manifest,opts}=waitFixture(t,['a','b']);
  let reads=0;
  const rpc={call:async(m,p)=>{
    if(p.threadId==='a')return thread('active');
    return ++reads>2?thread('active','inProgress',['waitingOnUserInput']):thread('active');
  }};
  const r=await new TeamControl(manifest,rpc,opts).wait({});
  assert.deepEqual(r.waiting,['b']);
  assert.equal(r.needsInput,true);
  assert.equal(r.timedOut,false);
});

test('team_wait bounds every read by the time left and stays under 60 seconds',async t=>{
  const {manifest,clock,opts}=waitFixture(t,['a']);
  const rpc={call:async(m,p,timeout)=>{
    assert.ok(Number.isFinite(timeout)&&timeout<=30000,`timeout ${timeout}`);
    assert.ok(clock.t+timeout<=55000,'read may outlast the budget');
    clock.t+=Math.min(20000,timeout);
    return thread('active');
  }};
  await new TeamControl(manifest,rpc,opts).wait({seconds:45});
  assert.ok(clock.t<60000,`took ${clock.t}`);
});

test('a notLoaded thread is not running even when its last turn is inProgress',async t=>{
  const {manifest,opts}=waitFixture(t,['a','b']);
  const calls=[];
  const rpc={call:async(m,p)=>{
    calls.push(m);
    if(m==='turn/start')return {turn:{id:'n1',status:'inProgress'}};
    return thread(p.threadId==='b'?'notLoaded':'idle','inProgress');
  }};
  const ctl=new TeamControl(manifest,rpc,opts);
  assert.equal((await ctl.wait({roles:['b']})).timedOut,false);
  assert.deepEqual(await ctl.interrupt({role:'b'}),{role:'b',status:'not_running'});
  assert.equal((await ctl.dispatch({role:'b',task:'Review',read_only:true})).turnId,'n1');
  assert.ok(calls.includes('thread/resume'));
  assert.ok(!calls.includes('turn/interrupt'));
});

test('a notLoaded worker with a stale inProgress turn does not block an overlapping dispatch',async t=>{
  const {manifest,opts}=waitFixture(t,['a','b']);
  const team=JSON.parse(fs.readFileSync(manifest));team.members.b.ownedPaths=['src'];
  fs.writeFileSync(manifest,JSON.stringify(team));
  const rpc={call:async(m,p)=>m==='turn/start'?{turn:{id:'n1',status:'inProgress'}}:thread(p.threadId==='b'?'notLoaded':'idle',p.threadId==='b'?'inProgress':'completed')};
  assert.equal((await new TeamControl(manifest,rpc,opts).dispatch({role:'a',task:'x',owned_paths:['src/x']})).turnId,'n1');
});

// Runs lines through serveMcp and returns the parsed replies.
async function mcpRun(control,lines){
  const input=new PassThrough(), output=new PassThrough();
  let text='';output.on('data',d=>{text+=d;});
  const done=serveMcp(control,input,output);
  for(const l of lines)input.write(l+'\n');
  input.end();await done;
  return text.split('\n').filter(Boolean).map(l=>JSON.parse(l));
}

test('the MCP loop answers malformed input with JSON-RPC errors',async()=>{
  const replies=await mcpRun({models:()=>[]},['{not json','[{"jsonrpc":"2.0","id":1,"method":"ping"}]','{"jsonrpc":"2.0","id":7}','{"jsonrpc":"2.0","id":2,"method":"ping"}']);
  assert.deepEqual(replies.map(r=>[r.id,r.error?.code??null]),[[null,-32700],[null,-32600],[7,-32600],[2,null]]);
});

test('a long team_wait does not block ping, and dispatches never interleave',async()=>{
  const events=[];
  let release;const gate=new Promise(r=>{release=r;});
  const control={
    models:()=>[],
    wait:async()=>{await gate;return {done:true};},
    dispatch:async({role})=>{events.push(`start ${role}`);await new Promise(r=>setTimeout(r,20));events.push(`end ${role}`);return {role};},
    interrupt:async({role})=>{events.push(`start int ${role}`);await new Promise(r=>setTimeout(r,5));events.push(`end int ${role}`);return {role};}
  };
  const call=(id,name,args)=>JSON.stringify({jsonrpc:'2.0',id,method:'tools/call',params:{name,arguments:args}});
  const input=new PassThrough(), output=new PassThrough();
  const got=[];output.on('data',d=>{for(const l of String(d).split('\n').filter(Boolean))got.push(JSON.parse(l));});
  const done=serveMcp(control,input,output);
  input.write(call(1,'team_wait',{})+'\n');
  input.write('{"jsonrpc":"2.0","id":2,"method":"ping"}\n');
  input.write(call(3,'team_dispatch',{role:'a'})+'\n');
  input.write(call(4,'team_dispatch',{role:'b'})+'\n');
  input.write(call(5,'team_interrupt',{role:'c'})+'\n');
  await new Promise(r=>setTimeout(r,150));
  assert.ok(got.some(r=>r.id===2),'ping answered while team_wait runs');
  assert.ok(!got.some(r=>r.id===1));
  release();input.end();await done;
  assert.deepEqual(events,['start a','end a','start b','end b','start int c','end int c']);
  const text=id=>JSON.parse(got.find(r=>r.id===id).result.content[0].text);
  assert.deepEqual([text(1).done,text(3).role,text(4).role,text(5).role],[true,'a','b','c']);
});

test('owned_paths reject Windows path aliases and canonicalize junctions',{skip:process.platform!=='win32'},t=>{
  const root=fs.realpathSync.native(tempDir(t,'codex-team-alias-'));
  const project=path.join(root,'proj'), outside=path.join(root,'outside');
  fs.mkdirSync(path.join(project,'real'),{recursive:true});fs.mkdirSync(outside);
  assert.deepEqual(normalizeOwned(project,['src.','src ','SRC\\']),['src']);
  assert.deepEqual(normalizeOwned(project,['a. /b.']),['a/b']);
  for(const bad of ['src::$DATA','a:b/c','src/..  ','. .','.. /x'])
    assert.throws(()=>normalizeOwned(project,[bad]),undefined,bad);
  fs.symlinkSync(outside,path.join(project,'escape'),'junction');
  fs.symlinkSync(path.join(project,'real'),path.join(project,'alias'),'junction');
  assert.throws(()=>normalizeOwned(project,['escape/x']),/outside/);
  assert.throws(()=>normalizeOwned(project,['escape']),/outside/);
  assert.deepEqual(normalizeOwned(project,['alias/x']),['real/x']);
});

test('dispatch re-reads the manifest and keeps another member\'s concurrent update',async t=>{
  const dir=tempDir(t,'codex-team-merge-');
  const manifest=path.join(dir,'team.json');
  fs.writeFileSync(manifest,JSON.stringify({project:dir,members:{a:{role:'a',threadId:'a',readOnly:true},b:{role:'b',threadId:'b',lastTurnId:'old'}}}));
  const rpc={call:async(m)=>{
    if(m==='turn/start'){
      // Another process updates member b while this turn starts.
      const other=JSON.parse(fs.readFileSync(manifest));other.members.b.lastTurnId='newer';fs.writeFileSync(manifest,JSON.stringify(other));
      return {turn:{id:'a1',status:'inProgress'}};
    }
    return thread('idle','completed');
  }};
  await new TeamControl(manifest,rpc).dispatch({role:'a',task:'Review'});
  const saved=JSON.parse(fs.readFileSync(manifest)).members;
  assert.equal(saved.b.lastTurnId,'newer');
  assert.equal(saved.a.lastTurnId,'a1');
});
