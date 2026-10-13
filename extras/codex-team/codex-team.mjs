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
  throw new Error('Codex CLI not found. Run npm install -g @openai/codex, then try again.');
}

function loadRoles() {
  const r = spawnSync(python, [...pyArgs, path.join(DIR, 'windows_helper.py'), 'roles', path.join(homeDir(), 'agents')],
    {encoding:'utf8', windowsHide:true});
  if (r.status !== 0) throw new Error(`Could not read the role files: ${r.stderr || r.error}`);
  return JSON.parse(r.stdout);
}

export class Rpc {
  constructor(url) { this.url = url; this.next = 1; this.pending = new Map(); this.listeners = new Set(); }
  async open() {
    this.ws = new WebSocket(this.url);
    try { await new Promise((resolve,reject) => {
      const timer = setTimeout(() => reject(new Error('Timed out connecting to the local server.')), 8000);
      this.ws.addEventListener('open', () => {clearTimeout(timer);resolve();}, {once:true});
      this.ws.addEventListener('error', () => {clearTimeout(timer);reject(new Error('Cannot connect to the local server.'));}, {once:true});
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
      for (const p of this.pending.values()) {clearTimeout(p.timer);p.reject(new Error('The local server connection closed.'));}
      this.pending.clear();
    });
    await this.call('initialize', {clientInfo:{name:'codex_team_local',title:'Codex Team',version:'1.0.0'}});
    this.ws.send(JSON.stringify({method:'initialized',params:{}}));
    return this;
  }
  call(method,params={},timeout=30000) {
    const id=this.next++;
    return new Promise((resolve,reject) => {
      const timer=setTimeout(() => {this.pending.delete(id);reject(new Error(`${method}: no response in time. Check the status before retrying a request that changes anything, so it does not run twice.`));}, timeout);
      this.pending.set(id,{resolve,reject,timer});
      this.ws.send(JSON.stringify({id,method,params}));
    });
  }
  close() {this.ws?.close();}
}

function openWindow(manifest, role) {
  const args=[process.execPath,FILE,'attach',manifest,role];
  const r=spawnSync(python,[...pyArgs,path.join(DIR,'windows_helper.py'),'window',...args],{encoding:'utf8',windowsHide:true});
  if(r.status!==0) throw new Error(`Cannot open a terminal window: ${r.stderr || r.error}`);
}

function workerInstructions(role, team) {
  return `${role.developer_instructions}\n\nThis session is a team worker running in its own CLI window. Do the work the coordinator sends and report the result in this conversation. Wait until you receive an assignment. Do not create other agents or control sessions outside the team.\nTeam project: ${team.project}\nEach assignment names the paths you own for writing. Change only those paths, and ask the coordinator for changes to shared files. Your actual access follows the Codex sandbox.\n`;
}

// Team models are configuration: "model:effort" entries separated by commas, listed from
// routine work to the most demanding. The first entry is the worker default and the last
// is the coordinator default (CODEX_TEAM_COORDINATOR_MODEL overrides it).
export const DEFAULT_TEAM_MODELS='gpt-6-sol:medium,gpt-6-astra:high';
const describeModels=models=>models.map(m=>`${m.model}/${m.effort}`).join(', ');

export function parseModels(spec) {
  if(typeof spec!=='string'||!spec.trim())throw new Error('Team models are empty. Use model:effort entries, for example gpt-6-sol:medium,gpt-6-astra:high.');
  const models=spec.split(',').map(entry=>{
    const match=/^\s*([^\s:]+)\s*:\s*([A-Za-z][\w-]*)\s*$/.exec(entry);
    if(!match)throw new Error(`Invalid team model "${entry.trim()}". Use model:effort, for example gpt-6-sol:medium.`);
    return {model:match[1],effort:match[2]};
  });
  if(new Set(models.map(m=>m.model)).size!==models.length)throw new Error('Each team model may be listed only once.');
  return models;
}

// `--models` wins over CODEX_TEAM_MODELS; both fall back to DEFAULT_TEAM_MODELS.
export const teamModels=(spec=process.env.CODEX_TEAM_MODELS)=>parseModels(spec?.trim()?spec:DEFAULT_TEAM_MODELS);

export function modelSettings(model,models=teamModels()) {
  const selected=model===undefined?models[0]:models.find(m=>m.model===model);
  if(!selected)throw new Error(`Team model must be one of: ${describeModels(models)}. Configure CODEX_TEAM_MODELS or start --models.`);
  return {model:selected.model,effort:selected.effort};
}

// CODEX_TEAM_COORDINATOR_MODEL is a configured model name, or model:effort for a coordinator-only model.
export function coordinatorModel(models,pinned=process.env.CODEX_TEAM_COORDINATOR_MODEL) {
  pinned=pinned?.trim();
  if(!pinned)return modelSettings(models.at(-1).model,models);
  if(!pinned.includes(':'))return modelSettings(pinned,models);
  const [only,...extra]=parseModels(pinned);
  if(extra.length)throw new Error('CODEX_TEAM_COORDINATOR_MODEL takes one model or model:effort.');
  return only;
}

// Releases from 2.0 no longer install an `orchestrator` role; use this brief when it is absent.
const COORDINATOR_ROLE={description:'Team coordinator',developer_instructions:'You coordinate a team of Codex CLI workers. Confirm the goal and completion criteria, assign only meaningful independent work, review results against real evidence, and report the outcome, the checks actually run and the remaining limits in the user\'s language.'};

export function coordinatorInstructions(role, team) {
  const models=team.models||teamModels();
  return `${role.developer_instructions}\n\nThis session is the coordinator connected to several CLI windows. Take the user's requests and hand work to the separate sessions with the codex_team MCP tools. Use this connected team's tools instead of the built-in spawn_agent or the regular orchestrate skill.\nProject: ${team.project}\nWorkers: ${Object.keys(team.members).join(', ')}\nFirst check status and roles with team_members. Give team_dispatch a concrete task, completion criteria and owned_paths. Use read_only=true when only analysis is needed. owned_paths are non-overlapping relative file or directory paths, not globs.\nIn each team_dispatch, set model and model_reason to fit the difficulty of the work. Configured team models, listed from routine to the most demanding work (each runs at the effort shown): ${describeModels(models)}. Use the first for routine implementation and repetitive work, and later ones for design, complex root-cause analysis and important reviews. The same role may use a different model on its next assignment. Reassign only after the current work finishes, and include the background it needs. When you assign work, tell the user the role, model and reason in one short line.\nAssign independent pieces of work separately, then wait for results with team_wait. After completion, read the actual content with team_result. Review the results and, if needed, assign follow-up work to the same role. Assign qa_engineer verification after the implementation.\nThe coordinator owns shared files. Workers share the project folder, so coordinate scopes and never revert another worker's changes. Do not start development the user did not ask for.\nWhen a worker waits for approval or user input, tell the user which worker window it is. Never weaken the approval policy or approve on the user's behalf. Before reporting completion, check the actual changes and verification results.\n`;
}

async function createThread(rpc,team,roleName,instructions,isCoordinator=false) {
  const role=team.roleDefinitions[roleName];
  const selected=isCoordinator?team.coordinatorModel:modelSettings(role.model||undefined,team.models);
  const config={'features.multi_agent':false};
  if (isCoordinator) config['mcp_servers.codex_team']={command:process.execPath,args:[FILE,'mcp',team.manifest],startup_timeout_sec:30,tool_timeout_sec:65};
  config.model_reasoning_effort=selected.effort;
  const params={cwd:team.project,developerInstructions:instructions,config,model:selected.model,
    sandbox:role.sandbox_mode==='read-only'?'read-only':'workspace-write',approvalPolicy:'on-request',approvalsReviewer:'user'};
  const result=await rpc.call('thread/start',params,60000);
  if(result.model!==selected.model || result.reasoningEffort!==selected.effort)throw new Error(`${roleName}: the requested model or reasoning effort was not applied.`);
  const id=result.thread.id;
  await rpc.call('thread/name/set',{threadId:id,name:`${team.id} · ${roleName}`});
  // Empty threads are unloaded without a rollout when the creation client leaves.
  // Persist a setup message before opening a separate interactive CLI client.
  await rpc.call('thread/inject_items',{threadId:id,items:[{type:'message',role:'user',content:[{type:'input_text',text:`Codex Team setup: connected as the ${roleName} role. Wait until an actual assignment arrives.`}]}]});
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

export async function startTeam(project,roles,{windows=true,models:modelSpec}={}) {
  if(process.platform!=='win32')throw new Error('The multi-window launcher is Windows-only. On other systems, use the orchestrate skill.');
  const models=teamModels(modelSpec), coordinatorSettings=coordinatorModel(models);
  project=fs.realpathSync(path.resolve(project));
  if(!fs.statSync(project).isDirectory()) throw new Error('A project directory is required.');
  const definitions=loadRoles();
  for(const role of roles) if(!definitions[role]) throw new Error(`Role is not installed in the Codex agents directory: ${role}`);
  definitions.orchestrator??=COORDINATOR_ROLE;
  if(new Set(roles).size!==roles.length || roles.includes('orchestrator')) throw new Error('List each worker role once, and do not list orchestrator.');
  if(roles.length<1 || roles.length>6) throw new Error('Choose between 1 and 6 worker roles.');
  const id=`team-${new Date().toISOString().replace(/[-:.TZ]/g,'').slice(0,14)}-${crypto.randomBytes(2).toString('hex')}`;
  const sessionDir=path.join(homeDir(),'teams',id);
  fs.mkdirSync(sessionDir,{recursive:true});
  const manifest=path.join(sessionDir,'team.json');
  const team={id,manifest,project,url:`ws://127.0.0.1:${await freePort()}`,codex:resolveCodex(),members:{},coordinator:null,
    models,coordinatorModel:coordinatorSettings,
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
  if(!rpc) {fs.writeFileSync(path.join(sessionDir,'stop.request'),'stop');throw new Error(`The local server did not start. Logs: ${sessionDir}`);}
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
  if(!member) throw new Error(`Role is not part of this team: ${role}`);
  process.stdout.write(`\u001b]0;Codex Team - ${role}\u0007`);
  console.log(`Codex Team | ${role}\nProject: ${team.project}\n${role==='orchestrator'?'Type the work for the team in this window.':'Work sent by the coordinator runs in this window automatically.'}\n`);
  const child=spawn(team.codex[0],[...team.codex.slice(1),'--remote',team.url,'resume',member.threadId],{stdio:'inherit',windowsHide:false});
  child.on('error',error=>console.error(error.message));
  const code=await new Promise(resolve=>child.once('exit',resolve));
  if(code) {console.error('The Codex window connection closed. Press Enter to close this window.');await new Promise(resolve=>{process.stdin.resume();process.stdin.once('data',resolve);});}
  process.exitCode=code||0;
}

export function normalizeOwned(project,values) {
  return [...new Set(values.map(value=>{
    if(typeof value!=='string' || !value.trim() || /[*?]/.test(value)) throw new Error('owned_paths takes relative file or folder paths. Globs are not supported.');
    const abs=path.resolve(project,value), rel=path.relative(project,abs);
    if(!rel || rel==='..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) throw new Error('A worker cannot own the whole project root or a path outside it.');
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
  models(){return this.team().models||teamModels();}
  async snapshot(role){
    const member=this.team().members[role];
    if(!member)throw new Error(`Unknown team role: ${role}`);
    const result=await this.rpc.call('thread/read',{threadId:member.threadId,includeTurns:true});
    return {role,description:member.description,model:member.model,reasoningEffort:member.reasoningEffort,modelReason:member.modelReason,...briefThread(result.thread)};
  }
  async members(){return await Promise.all(Object.keys(this.team().members).map(role=>this.snapshot(role)));}
  async dispatch({role,task,owned_paths=[],read_only=false,model,model_reason}){
    if(typeof task!=='string'||!task.trim())throw new Error('A concrete task is required.');
    const selected=modelSettings(model,this.models());
    if(model_reason!==undefined && (typeof model_reason!=='string'||!model_reason.trim()))throw new Error('model_reason must briefly say why the model was chosen.');
    const modelReason=model_reason||'default for routine work';
    const team=this.team(), member=team.members[role];
    if(!member)throw new Error(`Unknown team role: ${role}`);
    const current=await this.snapshot(role);
    if(current.status?.type==='active' || current.turnStatus==='inProgress')throw new Error(`${role} is busy. Wait for it to finish, or interrupt it before reassigning.`);
    read_only=read_only||member.readOnly;
    const owned=read_only?[]:normalizeOwned(team.project,owned_paths);
    if(!read_only&&!owned.length)throw new Error('Work that changes files needs owned_paths. For analysis only, set read_only=true.');
    for(const other of Object.values(team.members)){
      if(other.role===role || !other.ownedPaths?.length)continue;
      if(!owned.some(a=>other.ownedPaths.some(b=>scopesOverlap(a,b))))continue;
      const s=await this.snapshot(other.role);
      if(s.status?.type==='active'||s.turnStatus==='inProgress')throw new Error(`File ownership conflict: assign this after ${other.role} finishes.`);
    }
    const prompt=`Assignment from the coordinator\nRole: ${role}\nModel: ${selected.model} / ${selected.effort}\nReason: ${modelReason}\nOwned paths: ${read_only?'none (read and analyze only)':owned.join(', ')}\n${task}\n\nReport your scope, the actual result, changed files and verification results.`;
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
export const teamTools=models=>[
  toolSchema('team_members','List the connected worker roles, their run status and latest results.'),
  toolSchema('team_dispatch','Assign a task to a separate CLI worker with a model chosen for that task; each model runs at its configured effort. owned_paths reserves files for collaboration.',{role:{type:'string'},task:{type:'string'},owned_paths:{type:'array',items:{type:'string'}},read_only:{type:'boolean'},model:{type:'string',enum:models.map(m=>m.model),description:`Configured models from routine to most demanding work: ${describeModels(models)}`},model_reason:{type:'string',description:'Why this model fits this task'}},['role','task','model','model_reason']),
  toolSchema('team_wait','Wait up to 45 seconds for workers to finish or to need approval or input.',{roles:{type:'array',items:{type:'string'}},seconds:{type:'number'}}),
  toolSchema('team_result','Read the latest actual result and status of one role.',{role:{type:'string'}},['role']),
  toolSchema('team_interrupt','Interrupt only the current work of one worker in this team.',{role:{type:'string'}},['role'])
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
      else if(request.method==='tools/list')result={tools:teamTools(control.models())};
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
  const last=path.join(homeDir(),'teams','last.json');
  if(!fs.existsSync(last))throw new Error('No team has been started yet. Run codex-team start first, or pass the team.json path.');
  return readJson(last).manifest;
}
// A flag's value must follow it and must not be another flag.
export function flagValue(args,flag,example){
  const at=args.indexOf(flag);
  if(at<0)return undefined;
  const value=args[at+1];
  if(!value?.trim()||value.startsWith('--'))throw new Error(`${flag} needs a value such as ${example}.`);
  return value;
}
async function main(args){
  const command=args.shift()||'help';
  if(command==='serve')return serve(args[0]);
  if(command==='attach')return attach(args[0],args[1]);
  if(command==='mcp')return mcp(args[0]);
  if(command==='start'){
    const project=args.shift()||process.cwd();
    const roleList=flagValue(args,'--roles','researcher,business_analyst');
    const roles=roleList?roleList.split(',').map(role=>role.trim()):['frontend_developer','backend_developer','qa_engineer'];
    const models=flagValue(args,'--models','gpt-6-sol:medium,gpt-6-astra:high');
    const team=await startTeam(project,roles,{windows:!args.includes('--headless'),models});
    console.log(`Team created: ${team.id}\nProject: ${team.project}\nModels: ${describeModels(team.models)} (coordinator: ${describeModels([team.coordinatorModel])})\nType the work in the coordinator window.\nSettings: ${team.manifest}`);return;
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
      if(fs.existsSync(path.join(path.dirname(manifest),'server-stopped.json'))){console.log("This team's local server has stopped.");return;}
      await delay(250);
    }
    throw new Error('The stop request was saved, but the server has not confirmed that it stopped yet.');
  }
  if(command==='roles'){
    for(const [name,role]of Object.entries(loadRoles()))console.log(`${name}: ${role.description}`);
    return;
  }
  console.log('Codex Team - specialists working across several CLI windows (optional, Windows only, experimental)\n\n  codex-team start C:\\projects\\my-app\n  codex-team start C:\\projects\\my-app --roles researcher,business_analyst\n  codex-team start C:\\projects\\my-app --models gpt-6-sol:medium,gpt-6-astra:high\n  codex-team status\n  codex-team open\n  codex-team stop\n  codex-team roles\n\nstart creates empty coordinator and worker sessions and opens their windows. Work begins when you send a request to the coordinator.\n\nModels: --models or CODEX_TEAM_MODELS (model:effort,..., routine first; default ' + DEFAULT_TEAM_MODELS + '),\nCODEX_TEAM_COORDINATOR_MODEL (default: the last listed model).');
}

if(process.argv[1] && path.resolve(process.argv[1])===FILE){
  const args=process.argv.slice(2);
  main([...args]).then(()=>{
    if(!['serve','attach','mcp'].includes(args[0]))process.exit(0);
  }).catch(error=>{console.error(`Codex Team error: ${error.message}`);process.exit(1);});
}
