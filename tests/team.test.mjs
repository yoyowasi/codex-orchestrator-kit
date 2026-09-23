import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import {normalizeOwned,scopesOverlap,TeamControl} from '../tools/codex-team/codex-team.mjs';

test('file ownership rejects escapes and distinguishes siblings',()=>{
  const root=path.join(os.tmpdir(),'codex-team-scope-test');
  assert.deepEqual(normalizeOwned(root,['src/pages','src/pages/']),['src/pages']);
  assert.throws(()=>normalizeOwned(root,['../other']));
  assert.throws(()=>normalizeOwned(root,['.']));
  assert.throws(()=>normalizeOwned(root,['src/*']));
  assert.equal(scopesOverlap('src','src/pages'),true);
  assert.equal(scopesOverlap('src/pages','src/pages-other'),false);
});

test('dispatcher refuses conflicting writes before starting a worker turn',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codex-team-unit-'));
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
  await assert.rejects(()=>ctl.dispatch({role:'frontend_developer',task:'Change shared file',owned_paths:['src/shared/types.ts']}),/충돌/);
  assert.equal(starts,0);
});

test('read-only dispatch sends a readOnly policy and no write reservation',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codex-team-unit-'));
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

test('same worker can use Astra for analysis and Sol for a later simple task',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codex-team-routing-'));
  const manifest=path.join(dir,'team.json');
  fs.writeFileSync(manifest,JSON.stringify({project:dir,members:{backend_developer:{role:'backend_developer',threadId:'back'}}}));
  const starts=[];
  const rpc={call:async(method,p)=>{
    if(method==='turn/start'){starts.push(p);return {turn:{id:`t${starts.length}`,status:'completed'}};}
    return {thread:{status:{type:'idle'},turns:[]}};
  }};
  const ctl=new TeamControl(manifest,rpc);
  await ctl.dispatch({role:'backend_developer',task:'Diagnose race condition',read_only:true,model:'gpt-6-astra',model_reason:'동시성 원인 분석'});
  await ctl.dispatch({role:'backend_developer',task:'Implement agreed fix',owned_paths:['src/api'],model:'gpt-6-sol',model_reason:'원인이 밝혀진 수정'});
  assert.deepEqual(starts.map(p=>[p.model,p.effort]),[['gpt-6-astra','high'],['gpt-6-sol','medium']]);
  const state=JSON.parse(fs.readFileSync(manifest)).members.backend_developer;
  assert.equal(state.model,'gpt-6-sol');
  assert.equal(state.reasoningEffort,'medium');
  assert.equal(state.modelReason,'원인이 밝혀진 수정');
  await assert.rejects(()=>ctl.dispatch({role:'backend_developer',task:'x',read_only:true,model:'not-a-model'}),/팀 모델/);
  assert.equal(starts.length,2);
});
