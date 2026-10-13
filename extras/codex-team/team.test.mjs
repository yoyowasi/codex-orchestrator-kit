import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import {normalizeOwned,scopesOverlap,TeamControl,parseModels,teamModels,modelSettings,coordinatorModel,
  coordinatorInstructions,teamTools,flagValue,DEFAULT_TEAM_MODELS} from './codex-team.mjs';

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
