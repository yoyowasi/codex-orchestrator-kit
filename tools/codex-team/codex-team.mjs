import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import crypto from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import readline from 'node:readline';

const FILE = fileURLToPath(import.meta.url);
const DIR = path.dirname(FILE);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const readJson = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const homeDir = () => process.env.CODEX_HOME || path.join(os.homedir(), '.codex');
const python = process.env.CODEX_TEAM_PYTHON || 'py';
const pyArgs = python.toLowerCase().endsWith('py') || python.toLowerCase().endsWith('py.exe') ? ['-3', '-X', 'utf8'] : ['-X', 'utf8'];

function saveJson(file, data) {
  const temp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(data, null, 2), 'utf8');
  fs.renameSync(temp, file);
}

function resolveCodex() {
  const located = spawnSync('where.exe', ['codex.cmd'], {encoding:'utf8', windowsHide:true});
  for (const shim of (located.stdout || '').trim().split(/\r?\n/)) {
    const packageDir=path.join(path.dirname(shim),'node_modules','@openai','codex');
    const arch=process.arch==='arm64'?'arm64':'x64';
    const triple=arch==='arm64'?'aarch64-pc-windows-msvc':'x86_64-pc-windows-msvc';
    const native=path.join(packageDir,'node_modules','@openai',`codex-win32-${arch}`,'vendor',triple,'bin','codex.exe');
    if(fs.existsSync(native))return [native];
    const entry = path.join(packageDir, 'bin', 'codex.js');
    if (fs.existsSync(entry)) return [process.execPath, entry];
  }
  const native = spawnSync('where.exe', ['codex.exe'], {encoding:'utf8', windowsHide:true});
  const exe = (native.stdout || '').trim().split(/\r?\n/)[0];
  if (exe && fs.existsSync(exe)) return [exe];
  throw new Error('Codex CLI를 찾을 수 없습니다. npm install -g @openai/codex 후 다시 실행하세요.');
}

function loadRoles() {
  const r = spawnSync(python, [...pyArgs, path.join(DIR, 'windows_helper.py'), 'roles', path.join(homeDir(), 'agents')],
    {encoding:'utf8', windowsHide:true});
  if (r.status !== 0) throw new Error(`역할 파일을 읽지 못했습니다: ${r.stderr || r.error}`);
  return JSON.parse(r.stdout);
}

export class Rpc {
  constructor(url) { this.url = url; this.next = 1; this.pending = new Map(); this.listeners = new Set(); }
  async open() {
    this.ws = new WebSocket(this.url);
    try { await new Promise((resolve,reject) => {
      const timer = setTimeout(() => reject(new Error('로컬 서버 연결 시간 초과')), 8000);
      this.ws.addEventListener('open', () => {clearTimeout(timer);resolve();}, {once:true});
      this.ws.addEventListener('error', () => {clearTimeout(timer);reject(new Error('로컬 서버에 연결할 수 없습니다.'));}, {once:true});
    }); } catch(error) {this.ws.close();throw error;}
    this.ws.addEventListener('message', ev => {
      let msg;
      try {msg = JSON.parse(ev.data);} catch {return;}
      if (msg.id !== undefined && !msg.method) {
        const pending = this.pending.get(msg.id);
        if (pending) {
          this.pending.delete(msg.id); clearTimeout(pending.timer);
          msg.error ? pending.reject(new Error(JSON.stringify(msg.error))) : pending.resolve(msg.result);
        }
      } else {
        // Approval and user-input requests are left to the attached interactive CLI.
        // This transport never approves actions automatically.
        for (const listener of this.listeners) listener(msg);
      }
    });
    this.ws.addEventListener('close', () => {
      for (const p of this.pending.values()) {clearTimeout(p.timer);p.reject(new Error('로컬 서버 연결이 종료되었습니다.'));}
      this.pending.clear();
    });
    await this.call('initialize', {clientInfo:{name:'codex_team_local',title:'Codex Team',version:'1.0.0'}});
    this.ws.send(JSON.stringify({method:'initialized',params:{}}));
    return this;
  }
  call(method,params={},timeout=30000) {
    const id=this.next++;
    return new Promise((resolve,reject) => {
      const timer=setTimeout(() => {this.pending.delete(id);reject(new Error(`${method}: 응답 시간 초과. 변경 요청은 중복 실행하지 말고 상태를 먼저 확인하세요.`));}, timeout);
      this.pending.set(id,{resolve,reject,timer});
      this.ws.send(JSON.stringify({id,method,params}));
    });
  }
  close() {this.ws?.close();}
}

function openWindow(manifest, role) {
  const args=[process.execPath,FILE,'attach',manifest,role];
  const r=spawnSync(python,[...pyArgs,path.join(DIR,'windows_helper.py'),'window',...args],{encoding:'utf8',windowsHide:true});
  if(r.status!==0) throw new Error(`터미널 창을 열 수 없습니다: ${r.stderr || r.error}`);
}

function workerInstructions(role, team) {
  return `${role.developer_instructions}\n\n이 세션은 별도 CLI 창에서 실행되는 팀 작업자다. 총괄이 전달한 작업을 수행하고 결과를 이 대화에 보고한다. 작업을 받기 전에는 기다린다. 다른 에이전트를 생성하거나 팀 외 세션을 제어하지 않는다.\n팀 프로젝트: ${team.project}\n각 배정에 쓰기 담당 경로가 전달된다. 배정된 경로만 수정하고 공통 파일 변경은 총괄에게 요청한다. 실제 접근 권한은 Codex 샌드박스를 따른다.\n`;
}

export function modelSettings(model='gpt-6-sol') {
  const efforts={'gpt-6-astra':'high','gpt-6-sol':'medium'};
  if(!Object.hasOwn(efforts,model))throw new Error('팀 모델은 gpt-6-astra/high 또는 gpt-6-sol/medium을 사용하세요.');
  return {model,effort:efforts[model]};
}

function coordinatorInstructions(role, team) {
  return `${role.developer_instructions}\n\n이 세션은 여러 CLI 창을 연결한 총괄이다. 사용자 요청을 받아 실제 codex_team MCP 도구로 별도 세션에 작업을 전달한다. 내장 spawn_agent나 일반 orchestrate 스킬 대신 이 연결된 팀의 도구를 사용한다.\n프로젝트: ${team.project}\n작업자: ${Object.keys(team.members).join(', ')}\n먼저 team_members로 상태와 역할을 확인한다. team_dispatch에는 구체적 작업, 완료 조건과 owned_paths를 전달한다. 분석만 필요하면 read_only=true를 사용한다. owned_paths는 중첩하지 않는 상대 파일 또는 디렉터리 경로이며 글로브가 아니다.\n각 team_dispatch에서 작업 난도에 맞는 model과 model_reason을 지정한다. 일반 구현·반복 작업은 gpt-6-sol(medium), 설계·복잡한 원인 분석·중요한 검토는 gpt-6-astra(high)를 선택한다. 같은 역할도 다음 배정에서 모델을 바꿀 수 있다. 현재 작업이 끝난 다음 필요한 배경을 포함해 재배정한다. 배정할 때 역할·모델·선택 이유를 사용자에게 짧게 알린다.\n독립된 작업을 각각 배정한 뒤 team_wait로 결과를 기다린다. 완료 후 team_result로 실제 내용을 읽는다. 결과를 검토하고 필요하면 같은 역할에 후속 작업을 다시 배정한다. qa_engineer의 검증은 구현 이후에 배정한다.\n공통 파일은 총괄이 소유한다. 프로젝트 폴더를 공유하므로 작업 범위를 조율하고 다른 작업자의 변경을 되돌리지 않는다. 사용자가 요청하지 않은 개발을 시작하지 않는다.\n승인이나 사용자 입력 대기 상태면 해당 작업자 창을 알려준다. 승인 정책을 약화하거나 대신 승인하지 않는다. 완료 보고 전에 실제 수정 내용과 검증 결과를 확인한다.\n`;
}

async function createThread(rpc,team,roleName,instructions,isCoordinator=false) {
  const role=team.roleDefinitions[roleName];
  const selected=modelSettings(isCoordinator?'gpt-6-astra':(role.model||'gpt-6-sol'));
  const config={'features.multi_agent':false};
  if (isCoordinator) config['mcp_servers.codex_team']={command:process.execPath,args:[FILE,'mcp',team.manifest],startup_timeout_sec:30,tool_timeout_sec:65};
  config.model_reasoning_effort=selected.effort;
  const params={cwd:team.project,developerInstructions:instructions,config,model:selected.model,
    sandbox:role.sandbox_mode==='read-only'?'read-only':'workspace-write',approvalPolicy:'on-request',approvalsReviewer:'user'};
  const result=await rpc.call('thread/start',params,60000);
  if(result.model!==selected.model || result.reasoningEffort!==selected.effort)throw new Error(`${roleName}: 요청한 모델/추론 수준이 적용되지 않았습니다.`);
  const id=result.thread.id;
  await rpc.call('thread/name/set',{threadId:id,name:`${team.id} · ${roleName}`});
  // Empty threads are unloaded without a rollout when the creation client leaves.
  // Persist a setup message before opening a separate interactive CLI client.
  await rpc.call('thread/inject_items',{threadId:id,items:[{type:'message',role:'user',content:[{type:'input_text',text:`Codex Team 연결 설정: ${roleName} 역할로 연결되었습니다. 실제 작업 지시가 도착할 때까지 기다리세요.`}]}]});
  return {threadId:id,role:roleName,description:role.description,
    model:result.model,reasoningEffort:result.reasoningEffort,
    readOnly:role.sandbox_mode==='read-only',sandboxPolicy:result.sandbox,lastTurnId:null,ownedPaths:[]};
}

async function freePort() {
  const server=net.createServer();
  await new Promise((res,rej)=>{server.once('error',rej);server.listen(0,'127.0.0.1',res);});
  const port=server.address().port;
  await new Promise(res=>server.close(res));
  return port;
}

export async function startTeam(project,roles,{windows=true}={}) {
  if(process.platform!=='win32')throw new Error('여러 CLI 창 실행기는 Windows용입니다. 다른 운영체제에서는 orchestrate 스킬을 사용하세요.');
  project=fs.realpathSync(path.resolve(project));
  if(!fs.statSync(project).isDirectory()) throw new Error('프로젝트 디렉터리가 필요합니다.');
  const definitions=loadRoles();
  for(const role of ['orchestrator',...roles]) if(!definitions[role]) throw new Error(`전역 역할이 없습니다: ${role}`);
  if(new Set(roles).size!==roles.length || roles.includes('orchestrator')) throw new Error('작업자 역할은 중복 없이 지정하세요.');
  if(roles.length<1 || roles.length>6) throw new Error('작업자 수는 1~6명으로 지정하세요.');
  const id=`team-${new Date().toISOString().replace(/[-:.TZ]/g,'').slice(0,14)}-${crypto.randomBytes(2).toString('hex')}`;
  const sessionDir=path.join(homeDir(),'teams',id);
  fs.mkdirSync(sessionDir,{recursive:true});
  const manifest=path.join(sessionDir,'team.json');
  const team={id,manifest,project,url:`ws://127.0.0.1:${await freePort()}`,codex:resolveCodex(),members:{},coordinator:null,
    roleDefinitions:Object.fromEntries(['orchestrator',...roles].map(r=>[r,definitions[r]]))};
  saveJson(manifest,team);
  const supervisor=spawn(process.execPath,[FILE,'serve',manifest],{detached:true,stdio:'ignore',windowsHide:true});
  supervisor.unref();
  let rpc;
  for(let i=0;i<60;i++) {
    if(fs.existsSync(path.join(sessionDir,'server-error.txt'))) throw new Error(fs.readFileSync(path.join(sessionDir,'server-error.txt'),'utf8'));
    try {
      const health=await fetch(team.url.replace('ws://','http://')+'/readyz',{signal:AbortSignal.timeout(750)});
      if(health.ok){rpc=await new Rpc(team.url).open();break;}
    } catch {}
    await delay(500);
  }
  if(!rpc) {fs.writeFileSync(path.join(sessionDir,'stop.request'),'stop');throw new Error(`서버 시작 실패. 로그: ${sessionDir}`);}
  try {
    for(const role of roles) {
      team.members[role]=await createThread(rpc,team,role,workerInstructions(definitions[role],team));
      saveJson(manifest,team);
    }
    team.coordinator=await createThread(rpc,team,'orchestrator',coordinatorInstructions(definitions.orchestrator,team),true);
    saveJson(manifest,team);
    saveJson(path.join(homeDir(),'teams','last.json'),{manifest});
    if(windows) {
      for(const role of roles) openWindow(manifest,role);
      openWindow(manifest,'orchestrator');
    }
    return team;
  } catch(error) {
    fs.writeFileSync(path.join(sessionDir,'stop.request'),'stop');throw error;
  } finally {rpc.close();}
}

async function serve(manifest) {
  const team=readJson(manifest), dir=path.dirname(manifest);
  const out=fs.openSync(path.join(dir,'server.log'),'a');
  const child=spawn(team.codex[0],[...team.codex.slice(1),'app-server','--listen',team.url],{stdio:['ignore',out,out],windowsHide:true});
  child.on('error',error=>{fs.writeFileSync(path.join(dir,'server-error.txt'),error.message);});
  let stopped=false;
  child.on('exit',code=>{fs.writeFileSync(path.join(dir,'server-stopped.json'),JSON.stringify({code}));process.exitCode=code||0;clearInterval(timer);fs.closeSync(out);});
  const timer=setInterval(()=>{
    if(!stopped&&fs.existsSync(path.join(dir,'stop.request'))){
      stopped=true;
      // Kill only the exact process tree created by this supervisor.
      if(team.codex.length>1)spawnSync('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
      else child.kill();
    }
  },750);
}

async function attach(manifest,role) {
  const team=readJson(manifest);
  const member=role==='orchestrator'?team.coordinator:team.members[role];
  if(!member) throw new Error(`등록되지 않은 역할: ${role}`);
  process.stdout.write(`\u001b]0;Codex Team - ${role}\u0007`);
  console.log(`Codex Team | ${role}\n프로젝트: ${team.project}\n${role==='orchestrator'?'이 창에 개발할 작업을 입력하세요.':'총괄이 작업을 보내면 이 창에서 자동으로 진행됩니다.'}\n`);
  const child=spawn(team.codex[0],[...team.codex.slice(1),'--remote',team.url,'resume',member.threadId],{stdio:'inherit',windowsHide:false});
  child.on('error',error=>console.error(error.message));
  const code=await new Promise(resolve=>child.once('exit',resolve));
  if(code) {console.error('Codex 창 연결이 종료되었습니다.');await new Promise(resolve=>{process.stdin.resume();process.stdin.once('data',resolve);});}
  process.exitCode=code||0;
}

export function normalizeOwned(project,values) {
  return [...new Set(values.map(value=>{
    if(typeof value!=='string' || !value.trim() || /[*?]/.test(value)) throw new Error('owned_paths에는 상대 파일/폴더 경로를 입력하세요. 글로브는 지원하지 않습니다.');
    const abs=path.resolve(project,value), rel=path.relative(project,abs);
    if(!rel || rel==='..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) throw new Error('프로젝트 루트 전체 또는 외부 경로는 작업자에게 배정할 수 없습니다.');
    return rel.replaceAll('\\','/').replace(/\/$/,'').toLowerCase();
  }))];
}
export const scopesOverlap=(a,b)=>a===b || a.startsWith(b+'/') || b.startsWith(a+'/');

function briefThread(thread) {
  const turn=thread.turns?.at(-1);
  const messages=(turn?.items || []).filter(i=>i.type==='agentMessage');
  const finals=messages.filter(i=>i.phase==='final_answer');
  return {status:thread.status,turnId:turn?.id||null,turnStatus:turn?.status||null,error:turn?.error||null,
    text:(finals.length?finals:messages).map(i=>i.text||'').join('\n').slice(-18000)};
}

export class TeamControl {
  constructor(manifest,rpc){this.manifest=manifest;this.rpc=rpc;}
  team(){return readJson(this.manifest);}
  async snapshot(role){
    const member=this.team().members[role];
    if(!member)throw new Error(`알 수 없는 팀 역할: ${role}`);
    const result=await this.rpc.call('thread/read',{threadId:member.threadId,includeTurns:true});
    return {role,description:member.description,model:member.model,reasoningEffort:member.reasoningEffort,modelReason:member.modelReason,...briefThread(result.thread)};
  }
  async members(){return await Promise.all(Object.keys(this.team().members).map(role=>this.snapshot(role)));}
  async dispatch({role,task,owned_paths=[],read_only=false,model='gpt-6-sol',model_reason}){
    if(typeof task!=='string'||!task.trim())throw new Error('구체적인 task가 필요합니다.');
    const selected=modelSettings(model);
    if(model_reason!==undefined && (typeof model_reason!=='string'||!model_reason.trim()))throw new Error('model_reason에는 모델 선택 이유를 짧게 적으세요.');
    const modelReason=model_reason||'일반 작업 기본값';
    const team=this.team(), member=team.members[role];
    if(!member)throw new Error(`알 수 없는 팀 역할: ${role}`);
    const current=await this.snapshot(role);
    if(current.status?.type==='active' || current.turnStatus==='inProgress')throw new Error(`${role}는 작업 중입니다. 완료를 기다리거나 중단 후 다시 배정하세요.`);
    read_only=read_only||member.readOnly;
    const owned=read_only?[]:normalizeOwned(team.project,owned_paths);
    if(!read_only&&!owned.length)throw new Error('수정 작업에는 owned_paths가 필요합니다. 분석만 맡길 때는 read_only=true를 지정하세요.');
    for(const other of Object.values(team.members)){
      if(other.role===role || !other.ownedPaths?.length)continue;
      if(!owned.some(a=>other.ownedPaths.some(b=>scopesOverlap(a,b))))continue;
      const s=await this.snapshot(other.role);
      if(s.status?.type==='active'||s.turnStatus==='inProgress')throw new Error(`파일 소유권 충돌: ${other.role} 작업 완료 후 배정하세요.`);
    }
    const prompt=`총괄의 작업 배정\n역할: ${role}\n모델: ${selected.model} / ${selected.effort}\n선택 이유: ${modelReason}\n쓰기 담당: ${read_only?'없음 — 읽기와 분석만 수행':owned.join(', ')}\n${task}\n\n담당 범위, 실제 결과, 변경 파일과 검증 결과를 보고하세요.`;
    if(current.status?.type==='notLoaded')await this.rpc.call('thread/resume',{threadId:member.threadId});
    const sandboxPolicy=read_only?{type:'readOnly'}:(member.sandboxPolicy||{type:'workspaceWrite',writableRoots:[team.project],networkAccess:false,excludeTmpdirEnvVar:false,excludeSlashTmp:false});
    const result=await this.rpc.call('turn/start',{threadId:member.threadId,input:[{type:'text',text:prompt}],sandboxPolicy,...selected});
    member.lastTurnId=result.turn.id;member.ownedPaths=owned;
    member.model=selected.model;member.reasoningEffort=selected.effort;member.modelReason=modelReason;
    saveJson(this.manifest,team);
    return {role,threadId:member.threadId,turnId:result.turn.id,status:result.turn.status,ownedPaths:owned,model:selected.model,reasoningEffort:selected.effort,modelReason};
  }
  async wait({roles,seconds=30}={}){
    roles=roles?.length?roles:Object.keys(this.team().members);
    const until=Date.now()+Math.min(45,Math.max(1,seconds))*1000;
    while(true){
      const states=await Promise.all(roles.map(role=>this.snapshot(role)));
      const active=states.filter(s=>s.status?.type==='active'||s.turnStatus==='inProgress');
      const needsInput=states.some(s=>s.status?.activeFlags?.some(f=>/waiting|approval|input/i.test(typeof f==='string'?f:JSON.stringify(f))));
      if(!active.length||needsInput||Date.now()>=until)return {timedOut:!!active.length&&!needsInput,needsInput,members:states};
      await delay(2000);
    }
  }
  async interrupt({role}){
    const member=this.team().members[role], state=await this.snapshot(role);
    if(!state.turnId || state.turnStatus!=='inProgress')return {role,status:'not_running'};
    await this.rpc.call('turn/interrupt',{threadId:member.threadId,turnId:state.turnId});
    return {role,status:'interrupt_requested'};
  }
}

const toolSchema=(name,description,properties={},required=[])=>({name,description,inputSchema:{type:'object',properties,required,additionalProperties:false}});
export const TOOLS=[
  toolSchema('team_members','연결된 작업자 역할, 실행 상태와 최근 결과를 확인한다.'),
  toolSchema('team_dispatch','별도 CLI 작업자에 작업별 모델을 선택해 배정한다. Sol은 medium, Astra는 high를 쓴다. 파일 담당 경로는 협업용 예약이다.',{role:{type:'string'},task:{type:'string'},owned_paths:{type:'array',items:{type:'string'}},read_only:{type:'boolean'},model:{type:'string',enum:['gpt-6-sol','gpt-6-astra'],description:'일반 구현은 Sol, 설계·복잡한 분석·중요한 검토는 Astra'},model_reason:{type:'string',description:'이 작업에 해당 모델을 선택한 이유'}},['role','task','model','model_reason']),
  toolSchema('team_wait','작업자 완료 또는 승인·입력 대기를 최대 45초 기다린다.',{roles:{type:'array',items:{type:'string'}},seconds:{type:'number'}}),
  toolSchema('team_result','지정한 역할의 실제 최근 작업 결과와 상태를 읽는다.',{role:{type:'string'}},['role']),
  toolSchema('team_interrupt','이 팀의 지정된 작업자의 현재 작업만 중단한다.',{role:{type:'string'}},['role'])
];

async function mcp(manifest){
  const team=readJson(manifest), rpc=await new Rpc(team.url).open(), control=new TeamControl(manifest,rpc);
  const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  const send=message=>process.stdout.write(JSON.stringify(message)+'\n');
  for await(const line of lines){
    let request;
    try{request=JSON.parse(line);}catch{continue;}
    if(request.id===undefined)continue;
    try{
      let result;
      if(request.method==='initialize')result={protocolVersion:request.params?.protocolVersion||'2024-11-05',capabilities:{tools:{}},serverInfo:{name:'codex-team',version:'1.0.0'}};
      else if(request.method==='ping')result={};
      else if(request.method==='tools/list')result={tools:TOOLS};
      else if(request.method==='tools/call'){
        const {name,arguments:args={}}=request.params;
        try{
          let data;
          if(name==='team_members')data=await control.members();
          else if(name==='team_dispatch')data=await control.dispatch(args);
          else if(name==='team_wait')data=await control.wait(args);
          else if(name==='team_result')data=await control.snapshot(args.role);
          else if(name==='team_interrupt')data=await control.interrupt(args);
          else throw new Error('Unknown tool');
          result={content:[{type:'text',text:JSON.stringify(data)}]};
        }catch(error){result={isError:true,content:[{type:'text',text:error.message}]};}
      }else{send({jsonrpc:'2.0',id:request.id,error:{code:-32601,message:'Method not found'}});continue;}
      send({jsonrpc:'2.0',id:request.id,result});
    }catch(error){send({jsonrpc:'2.0',id:request.id,error:{code:-32603,message:error.message}});}
  }
  rpc.close();
}

function lastManifest(value){
  if(value)return path.resolve(value);
  return readJson(path.join(homeDir(),'teams','last.json')).manifest;
}
async function main(args){
  const command=args.shift()||'help';
  if(command==='serve')return serve(args[0]);
  if(command==='attach')return attach(args[0],args[1]);
  if(command==='mcp')return mcp(args[0]);
  if(command==='start'){
    const project=args.shift()||process.cwd();
    const at=args.indexOf('--roles');
    const roles=at>=0?args[at+1].split(','):['frontend_developer','backend_developer','qa_engineer'];
    const team=await startTeam(project,roles,{windows:!args.includes('--headless')});
    console.log(`팀 생성 완료: ${team.id}\n프로젝트: ${team.project}\n총괄 창에 작업을 입력하세요.\n설정: ${team.manifest}`);return;
  }
  if(command==='status'){
    const manifest=lastManifest(args[0]), rpc=await new Rpc(readJson(manifest).url).open();
    try{console.log(JSON.stringify(await new TeamControl(manifest,rpc).members(),null,2));}finally{rpc.close();}return;
  }
  if(command==='open'){
    const manifest=lastManifest(args[0]), team=readJson(manifest);
    for(const role of [...Object.keys(team.members),'orchestrator'])openWindow(manifest,role);
    return;
  }
  if(command==='stop'){
    const manifest=lastManifest(args[0]);
    fs.writeFileSync(path.join(path.dirname(manifest),'stop.request'),'stop');
    for(let i=0;i<20;i++){
      if(fs.existsSync(path.join(path.dirname(manifest),'server-stopped.json'))){console.log('이 팀의 로컬 서버가 종료되었습니다.');return;}
      await delay(250);
    }
    throw new Error('종료 요청은 저장했지만 아직 서버 종료를 확인하지 못했습니다.');
  }
  if(command==='roles'){
    for(const [name,role]of Object.entries(loadRoles()))console.log(`${name}: ${role.description}`);
    return;
  }
  console.log('Codex Team — 여러 CLI 창에서 전문가 협업\n\n  codex-team start C:\\projects\\my-app\n  codex-team start C:\\projects\\my-app --roles researcher,business_analyst\n  codex-team status\n  codex-team open\n  codex-team stop\n  codex-team roles\n\nstart는 빈 총괄·작업자 세션을 만들고 창을 엽니다. 총괄에 요청할 때 작업이 시작됩니다.');
}

if(process.argv[1] && path.resolve(process.argv[1])===FILE){
  const args=process.argv.slice(2);
  main([...args]).then(()=>{
    if(!['serve','attach','mcp'].includes(args[0]))process.exit(0);
  }).catch(error=>{console.error(`Codex Team 오류: ${error.message}`);process.exit(1);});
}
