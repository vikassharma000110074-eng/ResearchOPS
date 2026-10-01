// Simulated DOM checks. These do not validate CSS layout or actual WebGL.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const rid='19cce0da-c633-4822-8443-04d0ed28d687';
const request={question:'Should we launch this research platform?',max_tasks:3,research_mode:'Standard',forecast_years:3};
const result={research_id:rid,question:request.question,request_options:request,
  metrics:{tasks:3,verified_findings:1,sources_retrieved:1},plan:{tasks:[]},
  synthesis:{executive_summary:'Simulated test report',opportunities:[],limitations:['Offline fixture']},
  risk_assessment:{overall_score:null,risks:[],band:'Not assessed'},research_quality:{},
  source_catalog:[{source_id:'S1',url:'javascript:alert(1)',domain:'unsafe.test',title:'Unsafe URL fixture'}],
  verified_findings:[],forecast:{method:'evidence-based-scenario',available:true,warning:'Scenarios are illustrative.',
    scenarios:{base:{annual_rate:.1,series:[{year:0,value:100},{year:3,value:133.1}]}}},
  decision_suggestion:{enabled:false}};
const dom=new JSDOM(fs.readFileSync(path.join(root,'frontend/index.html'),'utf8'),
  {url:'http://localhost:3000',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window;
w.Headers=Headers;w.AbortController=AbortController;
w.matchMedia=()=>({matches:true,addEventListener(){},removeEventListener(){}});
w.scrollTo=()=>{};
w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
w.HTMLDialogElement.prototype.close=function(){this.open=false;};
let job={research_id:rid,question:request.question,request,status:'running',progress:14,stage:'Retrieving sources',result:null,metrics:{}};
let summary={...job,report_available:false};
let requests=[],pendingStart=null;
w.fetch=async(url,options={})=>{
  requests.push({url,method:options.method||'GET',headers:options.headers});
  let body;
  if(url==='/api/health')body={status:'ok',demo_mode:true,worker_status:'online',authentication_required:false};
  else if(url==='/api/storage')body={database_bytes:1048576,budget_mb:350,saved_jobs:1,max_saved_jobs:100,monthly_runs:1,max_monthly_runs:30};
  else if(url==='/api/research/run')return await new Promise(resolve=>{pendingStart=()=>resolve(new Response(JSON.stringify({...job,status:'queued',progress:0}),{status:202,headers:{'content-type':'application/json'}}));});
  else if(url.startsWith('/api/research?'))body={items:summary?[summary]:[],total:summary?1:0};
  else if(url===`/api/research/${rid}`)body=job;
  else if(url.endsWith('/permanent')){summary=null;body={deleted:true};}
  else if(url.endsWith('/cancel')){job={...job,status:'cancelled',stage:'Cancelled'};body=job;}
  else throw Error('Unexpected test request '+url);
  return new Response(JSON.stringify(body),{headers:{'content-type':'application/json'}});
};
let code=fs.readFileSync(path.join(root,'frontend/app.js'),'utf8');
code=code.slice(0,code.lastIndexOf("document.addEventListener('DOMContentLoaded'"));
w.eval(code+'\nwindow.testApp={state,initControls,health,startResearch,startNewChat,showJob,renderHistory,openHistoryJob,reuseHistoryBrief,restoreJob,cancelCurrent,safeUrl,permanentlyDeleteHistoryJob};');
const app=w.testApp;
const tick=()=>new Promise(resolve=>setTimeout(resolve,5));
(async()=>{
  app.initControls();await app.health();
  assert.equal(w.document.querySelector('#demoBanner').classList.contains('hidden'),false);
  app.showJob(job);assert.equal(w.document.querySelector('#progressPct').textContent,'14%');
  await tick();assert.equal(w.document.querySelector('#progressPct').textContent,'14%');
  w.document.querySelector('#question').value=request.question;
  const starting=app.startResearch();await tick();
  assert.ok(pendingStart);assert.equal(w.document.querySelector('#startResearch').disabled,true);
  app.startNewChat();pendingStart();await starting;
  assert.equal(app.state.researchId,null);assert.equal(app.state.result,null);
  assert.equal(w.localStorage.getItem('researchops:researchId'),null);
  assert.equal(w.document.querySelector('#question').value,'');
  assert.equal(requests.some(x=>x.url.endsWith('/cancel')),false);
  await app.renderHistory(true);
  assert.ok(w.document.querySelector('[data-history-action="reconnect"]'));
  assert.match(w.document.querySelector('#storageUsage').textContent,/1.0 \/ 350 MB/);
  assert.equal(w.document.querySelector('[data-history-action="open-report"]'),null);
  job={...job,status:'failed',progress:40,error:'Provider unavailable',stage:'Retry available'};
  summary={...job,report_available:false};await app.renderHistory(true);
  assert.ok(w.document.querySelector('[data-history-action="retry"]'));
  assert.match(w.document.querySelector('.history-error').textContent,/Provider unavailable/);
  job={...job,status:'completed',progress:100,error:null,result,stage:'Completed'};
  summary={...job,report_available:true};await app.renderHistory(true);
  assert.ok(w.document.querySelector('[data-history-action="open-report"]'));
  await app.openHistoryJob(rid,'report');
  assert.equal(app.state.route,'report');assert.equal(app.state.result.question,request.question);
  assert.match(w.document.querySelector('#tab-risk').textContent,/Not assessed/);
  assert.match(w.document.querySelector('#tab-forecast').textContent,/Scenarios are illustrative/);
  assert.equal(app.safeUrl('javascript:alert(1)'),'#');
  assert.equal(w.document.querySelector('#tab-sources a')?.getAttribute('href'),'#');
  await app.reuseHistoryBrief(rid);
  assert.equal(w.document.querySelector('#question').value,request.question);
  assert.equal(app.state.researchId,null);assert.equal(app.state.forecastYears,3);
  app.state.researchId=rid;await app.restoreJob();
  assert.equal(app.state.result.research_id,rid);
  job={...job,status:'running',progress:40,result:null};await app.cancelCurrent();
  assert.equal(w.document.querySelector('#progressStage').textContent,'Cancelled');
  assert.equal(w.document.querySelector('#retryResearch').classList.contains('hidden'),false);
  summary={...job,archived:true};w.document.querySelector('#historyStatus').value='archived';await app.renderHistory(true);
  assert.ok(w.document.querySelector('[data-history-action="permanent"]'));
  w.confirm=()=>false;await app.permanentlyDeleteHistoryJob(rid);assert.equal(requests.some(x=>x.url.endsWith('/permanent')),false);
  w.confirm=()=>true;await app.permanentlyDeleteHistoryJob(rid);assert.equal(requests.some(x=>x.url.endsWith('/permanent')&&x.method==='DELETE'),true);
  console.log('Frontend DOM checks passed: real progress, pending-start/New Chat, history, reopen/reuse/refresh, cancel, risk and forecast limitations, safe links.');
  w.close();
})().catch(error=>{console.error(error);w.close();process.exitCode=1;});
