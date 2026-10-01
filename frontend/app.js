
// Vercel production always uses the same origin; old external API settings do not carry over.
let API = window.RESEARCHOPS_CONFIG?.sameOrigin ? '' : (localStorage.getItem('researchops:apiBase') || window.RESEARCHOPS_CONFIG?.apiBase || '').replace(/\/$/,'');
let sessionToken = sessionStorage.getItem('researchops:session') || '';
let backendHealth = null;
const state = {
  route: 'workspace',
  researchId: localStorage.getItem('researchops:researchId') || null,
  result: null,
  polling: false,
  forecastYears: 5,
  researchMode: 'Standard',
  pollToken: 0,
  runToken: 0,
  motion: !matchMedia('(prefers-reduced-motion: reduce)').matches,
  history: []
};

const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = (s='') => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const safeUrl = value => {try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:'#';}catch{return '#';}};
const num = (v,d=0) => Number.isFinite(Number(v)) ? Number(v) : d;
const sleep = ms => new Promise(r => setTimeout(r, ms));

function toast(msg, type=''){
  const el = $('#toast');
  el.textContent = msg;
  el.className = `toast show ${type}`;
  clearTimeout(toast.t);
  toast.t = setTimeout(()=>el.className='toast', 4300);
}

async function api(path, opts={}){
  const headers = new Headers(opts.headers || {});
  if(sessionToken) headers.set('Authorization', `Bearer ${sessionToken}`);
  const controller = new AbortController();
  const timeout=setTimeout(()=>controller.abort(),30000);
  let res;
  try{res=await fetch(API + path,{...opts,headers,signal:controller.signal});}
  catch(e){throw new Error(e.name==='AbortError'?'Connection timed out. Accepted jobs continue in the worker. Check History.':e.message);}
  finally{clearTimeout(timeout);}
  if(res.status===401){sessionToken='';sessionStorage.removeItem('researchops:session');openConnection();}

  if(!res.ok){
    let detail = `${res.status} ${res.statusText}`;
    try{
      const j = await res.json();
      detail = typeof j.detail==='string' ? j.detail : Array.isArray(j.detail) ? j.detail.map(x=>`${x.loc?.slice(1).join('.') || 'Input'}: ${x.msg}`).join('; ') : JSON.stringify(j);
    }catch{
      try{ detail = await res.text() || detail; }catch{}
    }
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res;
}

async function health(){
  try{
    const h = await api('/api/health');
    backendHealth=h;
    $('#demoBanner').classList.toggle('hidden',!h.demo_mode);
    $('#statusDot').className = `status-dot ${h.status === 'ok' ? 'ok' : 'bad'}`;
    $('#statusText').textContent = h.status!=='ok' ? `Configuration required: ${(h.missing||[]).join(', ')}` : h.worker_status==='offline' ? 'API online · start the worker' : h.demo_mode ? 'Offline demo · no live research' : 'Research engine online';
    if(h.authentication_required && !sessionToken) openConnection();
    $('#railEngine').textContent = h.mapreduce_engine || 'unknown';
  }catch(e){
    $('#statusDot').className='status-dot bad';
    $('#statusText').textContent='Backend unavailable';
    $('#railEngine').textContent='offline';
    $('#connectionHint').textContent='Check your Vercel deployment and database connection. For local use, start the API and worker.';
  }
}

function setRoute(route){
  state.route = route;
  $$('.view').forEach(v=>v.classList.toggle('active', v.dataset.view===route));
  $$('[data-route]').forEach(b=>b.classList.toggle('active', b.dataset.route===route));
  if(route==='history') renderHistory();
  if(route==='trail') renderTrail();
  if(route==='report') renderReport();
  window.scrollTo({top:0,behavior:'smooth'});
}

function initControls(){
  $$('[data-route]').forEach(b=>b.addEventListener('click',()=>setRoute(b.dataset.route)));

  $$('#forecastYears button').forEach(b=>b.addEventListener('click',()=>{
    $$('#forecastYears button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active'); state.forecastYears = Number(b.dataset.value);
  }));

  const bindRange = (id,out) => {
    const el=$(id), o=$(out);
    const go=()=>o.value=el.value;
    el.addEventListener('input',go); go();
  };
  bindRange('#maxTasks','#maxTasksOut');

  $$('#researchMode button').forEach(b=>b.addEventListener('click',()=>{
    $$('#researchMode button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    state.researchMode=b.dataset.value || 'Standard';
  }));

  $('#decisionSupport').addEventListener('change', e => $('#decisionStyleWrap').classList.toggle('hidden', !e.target.checked));
  $('#addHistory').addEventListener('click',()=>addHistoryRow());
  $('#startResearch').addEventListener('click', startResearch);
  $('#newResearch').addEventListener('click', startNewChat);
  $('#newChatTop')?.addEventListener('click', startNewChat);
  $('#newChatRail')?.addEventListener('click', startNewChat);
  $('#newChatHistory')?.addEventListener('click', startNewChat);

  $('#historySearch')?.addEventListener('input', applyHistoryFilter);
  $('#historyStatus')?.addEventListener('change', ()=>renderHistory(true));
  $('#refreshHistory')?.addEventListener('click', ()=>renderHistory(true));
  $('#historyList')?.addEventListener('click', async e=>{
    const btn=e.target.closest('[data-history-action]');
    if(!btn) return;
    const id=btn.dataset.id, action=btn.dataset.historyAction;
    if(action==='open-report') await openHistoryJob(id,'report');
    if(action==='open-trail') await openHistoryJob(id,'trail');
    if(action==='reconnect') await openHistoryJob(id,'workspace');
    if(action==='reuse') await reuseHistoryBrief(id);
    if(action==='delete') await deleteHistoryJob(id);
    if(action==='permanent') await permanentlyDeleteHistoryJob(id);
    if(action==='restore'){await api(`/api/research/${encodeURIComponent(id)}/restore`,{method:'POST'});state.history=[];await renderHistory(true);}
    if(action==='retry'){ await openHistoryJob(id,'workspace'); await retryCurrent(); }
  });

  $$('.result-tabs button').forEach(b=>b.addEventListener('click',()=>{
    $$('.result-tabs button').forEach(x=>x.classList.remove('active'));
    $$('.result-tab').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    $(`#tab-${b.dataset.resultTab}`).classList.add('active');
  }));

  $('#connectButton').addEventListener('click',openConnection);
  $('#connectionForm').addEventListener('submit',connectWorkspace);
  $('#signOut').addEventListener('click',()=>{sessionToken='';sessionStorage.removeItem('researchops:session');state.pollToken++;state.polling=false;state.result=null;state.history=[];$('#resultsPanel').classList.add('hidden');$('#historyList').innerHTML='';openConnection();});
  $('#cancelResearch').addEventListener('click',cancelCurrent);
  $('#retryResearch').addEventListener('click',retryCurrent);
  $('#exportHistory').addEventListener('click',exportHistory);
  $('#importBrowserHistory').addEventListener('click',importBrowserHistory);
  $('#importHistoryFile').addEventListener('change',importHistoryFile);
  $('#loadMoreHistory').addEventListener('click',()=>renderHistory(true,true));

  $('#motionToggle').addEventListener('click',()=>{
    state.motion = !state.motion;
    document.body.dataset.motion = state.motion ? 'on' : 'off';
    $('#motionToggle').style.opacity = state.motion ? '1' : '.45';
  });

  addHistoryRow();
}

function addHistoryRow(year='', value=''){
  const wrap = $('#historyRows');
  const row=document.createElement('div');
  row.className='history-row';
  row.innerHTML=`<input class="hist-year" type="number" min="1900" max="2200" placeholder="Year" value="${esc(year)}"><input class="hist-value" type="number" min="0" step="any" placeholder="Value" value="${esc(value)}"><button type="button" aria-label="Remove row">×</button>`;
  row.querySelector('button').addEventListener('click',()=>row.remove());
  wrap.appendChild(row);
}

function historicalData(){
  return $$('.history-row').map(row=>{
    const year=Number($('.hist-year',row).value), value=Number($('.hist-value',row).value);
    return year && value>0 ? {year,value} : null;
  }).filter(Boolean);
}

function payload(){
  const baseline = Number($('#baseline').value);
  return {
    question: $('#question').value.trim(),
    geography: $('#geography').value.trim() || null,
    industry: $('#industry').value.trim() || null,
    max_tasks: Number($('#maxTasks').value),
    sources_per_task: state.researchMode==='Exhaustive' ? 10 : state.researchMode==='Standard' ? 6 : 8,
    research_mode: state.researchMode,
    baseline_value: baseline>0 ? baseline : null,
    historical_data: historicalData(),
    forecast_years: state.forecastYears,
    include_decision_suggestion: $('#decisionSupport').checked,
    decision_style: $('#decisionStyle').value
  };
}

function setProgress(pct, stage){
  pct=Math.max(0,Math.min(100,Number(pct)||0));
  $('#progressPct').textContent=`${pct}%`;
  $('#progressBar').style.width=`${pct}%`;
  $('#progressStage').textContent=stage || 'Waiting for worker';
  $$('.stage-lights span').forEach((el,i)=>el.classList.toggle('done',pct>=[6,14,40,66,73,80,89][i]));
}

function showJob(job){
  setProgress(job.progress,job.stage || job.status);
  $('#progressId').textContent=`ID ${job.research_id.slice(0,8)} · ${job.status}`;
  $('#jobError').textContent=job.error || '';
  $('#jobError').classList.toggle('hidden',!job.error);
  $('#cancelResearch').classList.toggle('hidden',!['queued','running'].includes(job.status));
  $('#retryResearch').classList.toggle('hidden',!['failed','cancelled'].includes(job.status));
  const m=job.metrics || {};
  $('#jobDetails').textContent=[m.search_queries_completed!=null?`${m.search_queries_completed} search queries completed`:null,
    m.unique_sources_discovered!=null?`${m.unique_sources_discovered} sources discovered`:null,
    job.attempts?`Attempt ${job.attempts}`:null].filter(Boolean).join(' · ');
  if(job.status==='completed' && job.result){
    state.result=job.result;
    $('#resultsPanel').classList.remove('hidden');
    renderResults();dispatchScene('complete',1);
  }else{
    $('#resultsPanel').classList.add('hidden');
    dispatchScene(['queued','running'].includes(job.status)?'researching':'idle',.6);
  }
}

async function startResearch(){
  const p=payload();
  if(p.question.length<8){toast('Enter a clear problem statement.','error');$('#question').focus();return;}
  const token=++state.runToken;
  state.pollToken++;state.polling=false;
  $('#startResearch').disabled=true;
  $('#progressPanel').classList.remove('hidden');$('#resultsPanel').classList.add('hidden');
  $('#jobError').classList.add('hidden');
  $('#retryResearch').classList.add('hidden');$('#cancelResearch').classList.add('hidden');
  setProgress(0,'Submitting research brief…');
  const signature=JSON.stringify(p);
  let pending;
  try{pending=JSON.parse(sessionStorage.getItem('researchops:pending')||'null');}catch{}
  if(!pending || pending.signature!==signature) pending={signature,key:crypto.randomUUID()};
  sessionStorage.setItem('researchops:pending',JSON.stringify(pending));
  try{
    const job=await api('/api/research/run',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body:signature});
    sessionStorage.removeItem('researchops:pending');state.history=[];
    if(token!==state.runToken){toast('Previous brief was saved. Open it in History.');return;}
    state.researchId=job.research_id;state.result=null;
    localStorage.setItem('researchops:researchId',job.research_id);
    showJob(job);
    toast(job.status==='failed'?'The job was saved but the worker could not start. See the error below.':'Research saved. You can open New Chat while it runs.',job.status==='failed'?'error':'');
    if(['queued','running'].includes(job.status))pollResearch();
  }catch(e){
    if(token===state.runToken){$('#jobError').textContent=e.message;$('#jobError').classList.remove('hidden');setProgress(0,'Could not confirm start — check History before retrying');toast(e.message,'error');}
  }finally{if(token===state.runToken)$('#startResearch').disabled=false;}
}

async function pollResearch(){
  if(state.polling || !state.researchId)return;
  state.polling=true;
  const token=++state.pollToken,rid=state.researchId;
  let errors=0;
  try{
    while(token===state.pollToken && rid===state.researchId){
      try{
        const job=await api(`/api/research/${encodeURIComponent(rid)}`);
        if(token!==state.pollToken)return;
        errors=0;showJob(job);
        if(['completed','failed','cancelled'].includes(job.status)){
          state.history=[];
          toast(job.status==='completed'?'Research completed and saved to History.':job.error || job.stage,job.status==='failed'?'error':'');
          return;
        }
      }catch(e){
        if(token!==state.pollToken)return;
        errors++;
        $('#jobDetails').textContent=`Connection interrupted. Reconnecting; saved work remains in History. ${e.message}`;
        if(!sessionToken && backendHealth?.authentication_required)return;
      }
      await sleep(document.hidden?10000:Math.min(15000,2000*(1+errors)));
    }
  }finally{if(token===state.pollToken)state.polling=false;}
}

async function cancelCurrent(){
  if(!state.researchId)return;
  try{const job=await api(`/api/research/${state.researchId}/cancel`,{method:'POST'});state.pollToken++;state.polling=false;showJob(job);state.history=[];toast('Research cancelled. Saved stages remain available for retry.');}
  catch(e){toast(e.message,'error');}
}

async function retryCurrent(){
  if(!state.researchId)return;
  try{state.pollToken++;state.polling=false;const job=await api(`/api/research/${state.researchId}/retry`,{method:'POST'});showJob(job);state.history=[];if(['queued','running'].includes(job.status))pollResearch();}
  catch(e){toast(e.message,'error');}
}

function startNewChat(){
  // The backend run is intentionally not cancelled. If it is still working it will
  // finish in the background and stay accessible from History.
  state.pollToken++;
  state.runToken++;
  state.polling=false;
  state.researchId=null;
  state.result=null;
  state.history=[];
  sessionStorage.removeItem('researchops:pending');
  $('#startResearch').disabled=false;
  localStorage.removeItem('researchops:researchId');
  populateResearchForm({research_mode:'Standard',forecast_years:5,max_tasks:3,decision_style:'Balanced'});
  $('#resultsPanel').classList.add('hidden');
  $('#progressPanel').classList.add('hidden');
  setProgress(0,'Ready');
  setRoute('workspace');
  dispatchScene('idle',.25);
  toast('New chat ready. Previous research remains saved in History.');
  setTimeout(()=>$('#question')?.focus(),80);
}

function resetResearch(){ startNewChat(); }

function metric(value,label){
  return `<div class="metric"><b>${esc(value)}</b><span>${esc(label)}</span></div>`;
}

function sourceMap(catalog=[]){
  return Object.fromEntries(catalog.map(s=>[s.source_id,s]));
}
function sourceLinks(ids=[], catalog=[]){
  const map=sourceMap(catalog);
  return ids.filter(id=>map[id]).map(id=>`<a href="${esc(safeUrl(map[id].url))}" target="_blank" rel="noopener">${esc(id)} · ${esc(map[id].domain||'source')}</a>`).join('');
}
function sourceChips(ids=[],catalog=[]){
  const map=sourceMap(catalog);
  return ids.filter(id=>map[id]).map(id=>`<a class="source-chip" href="${esc(safeUrl(map[id].url))}" target="_blank" rel="noopener">${esc(id)} · ${esc(map[id].domain||'source')}</a>`).join('');
}
function confidenceLabel(c){
  c=num(c); return c>=85?'Very high':c>=70?'High':c>=50?'Moderate':c>=30?'Low':'Very low';
}

function renderResults(){
  const r=state.result;if(!r)return;
  const q=r.research_quality||{}, m=r.metrics||{}, c=r.source_catalog||[];
  $('#metricGrid').innerHTML=[
    metric(m.tasks||0,'Research tasks'),
    metric(m.sources_retrieved||0,'Sources reviewed'),
    metric(m.verified_findings||0,'Verified findings'),
    metric(m.queries_executed||0,'Search queries'),
    metric(m.evidence_conflicts||0,'Evidence conflicts'),
    metric(`${q.readiness_score||0}/100`,'Decision readiness')
  ].join('');

  renderDecision($('#decisionCard'), r.decision_suggestion, c);

  $('#executiveSummary').textContent=r.synthesis?.executive_summary || 'No executive summary was produced.';
  $('#executiveSources').innerHTML=sourceChips(r.synthesis?.executive_source_ids||[], c);

  renderEvidence(r);
  renderOpportunities(r);
  renderRisk(r);
  renderForecast(r);
  renderSources(r);
  renderTrail();
  renderReport();
}

function renderDecision(container, advice, catalog){
  if(!container) return;
  if(!advice || !advice.enabled){container.classList.add('hidden'); return}
  container.classList.remove('hidden');
  const stance=advice.stance||'Insufficient evidence', conf=Math.max(0,Math.min(100,num(advice.confidence)));
  $('#decisionStance',container).textContent=stance;
  $('#decisionSummary',container).textContent=advice.summary||'';
  $('#confidencePct',container).textContent=`${conf}%`;
  $('#confidenceLabel',container).textContent=confidenceLabel(conf);
  const arc=$('#confidenceArc',container); if(arc) arc.style.strokeDashoffset=String(301.6*(1-conf/100));
  const reasons=(advice.reasons||[]).map(x=>`<div class="decision-point">${esc(x.text||'')}${sourceLinks(x.source_ids||[],catalog)?`<div class="source-row">${sourceLinks(x.source_ids||[],catalog)}</div>`:''}</div>`).join('');
  const groups=[];
  if(advice.conditions?.length) groups.push(`<div class="decision-point"><b>Conditions before acting</b><ul>${advice.conditions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`);
  if(advice.action_plan?.length){
    groups.push(`<div class="decision-action-wrap"><b>Recommended action plan</b><div class="action-plan">${advice.action_plan.map(x=>`<article class="action-item"><span class="action-priority ${esc((x.priority||'next').toLowerCase())}">${esc(x.priority||'Next')}</span><h4>${esc(x.action||'')}</h4>${x.why?`<p><b>Why:</b> ${esc(x.why)}</p>`:''}${x.expected_effect?`<p><b>Expected effect:</b> ${esc(x.expected_effect)}</p>`:''}${x.timeframe?`<small>${esc(x.timeframe)}</small>`:''}${sourceLinks(x.source_ids||[],catalog)?`<div class="source-row">${sourceLinks(x.source_ids||[],catalog)}</div>`:''}</article>`).join('')}</div></div>`);
  } else if(advice.next_actions?.length){
    groups.push(`<div class="decision-point"><b>Next actions</b><ul>${advice.next_actions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`);
  }
  if(advice.success_metrics?.length) groups.push(`<div class="decision-point"><b>Success metrics</b><ul>${advice.success_metrics.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`);
  if(advice.reconsider_if?.length) groups.push(`<div class="decision-point"><b>Reconsider if</b><ul>${advice.reconsider_if.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`);
  if(advice.watchouts?.length) groups.push(`<div class="decision-point"><b>Watchouts</b><ul>${advice.watchouts.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`);
  if(advice.confidence_method) groups.push(`<div class="confidence-method">${esc(advice.confidence_method)}</div>`);
  $('#decisionReasons',container).innerHTML=reasons+groups.join('');
}

function findingCard(item,catalog, extra=''){
  const claim=item.claim||item.text||'';
  const rationale=item.rationale||'';
  const conf=item.confidence ? `${Math.round(num(item.confidence)*100)}% confidence` : '';
  return `<article class="finding-card"><h4>${esc(claim)}</h4>${rationale?`<p>${esc(rationale)}</p>`:''}${extra}<div class="finding-meta"><span class="confidence-pill">${esc(conf)}</span><div class="source-row">${sourceLinks(item.source_ids||[],catalog)}</div></div></article>`;
}

function renderEvidence(r){
  const el=$('#tab-evidence'), c=r.source_catalog||[], arr=r.verified_findings||[];
  const coverage=r.research_coverage||{}, conflicts=r.evidence_conflicts||[], sweep=r.research_sweep||{};
  const sweepHtml=`<div class="research-sweep-card"><div><span class="panel-kicker">ADAPTIVE WEB SWEEP</span><h3>${esc(sweep.mode||'Deep')} research</h3><p>${num(sweep.queries_executed)} search queries · ${num(sweep.unique_sources)} unique sources · ${num(sweep.unique_domains)} domains</p></div><span class="sweep-stop">${esc((sweep.stop_reason||'completed').replaceAll('-',' '))}</span></div>`;
  const coverageHtml=coverage.tasks?.length?`<div class="coverage-grid">${coverage.tasks.map(x=>`<article class="coverage-item ${esc(x.status||'')}"><span>${esc(x.task_id||'')}</span><h4>${esc(x.topic||'Research area')}</h4><p>${num(x.sources_found)} sources · ${num(x.unique_domains)} domains · ${num(x.verified_findings)} verified</p><small>${esc((x.status||'').replaceAll('-',' '))}</small></article>`).join('')}</div>`:'';
  const conflictsHtml=conflicts.length?`<div class="conflict-block"><h3>Evidence conflicts to resolve</h3>${conflicts.map(x=>`<article class="conflict-item ${esc(x.severity||'medium')}"><span>${esc(x.severity||'medium')}</span><h4>${esc(x.topic||'Evidence conflict')}</h4><p>${esc(x.description||'')}</p>${x.resolution_needed?`<small>Resolve: ${esc(x.resolution_needed)}</small>`:''}<div class="source-row">${sourceLinks(x.source_ids||[],c)}</div></article>`).join('')}</div>`:'';
  const gaps=r.synthesis?.evidence_gaps||[], follow=r.synthesis?.recommended_follow_up_research||[];
  const gapsHtml=(gaps.length||follow.length)?`<div class="gap-panel"><h3>Evidence gaps & next research</h3>${gaps.length?`<div><b>Gaps</b><ul>${gaps.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}${follow.length?`<div><b>Recommended follow-up</b><ul>${follow.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}</div>`:'';
  const findings=arr.length?arr.map(x=>findingCard(x,c)).join(''):`<div class="empty-state"><h3>No verified findings</h3><p>No claim passed the strict corroboration threshold.</p></div>`;
  el.innerHTML=sweepHtml+coverageHtml+conflictsHtml+gapsHtml+findings;
}

function renderOpportunities(r){
  const el=$('#tab-opportunities'), c=r.source_catalog||[], arr=r.synthesis?.opportunities||[];
  el.innerHTML=arr.length?arr.map(x=>findingCard(x,c)).join(''):`<div class="empty-state"><h3>No evidence-backed opportunities</h3><p>The synthesis did not identify a sufficiently supported opportunity.</p></div>`;
}
function renderRisk(r){
  const el=$('#tab-risk'), ra=r.risk_assessment||{}, risks=ra.risks||[], c=r.source_catalog||[];
  const bars=risks.map(x=>`<div class="bar-row"><span title="${esc(x.text||'')}">${esc(x.text||'Risk')}</span><div class="bar-track"><i style="width:${Math.min(100,num(x.score)/25*100)}%"></i></div><b>${num(x.score)}/25</b></div>`).join('');
  const cards=risks.map(x=>findingCard(x,c,`<p>Likelihood ${num(x.likelihood)}/5 · Impact ${num(x.impact)}/5 · Score ${num(x.score)}/25${x.mitigation?`<br>Mitigation: ${esc(x.mitigation)}`:''}</p>`)).join('');
  el.innerHTML=`<div class="chart-panel"><h3>Aggregate risk · ${ra.overall_score!=null?`${num(ra.overall_score)}/100`:'Not assessed'} · ${esc(ra.band||'Unknown')}</h3>${bars||'<p>No quantified risks.</p>'}</div>${cards}`;
}
function renderForecast(r){
  const el=$('#tab-forecast'), fc=r.forecast||{}, c=r.source_catalog||[];
  let html=`<div class="chart-panel"><h3>${esc((fc.method||'forecast').replaceAll('-',' '))} · ${num(r.request_options?.forecast_years,5)} year horizon</h3>`;
  const lines=[];
  if(fc.method==='evidence-based-scenario'){
    for(const [name,obj] of Object.entries(fc.scenarios||{})){
      const s=(obj.series||[]).map(p=>({year:p.year,value:p.value,label:name}));
      if(s.length) lines.push({name:name[0].toUpperCase()+name.slice(1),pts:s});
    }
  }else if(fc.method==='ridge-log-trend-ml'){
    const rows=fc.forecast||[];
    if(rows.length){
      lines.push({name:'Predicted',pts:rows.map(x=>({year:x.year,value:x.predicted}))});
      lines.push({name:'P10',pts:rows.map(x=>({year:x.year,value:x.p10}))});
      lines.push({name:'P90',pts:rows.map(x=>({year:x.year,value:x.p90}))});
    }
  }
  html+=lines.length?forecastSvg(lines):`<p style="color:var(--muted);font-size:12px">${esc(fc.warning||fc.message||'Not enough defensible data for a numeric forecast.')}</p>`;
  if(lines.length && (fc.warning||fc.message))html+=`<p class="forecast-warning">${esc(fc.warning||fc.message)}</p>`;
  if(lines.length) html+=`<div class="forecast-legend">${lines.map((x,i)=>`<span style="color:${['#6ee7ff','#a897ff','#7fffd7','#ffcc77'][i%4]}">${esc(x.name)}</span>`).join('')}</div>`;
  const ids=[...new Set((fc.evidence||[]).flatMap(x=>x.source_ids||[]))];
  if(ids.length)html+=`<div class="source-row" style="margin-top:12px">${sourceLinks(ids,c)}</div>`;
  html+='</div>';
  el.innerHTML=html;
}

function forecastSvg(lines){
  const all=lines.flatMap(l=>l.pts).filter(p=>Number.isFinite(Number(p.value)));
  if(!all.length)return '';
  const W=900,H=260,pad={l:55,r:18,t:18,b:38};
  const xs=all.map(p=>Number(p.year)), ys=all.map(p=>Number(p.value));
  const xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
  const xr=Math.max(1,xmax-xmin), yr=Math.max(1e-9,ymax-ymin);
  const x=v=>pad.l+(Number(v)-xmin)/xr*(W-pad.l-pad.r);
  const y=v=>H-pad.b-(Number(v)-ymin)/yr*(H-pad.t-pad.b);
  const colors=['#6ee7ff','#a897ff','#7fffd7','#ffcc77'];
  const grid=[0,.25,.5,.75,1].map(t=>{
    const yy=pad.t+t*(H-pad.t-pad.b);
    const val=ymax-t*yr;
    return `<line x1="${pad.l}" x2="${W-pad.r}" y1="${yy}" y2="${yy}" stroke="rgba(147,203,255,.10)"/><text x="4" y="${yy+4}" fill="#667d90" font-size="9">${Number(val).toFixed(1)}</text>`;
  }).join('');
  const paths=lines.map((l,i)=>{
    const d=l.pts.map((p,j)=>`${j?'L':'M'}${x(p.year).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
    const dots=l.pts.map(p=>`<circle cx="${x(p.year)}" cy="${y(p.value)}" r="3" fill="${colors[i%colors.length]}"/>`).join('');
    return `<path d="${d}" fill="none" stroke="${colors[i%colors.length]}" stroke-width="2"/><g>${dots}</g>`;
  }).join('');
  const years=[...new Set(xs)].sort().map(v=>`<text x="${x(v)}" y="${H-10}" fill="#667d90" font-size="9" text-anchor="middle">${v}</text>`).join('');
  return `<svg class="forecast-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Forecast chart">${grid}${paths}${years}</svg>`;
}

function renderSources(r){
  const c=r.source_catalog||[], el=$('#tab-sources');
  const rows=c.map(s=>`<div class="source-table-row"><span>${esc(s.source_id)}</span><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.title||s.domain||'Source')}</a><span>${esc(s.domain||'')}</span><span class="score">${Math.round(num(s.quality_score)*100)}% · ${esc(s.authority_tier||'web')}</span></div>`).join('');
  el.innerHTML=`<div class="source-table"><div class="source-table-row head"><span>ID</span><span>Source</span><span>Domain</span><span>Quality / type</span></div>${rows}</div>`;
}

function formatHistoryDate(iso){
  if(!iso) return 'Unknown date';
  const d=new Date(iso);
  if(Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {year:'numeric',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'});
}

function historyStatusClass(status=''){
  return ['completed','running','queued','failed','cancelled'].includes(status) ? status : 'unknown';
}

function historySummary(job){
  const result=job.result || {}, request=job.request || {}, decision=result.decision_suggestion || {}, quality=result.research_quality || {}, metrics=result.metrics || {}, risk=result.risk_assessment || {};
  return {
    research_id:job.research_id,
    question:job.question || result.question || request.question || 'Research run',
    status:job.status || 'completed', stage:job.stage || 'Completed', progress:job.progress ?? 100,
    error:job.error || null, created_at:job.created_at, updated_at:job.updated_at,
    geography:request.geography, industry:request.industry,
    forecast_years:request.forecast_years || result.request_options?.forecast_years || 5,
    research_mode:request.research_mode || result.request_options?.research_mode || 'Deep',
    decision_support:Boolean(request.include_decision_suggestion),
    decision_stance:decision.enabled ? decision.stance : null,
    decision_confidence:decision.enabled ? decision.confidence : null,
    readiness_score:quality.readiness_score,
    verified_findings:metrics.verified_findings,
    sources_retrieved:metrics.sources_retrieved,
    risk_score:risk.overall_score,
    report_available:Boolean(result)
  };
}

async function renderHistory(force=false,more=false){
  const list=$('#historyList');
  if(!list) return;
  const status=$('#historyStatus')?.value || 'all';
  $('#historyLoading')?.classList.remove('hidden');
  try{
    if(force || !state.history.length || state.history._status!==status){
      const data=await api(`/api/research?status=${encodeURIComponent(status)}&limit=${more?100:Math.max(100,Math.min(250,state.history.length))}&offset=${more?state.history.length:0}`);
      state.history=more?[...state.history,...data.items]:data.items;
      $('#loadMoreHistory').classList.toggle('hidden',state.history.length>=data.total);
      Object.defineProperty(state.history,'_status',{value:status,writable:true,configurable:true});
    }
    applyHistoryFilter();
    await refreshStorage();
  }catch(e){
    toast(`Could not load saved research history: ${e.message}`,'error');
  }finally{
    $('#historyLoading')?.classList.add('hidden');
  }
}

function applyHistoryFilter(){
  const list=$('#historyList');
  if(!list) return;
  const needle=($('#historySearch')?.value || '').trim().toLowerCase();
  const items=(state.history || []).filter(x=>{
    const hay=[x.question,x.geography,x.industry,x.decision_stance].filter(Boolean).join(' ').toLowerCase();
    return !needle || hay.includes(needle);
  });
  $('#historyCount').textContent=`${items.length} research run${items.length===1?'':'s'}`;
  $('#historyEmpty').classList.toggle('hidden', items.length!==0);
  if(!items.length){list.innerHTML='';return}
  list.innerHTML=items.map(x=>{
    const status=historyStatusClass(x.status);
    const complete=x.status==='completed' && x.report_available;
    const decision=x.decision_stance ? `<div class="history-decision"><span>AI suggestion</span><b>${esc(x.decision_stance)}</b>${x.decision_confidence!=null?`<small>${Math.round(num(x.decision_confidence))}% confidence</small>`:''}</div>` : '';
    const metrics=[
      x.readiness_score!=null?`${Math.round(num(x.readiness_score))}/100 readiness`:null,
      x.verified_findings!=null?`${num(x.verified_findings)} verified`:null,
      x.sources_retrieved!=null?`${num(x.sources_retrieved)} sources`:null,
      x.risk_score!=null?`${Math.round(num(x.risk_score))}/100 risk`:null,
      x.forecast_years?`${x.forecast_years}Y forecast`:null,
      x.research_mode?`${x.research_mode} research`:null
    ].filter(Boolean).map(v=>`<span>${esc(v)}</span>`).join('');
    return `<article class="history-card" data-history-id="${esc(x.research_id)}">
      <div class="history-card-top"><span class="history-status ${status}"><i></i>${esc(x.status)}</span><time>${esc(formatHistoryDate(x.created_at))}</time></div>
      <h3>${esc(x.question)}</h3>
      <div class="history-context">${x.geography?`<span>${esc(x.geography)}</span>`:''}${x.industry?`<span>${esc(x.industry)}</span>`:''}<span>ID ${esc(x.research_id.slice(0,8))}</span></div>
      ${metrics?`<div class="history-metrics">${metrics}</div>`:''}
      ${decision}
      ${x.error?`<div class="history-error">${esc(x.error)}</div>`:''}
      <div class="history-actions">
        ${complete&&!x.archived?`<button class="primary-mini" data-history-action="open-report" data-id="${esc(x.research_id)}">Open report</button><button class="ghost-mini" data-history-action="open-trail" data-id="${esc(x.research_id)}">Research trail</button>`:''}
        <button class="ghost-mini" data-history-action="reuse" data-id="${esc(x.research_id)}">Reuse brief</button>
        ${!x.archived&&['queued','running'].includes(x.status)?`<button class="primary-mini" data-history-action="reconnect" data-id="${esc(x.research_id)}">View progress</button>`:''}
        ${!x.archived&&['failed','cancelled'].includes(x.status)?`<button class="primary-mini" data-history-action="retry" data-id="${esc(x.research_id)}">Retry saved stages</button>`:''}
        ${x.archived?`<button class="primary-mini" data-history-action="restore" data-id="${esc(x.research_id)}">Restore</button><button class="danger-mini" data-history-action="permanent" data-id="${esc(x.research_id)}">Delete permanently</button>`:''}
        ${!x.archived&&!['queued','running'].includes(x.status)?`<button class="danger-mini" data-history-action="delete" data-id="${esc(x.research_id)}">Archive</button>`:''}
      </div>
    </article>`;
  }).join('');
}

async function openHistoryJob(id,destination='report'){
  try{
    const job=await api(`/api/research/${encodeURIComponent(id)}`);
    state.pollToken++;state.polling=false;state.runToken++;
    state.researchId=id;state.result=job.result||null;
    localStorage.setItem('researchops:researchId',id);
    if(job.request)populateResearchForm(job.request);
    $('#progressPanel').classList.remove('hidden');showJob(job);
    setRoute(job.result?destination:'workspace');
    if(['queued','running'].includes(job.status))pollResearch();
  }catch(e){toast(`Could not open research: ${e.message}`,'error');}
}

async function reuseHistoryBrief(id){
  try{const job=await api(`/api/research/${encodeURIComponent(id)}`);startNewChat();populateResearchForm(job.request||{});toast('Brief restored. Start research to create a separate saved job.');}
  catch(e){toast(e.message,'error');}
}

async function deleteHistoryJob(id){
  try{await api(`/api/research/${encodeURIComponent(id)}`,{method:'DELETE'});
    if(state.researchId===id)startNewChat();state.history=[];await renderHistory(true);
    toast('Research archived. Choose Archived in History to restore it.');
  }catch(e){toast(e.message,'error');}
}

function populateResearchForm(req={}){
  $('#question').value=req.question || '';
  $('#geography').value=req.geography || '';
  $('#industry').value=req.industry || '';
  if(req.max_tasks){$('#maxTasks').value=Math.min(5,Math.max(3,req.max_tasks));$('#maxTasksOut').value=$('#maxTasks').value;}
  state.researchMode=req.research_mode || 'Deep';
  $$('#researchMode button').forEach(b=>b.classList.toggle('active',b.dataset.value===state.researchMode));
  state.forecastYears=Math.max(1,Math.min(5,Number(req.forecast_years)||5));
  $$('#forecastYears button').forEach(b=>b.classList.toggle('active',Number(b.dataset.value)===state.forecastYears));
  $('#decisionSupport').checked=Boolean(req.include_decision_suggestion);
  $('#decisionStyleWrap').classList.toggle('hidden',!$('#decisionSupport').checked);
  if(req.decision_style) $('#decisionStyle').value=req.decision_style;
  $('#baseline').value=req.baseline_value || '';
  $('#historyRows').innerHTML='';
  const hist=req.historical_data || [];
  if(hist.length) hist.forEach(p=>addHistoryRow(p.year,p.value)); else addHistoryRow();
}

function renderTrail(){
  const empty=$('#trailEmpty'), content=$('#trailContent');
  if(!state.result){empty.classList.remove('hidden');content.classList.add('hidden');return}
  empty.classList.add('hidden');content.classList.remove('hidden');
  const tasks=state.result.plan?.tasks||[];
  $('#taskTimeline').innerHTML=tasks.map((t,i)=>{const qs=(t.search_queries||[t.research_query]).filter(Boolean);return `<article class="task-card"><span class="num">TASK ${String(i+1).padStart(2,'0')}</span><h3>${esc(t.topic||'Research task')}</h3><p>${esc(t.purpose||'')}</p><div class="query-code">${qs.map((q,j)=>`${j+1}. ${esc(q)}`).join('<br>')}</div></article>`}).join('');
  $('#mapreduceTrace').textContent=JSON.stringify({research_sweep:state.result.research_sweep||{},mapreduce:state.result.mapreduce||{}},null,2);
}

function renderReport(){
  const empty=$('#reportEmpty'), content=$('#reportContent');
  if(!state.result){empty.classList.remove('hidden');content.classList.add('hidden');return}
  const r=state.result,c=r.source_catalog||[],q=r.research_quality||{},m=r.metrics||{},ra=r.risk_assessment||{};
  empty.classList.add('hidden');content.classList.remove('hidden');
  $('#downloadMarkdown').href='#';
  $('#downloadPdf').href='#';
  $('#downloadMarkdown').onclick=(e)=>{e.preventDefault(); downloadTextReport(r);};
  $('#downloadPdf').onclick=(e)=>{e.preventDefault(); downloadPdfReport(r);};
  $('#reportId').textContent=`RID ${r.research_id.slice(0,8)}`;
  $('#reportDecision').innerHTML='';
  if(r.decision_suggestion?.enabled){
    const a=r.decision_suggestion;
    const actions=(a.action_plan||[]).map(x=>`<li><b>${esc(x.priority||'Next')} · ${esc(x.action||'')}</b>${x.timeframe?` — ${esc(x.timeframe)}`:''}${x.expected_effect?`<br>${esc(x.expected_effect)}`:''}</li>`).join('');
    $('#reportDecision').innerHTML=`<article class="decision-terminal" style="margin-bottom:14px"><div class="decision-left"><span class="panel-kicker">AI DECISION SUGGESTION</span><h3>${esc(a.stance||'')}</h3><p>${esc(a.summary||'')}</p>${actions?`<div class="report-actions-plan"><b>Action plan</b><ul>${actions}</ul></div>`:''}</div><div class="confidence-dial"><div><b>${num(a.confidence)}%</b><span>Research confidence</span><small>${confidenceLabel(a.confidence)}</small></div></div><div class="decision-foot"><span>Advisory only · evidence confidence is a heuristic, not a probability of success.</span></div></article>`;
  }
  const findings=(r.verified_findings||[]).map(x=>`<li>${esc(x.claim||'')}</li>`).join('');
  const opp=(r.synthesis?.opportunities||[]).map(x=>`<li><b>${esc(x.text||'')}</b>${x.rationale?` — ${esc(x.rationale)}`:''}</li>`).join('');
  const risks=(ra.risks||[]).map(x=>`<li><b>${esc(x.text||'')}</b> — ${num(x.score)}/25. ${esc(x.mitigation||'')}</li>`).join('');
  const sources=c.map(s=>`<li><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.source_id)} · ${esc(s.title||s.domain||'source')}</a></li>`).join('');
  $('#reportStructured').innerHTML=`
    <section class="report-section"><h2>${esc(r.question||'Research report')}</h2><p>${esc(r.synthesis?.executive_summary||'')}</p></section>
    <section class="report-section"><div class="report-kpis">${[
      [m.verified_findings||0,'Verified findings'],[q.unique_domains||0,'Distinct domains'],[`${q.readiness_score||0}/100`,'Decision readiness'],[ra.overall_score!=null?`${ra.overall_score}/100`:'Not assessed','Aggregate risk']
    ].map(x=>`<div class="report-kpi"><b>${esc(x[0])}</b><span>${esc(x[1])}</span></div>`).join('')}</div></section>
    <section class="report-section"><h2>Research coverage</h2><p>${esc(r.research_sweep?.mode||'Deep')} adaptive research · ${num(r.research_sweep?.queries_executed)} search queries · ${num(r.research_sweep?.unique_sources)} unique sources · ${num(r.research_sweep?.unique_domains)} domains. Stop reason: ${esc((r.research_sweep?.stop_reason||'completed').replaceAll('-',' '))}.</p></section>
    <section class="report-section"><h2>Verified findings</h2><ul>${findings||'<li>No verified findings.</li>'}</ul></section>
    <section class="report-section"><h2>Business opportunities</h2><ul>${opp||'<li>No evidence-backed opportunities identified.</li>'}</ul></section>
    <section class="report-section"><h2>Risk analysis</h2><ul>${risks||'<li>No quantified risks.</li>'}</ul></section>
    <section class="report-section"><h2>Source register</h2><ul>${sources}</ul></section>`;
}

function triggerDownload(blob, filename){
  const url=URL.createObjectURL(blob), a=document.createElement('a');
  a.href=url; a.download=filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1200);
}

function downloadTextReport(r){
  const blob=new Blob([r.report_markdown || '# ResearchOps Report\n\nNo report text available.'],{type:'text/markdown;charset=utf-8'});
  triggerDownload(blob,`ResearchOps_${(r.research_id||'report').slice(0,8)}.md`);
}

async function downloadPdfReport(r){
  const btn=$('#downloadPdf');
  const old=btn?.innerHTML;
  try{
    if(btn) btn.innerHTML='<span>Building PDF…</span><i>…</i>';
    const res=await api(`/api/research/${encodeURIComponent(r.research_id)}/report.pdf`);
    if(!res.ok){ let detail='PDF generation failed'; try{const j=await res.json();detail=j.detail||detail}catch{} throw new Error(detail); }
    triggerDownload(await res.blob(),`ResearchOps_${(r.research_id||'report').slice(0,8)}.pdf`);
  }catch(e){ toast(`Could not build PDF: ${e.message}`,'error'); }
  finally{ if(btn && old) btn.innerHTML=old; }
}

async function restoreJob(){
  if(!state.researchId)return;
  try{
    const job=await api(`/api/research/${encodeURIComponent(state.researchId)}`);
    if(job.request)populateResearchForm(job.request);
    $('#progressPanel').classList.remove('hidden');showJob(job);
    if(['queued','running'].includes(job.status))pollResearch();
  }catch(e){toast(`Could not reconnect to saved research: ${e.message}`,'error');}
}

function openConnection(){
  $('#backendAddress').value=API;
  if(!$('#connectionDialog').open)$('#connectionDialog').showModal();
}

async function connectWorkspace(event){
  event.preventDefault();
  const entered=$('#backendAddress').value.trim().replace(/\/$/,'');
  try{
    if(entered){const u=new URL(entered);if(!['https:','http:'].includes(u.protocol)||u.pathname!=='/'||u.search||u.hash)throw new Error('Enter the backend origin, for example https://your-project.vercel.app');}
    API=window.RESEARCHOPS_CONFIG?.sameOrigin ? '' : entered;localStorage.setItem('researchops:apiBase',API);
    sessionToken='';sessionStorage.removeItem('researchops:session');
    const password=$('#workspacePassword').value;
    if(password){const answer=await api('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});sessionToken=answer.token;sessionStorage.setItem('researchops:session',sessionToken);}
    const h=await api('/api/health');
    if(h.authentication_required && !sessionToken)throw new Error('Enter the workspace password configured on the backend.');
    $('#workspacePassword').value='';$('#connectionDialog').close();$('#connectionError').textContent='';
    await health();await restoreJob();toast('Workspace connected. History is saved on the backend.');
  }catch(e){$('#connectionError').textContent=e.message;}
}

async function importJobs(jobs){
  let imported=0;
  for(let i=0;i<jobs.length;i+=20){const response=await api('/api/history/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jobs:jobs.slice(i,i+20)})});imported+=response.imported;}
  state.history=[];await renderHistory(true);toast(`${imported} completed reports imported. Existing reports were preserved.`);
}
async function importBrowserHistory(){
  try{await importJobs(await window.ResearchHistory.list('completed'));}catch(e){toast(e.message,'error');}
}
async function importHistoryFile(event){
  try{const file=event.target.files[0];if(!file)return;if(file.size>12000000)throw new Error('History file is too large. Import smaller batches.');const value=JSON.parse(await file.text());const jobs=Array.isArray(value)?value:value.jobs;if(!Array.isArray(jobs))throw new Error('Expected a JSON array of saved research jobs.');await importJobs(jobs);}
  catch(e){toast(e.message,'error');}finally{event.target.value='';}
}

function dispatchScene(mode,intensity){
  window.dispatchEvent(new CustomEvent('researchops:scene',{detail:{mode,intensity}}));
}

/* ---------- Three.js research graph ---------- */
async function initThree(){
  const canvas=$('#research-gl');
  try{
    const THREE=await import('three');
    const mobile=matchMedia('(max-width:760px)').matches;
    const reduced=matchMedia('(prefers-reduced-motion:reduce)').matches;
    const renderer=new THREE.WebGLRenderer({canvas,antialias:!mobile,alpha:true,powerPreference:'high-performance'});
    renderer.setPixelRatio(Math.min(devicePixelRatio,mobile?1.25:1.7));
    renderer.setSize(innerWidth,innerHeight,false);
    renderer.setClearColor(0x000000,0);

    const scene=new THREE.Scene();
    scene.fog=new THREE.FogExp2(0x071018,0.034);
    const camera=new THREE.PerspectiveCamera(48,innerWidth/innerHeight,.1,100);
    camera.position.set(0,0,12);

    const group=new THREE.Group(); group.position.set(mobile?0:3.6,0,0); scene.add(group);

    const core=new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.62,mobile?2:3),
      new THREE.MeshBasicMaterial({color:0x6ee7ff,wireframe:true,transparent:true,opacity:.18})
    ); group.add(core);

    const inner=new THREE.Mesh(
      new THREE.IcosahedronGeometry(.72,2),
      new THREE.MeshBasicMaterial({color:0xa897ff,wireframe:true,transparent:true,opacity:.45})
    ); group.add(inner);

    const rings=[];
    [[2.55,.008,0x6ee7ff],[2.05,.009,0xa897ff],[3.15,.006,0x7fffd7]].forEach((x,i)=>{
      const r=new THREE.Mesh(new THREE.TorusGeometry(x[0],x[1],5,96),new THREE.MeshBasicMaterial({color:x[2],transparent:true,opacity:.22}));
      r.rotation.x=(i===0?.9:i===1?1.9:.35); r.rotation.y=i*.7; rings.push(r);group.add(r);
    });

    const count=mobile?110:220;
    const pos=new Float32Array(count*3);
    for(let i=0;i<count;i++){
      const rad=3.4+Math.random()*5.5, th=Math.random()*Math.PI*2, u=Math.random()*2-1, s=Math.sqrt(1-u*u);
      pos[i*3]=Math.cos(th)*s*rad;pos[i*3+1]=u*rad;pos[i*3+2]=Math.sin(th)*s*rad;
    }
    const pg=new THREE.BufferGeometry();pg.setAttribute('position',new THREE.BufferAttribute(pos,3));
    const pts=new THREE.Points(pg,new THREE.PointsMaterial({color:0x86cfff,size:mobile?.025:.032,transparent:true,opacity:.56,sizeAttenuation:true}));
    group.add(pts);

    const nodes=[], links=[];
    const n=mobile?14:24;
    for(let i=0;i<n;i++){
      const a=Math.random()*Math.PI*2,b=Math.acos(Math.random()*2-1),r=2.2+Math.random()*1.6;
      const p=new THREE.Vector3(r*Math.sin(b)*Math.cos(a),r*Math.cos(b),r*Math.sin(b)*Math.sin(a));
      nodes.push(p);
      const m=new THREE.Mesh(new THREE.SphereGeometry(.04,8,8),new THREE.MeshBasicMaterial({color:i%4===0?0xa897ff:0x6ee7ff}));
      m.position.copy(p);group.add(m);
    }
    for(let i=0;i<n;i++){
      const next=(i*7+5)%n;
      const geo=new THREE.BufferGeometry().setFromPoints([nodes[i],nodes[next]]);
      const l=new THREE.Line(geo,new THREE.LineBasicMaterial({color:0x6ee7ff,transparent:true,opacity:.09}));
      group.add(l);links.push(l);
    }

    let mx=0,my=0,tx=0,ty=0,boost=.24, mode='idle';
    addEventListener('pointermove',e=>{tx=(e.clientX/innerWidth-.5)*2;ty=(e.clientY/innerHeight-.5)*2});
    addEventListener('researchops:scene',e=>{mode=e.detail?.mode||'idle';boost=Number(e.detail?.intensity||.25)});
    addEventListener('resize',()=>{
      frame.stillRendered=false;renderer.setSize(innerWidth,innerHeight,false);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();
      group.position.x=matchMedia('(max-width:760px)').matches?0:3.6;
    });
    let last=performance.now();
    function frame(now){
      requestAnimationFrame(frame);
      if(document.hidden || !state.motion || reduced){last=now;if(!frame.stillRendered){renderer.render(scene,camera);frame.stillRendered=true;}return;}
      frame.stillRendered=false;
      const dt=Math.min(.033,(now-last)/1000);last=now;mx+=(tx-mx)*.035;my+=(ty-my)*.035;
      group.rotation.y+=dt*(.055+boost*.08);group.rotation.x+=(my*.08-group.rotation.x)*.025;
      group.position.y+=( -my*.35-group.position.y)*.025;
      camera.position.x+=(mx*.24-camera.position.x)*.018;camera.lookAt(group.position.x*.3,0,0);
      rings.forEach((r,i)=>{r.rotation.z+=dt*(i%2?-.055:.07)*(1+boost)});
      inner.scale.setScalar(1+Math.sin(now*.002)*(mode==='researching'?.08:.025));
      core.material.opacity=.14+boost*.09+Math.sin(now*.0016)*.025;
      renderer.render(scene,camera);
    }
    requestAnimationFrame(frame);
  }catch(e){
    console.warn('Three.js unavailable; CSS visual fallback remains active.',e);
  }
}

async function refreshStorage(){
  try{
    const usage=await api('/api/storage');
    $('#storageUsage').textContent=`Database: ${(usage.database_bytes/1048576).toFixed(1)} / ${usage.budget_mb} MB app budget · Saved jobs: ${usage.saved_jobs}/${usage.max_saved_jobs} · Monthly starts/retries: ${usage.monthly_runs}/${usage.max_monthly_runs}`;
  }catch{ $('#storageUsage').textContent='Database usage unavailable. Check the Vercel Storage dashboard.'; }
}
async function exportHistory(){
  try{
    const data=await api('/api/history/export');
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='ResearchOps_History.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('Completed reports exported, including archived reports.');
  }catch(e){toast(e.message,'error');}
}
async function permanentlyDeleteHistoryJob(id){
  if(!confirm('Permanently delete this archived research and its saved stages? Export completed reports first. This cannot be undone.'))return;
  try{await api(`/api/research/${encodeURIComponent(id)}/permanent`,{method:'DELETE'});state.history=[];await renderHistory(true);toast('Archived research permanently deleted.');}
  catch(e){toast(e.message,'error');}
}

document.addEventListener('DOMContentLoaded', async ()=>{
  initControls();
  const readiness=health();
  initThree();
  setTimeout(()=>$('#boot').classList.add('out'),750);
  await readiness;
  if(!backendHealth?.authentication_required || sessionToken)await restoreJob();
  setInterval(()=>{if(document.visibilityState!=='hidden' && state.route==='history' && (!backendHealth?.authentication_required || sessionToken))renderHistory(true);},60000);
});

