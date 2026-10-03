(function(){
"use strict";
let payload=null,loading=false;

function scopeValue(){return window.AISHIN_SCOPE?.get?.()||"personal";}
function scopeUrl(url){return window.AISHIN_SCOPE?.url?.(url)||url;}
function fetchScope(url,options){return window.fetch(scopeUrl(url),options);}

const q=(s)=>document.querySelector(s);
const n=(v)=>Number.isFinite(Number(v))?Number(v):0;
const esc=(v)=>String(v==null?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
const pct=(v)=>n(v).toFixed(1)+"%";
const pct01=(v)=>Math.round(n(v)*100)+"%";
const dateText=(v)=>{if(!v)return"—";const d=new Date(v);return Number.isNaN(d.getTime())?String(v).slice(0,19):d.toLocaleString("ru-RU",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});};
function setText(s,v){const e=q(s);if(e)e.textContent=v;}

function renderSummary(data){
  const s=data.summary||{};
  const score=Math.max(0,Math.min(100,n(s.research_score)));
  const ring=q("#research-score-ring");if(ring)ring.style.setProperty("--research-score",score);
  setText("#research-score",pct(score));
  setText("#research-open-gaps",n(s.open_gaps));
  setText("#research-trusted-claims",n(s.trusted_claims));
  setText("#research-conflicted-claims",n(s.conflicted_claims));
  setText("#research-open-contradictions",n(s.open_contradictions));
  setText("#research-enabled-sources",n(s.enabled_sources));
  setText("#research-evidence-quality",pct(s.evidence_quality));
}

function renderGaps(items){
  const host=q("#research-gaps");if(!host)return;
  items=(items||[]).filter(x=>x.status==="open"||x.status==="researching");
  if(!items.length){host.innerHTML='<div class="research-empty">Открытых пробелов знаний нет.</div>';return;}
  host.innerHTML=items.slice(0,30).map(x=>
    '<article class="research-gap"><div><strong>'+esc(x.question)+'</strong><small>'+esc(x.origin||"")+' · priority '+pct01(x.priority)+' · uncertainty '+pct01(x.uncertainty)+'</small><div class="research-tagrow"><span class="research-tag gap">'+esc(x.status)+'</span><span class="research-tag">attempts '+n(x.attempts)+'</span></div></div><div><button type="button" data-research-gap="'+x.id+'">Исследовать</button></div></article>'
  ).join("");
  host.querySelectorAll("[data-research-gap]").forEach(btn=>btn.addEventListener("click",()=>researchGap(Number(btn.dataset.researchGap))));
}

function renderClaims(items){
  const host=q("#research-claims");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="research-empty">Claims ещё не сформированы.</div>';return;}
  host.innerHTML=items.slice(0,35).map(x=>
    '<article class="research-claim"><div><strong>'+esc(x.statement)+'</strong><small>support '+n(x.support_count)+' · counter '+n(x.contradiction_count)+' · groups '+n(x.independent_groups)+'</small><div class="research-tagrow"><span class="research-tag '+esc(x.status)+'">'+esc(x.status)+'</span><span class="research-tag">C'+x.id+'</span>'+(x.promoted_memory_id?'<span class="research-tag trusted">memory #'+x.promoted_memory_id+'</span>':'')+'</div></div><div class="research-scorebox"><strong>'+pct01(x.confidence)+'</strong><small>confidence</small></div></article>'
  ).join("");
}

function renderEvidence(items){
  const host=q("#research-evidence");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="research-empty">Evidence Ledger пока пуст.</div>';return;}
  host.innerHTML=items.slice(0,40).map(x=>
    '<article class="research-evidence"><span class="evidence-id">E'+x.id+'</span><div class="body"><strong>'+esc(x.title||x.source_type)+'</strong><small>'+esc(x.source_type)+' / '+esc(x.source_group)+' · score '+pct01(x.evidence_score)+'</small><p>'+esc(x.content)+'</p></div></article>'
  ).join("");
}

function renderConflicts(items){
  const host=q("#research-contradictions");if(!host)return;
  items=(items||[]).filter(x=>x.status==="open");
  if(!items.length){host.innerHTML='<div class="research-empty">Открытых противоречий нет.</div>';return;}
  host.innerHTML=items.slice(0,24).map(x=>
    '<article class="research-conflict"><div><strong>Contradiction #'+x.id+'</strong><small>claim C'+(x.claim_id||"—")+' · '+esc(x.contradiction_type)+' · severity '+pct01(x.severity)+'</small><div class="research-tagrow"><span class="research-tag conflicted">'+esc(x.status)+'</span><span class="research-tag">E'+(x.left_evidence_id||"—")+' ↔ E'+(x.right_evidence_id||"—")+'</span></div></div><div><button type="button" data-research-resolve="'+x.id+'">Разрешить</button></div></article>'
  ).join("");
  host.querySelectorAll("[data-research-resolve]").forEach(btn=>btn.addEventListener("click",()=>resolveConflict(Number(btn.dataset.researchResolve))));
}

function renderSources(items){
  const host=q("#research-sources");if(!host)return;
  items=items||[];
  host.innerHTML=items.length?items.slice(0,30).map(x=>
    '<article class="research-source '+(x.enabled?"":"disabled")+'"><i></i><div><strong>'+esc(x.label)+'</strong><small>'+esc(x.source_type)+' · group '+esc(x.independent_group)+' · prior '+pct01(x.trust_prior)+(x.source_type==="external_connector"?" · adapter disabled":"")+'</small></div></article>'
  ).join(""):'<div class="research-empty">Источники не зарегистрированы.</div>';
}

function renderSessions(items){
  const host=q("#research-sessions");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="research-empty">Исследовательских сессий ещё нет.</div>';return;}
  host.innerHTML=items.slice(0,18).map(x=>
    '<article class="research-session"><div><strong>'+esc(x.question)+'</strong><small>'+esc(x.trigger)+' · '+n(x.evidence_count)+' evidence · '+n(x.independent_groups)+' groups · '+n(x.claim_count)+' claims · '+n(x.duration_ms)+' ms</small><div class="research-tagrow"><span class="research-tag '+(x.status==="completed"?"trusted":"")+'">'+esc(x.status)+'</span><span class="research-tag">R'+x.id+'</span></div></div><div class="research-scorebox"><small>'+esc(dateText(x.completed_at||x.started_at))+'</small></div></article>'
  ).join("");
}

function renderGate(data){
  const host=q("#research-gate");if(!host)return;
  host.innerHTML=[
    ["≥82%","confidence"],
    ["≥2","support evidence"],
    ["≥2","independent primary groups"],
    ["0","counter-evidence for trusted"]
  ].map(x=>'<article><strong>'+x[0]+'</strong><span>'+x[1]+'</span></article>').join("");
}

function renderHistory(items){
  const svg=q("#research-history");if(!svg)return;
  items=(items||[]).slice(0,50).reverse();
  if(items.length<2){svg.innerHTML='<text x="450" y="85" text-anchor="middle" fill="#9a908c" font-size="11">История исследований ещё накапливается</text>';return;}
  const w=900,h=170,px=32,py=20,uw=w-px*2,uh=h-py*2;
  const values=items.map(x=>n((x.summary&&x.summary.state&&x.summary.state.research_score)||0));
  const min=Math.max(0,Math.min(...values)-4),max=Math.min(100,Math.max(...values)+8||10);
  const X=i=>px+uw*i/Math.max(1,items.length-1),Y=v=>py+uh-((v-min)/Math.max(1,max-min))*uh;
  const grid=[0,.25,.5,.75,1].map(r=>{const y=py+uh*r;return'<line class="grid" x1="'+px+'" y1="'+y+'" x2="'+(w-px)+'" y2="'+y+'"></line>';}).join("");
  const path=values.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(v).toFixed(1)).join(" ");
  const dots=values.map((v,i)=>'<circle class="dot" cx="'+X(i).toFixed(1)+'" cy="'+Y(v).toFixed(1)+'" r="3"><title>'+v.toFixed(1)+'%</title></circle>').join("");
  svg.innerHTML=grid+'<path class="line" d="'+path+'"></path>'+dots;
}

function renderPrinciples(items){
  const host=q("#research-principles");if(!host)return;
  host.innerHTML=(items||[]).map(x=>'<article class="research-principle">'+esc(x)+'</article>').join("");
}

function render(data){
  payload=data;
  renderSummary(data);renderGaps(data.gaps);renderClaims(data.claims);
  renderEvidence(data.evidence);renderConflicts(data.contradictions);
  renderSources(data.sources);renderSessions(data.sessions);
  renderGate(data);renderHistory(data.cycles);renderPrinciples(data.principles);
}

function load(){
  if(loading)return Promise.resolve(payload);
  loading=true;
  return fetchScope("/api/assistant/research?scope=personal&gap_limit=80&session_limit=50&claim_limit=100&evidence_limit=100&cycle_limit=60",{cache:"no-store"})
    .then(r=>{if(!r.ok)throw new Error("Research HTTP "+r.status);return r.json();})
    .then(render).catch(err=>{const h=q("#research-gaps");if(h&&!payload)h.innerHTML='<div class="research-empty">'+esc(err.message||err)+'</div>';})
    .finally(()=>{loading=false;});
}

function researchGap(id){
  const gap=(payload&&payload.gaps||[]).find(x=>Number(x.id)===Number(id));
  if(!gap)return;
  runQuery(gap.question,id,true);
}
function runQuery(question,gapId,synthesize){
  return fetchScope("/api/assistant/research/query",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({scope:scopeValue(),question:question,gap_id:gapId||null,synthesize:synthesize!==false})})
    .then(r=>{if(!r.ok)throw new Error("Research query HTTP "+r.status);return r.json();})
    .then(()=>load()).catch(err=>window.alert("Исследование не выполнено: "+(err.message||err)));
}
function resolveConflict(id){
  const resolution=window.prompt(
    "Укажите подтверждённое разрешение противоречия. Оно будет сохранено в Evidence Ledger:",
    ""
  );
  if(!resolution||!resolution.trim())return;
  fetchScope("/api/assistant/research/contradictions/"+encodeURIComponent(id)+"/resolve",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({scope:scopeValue(),resolution:resolution.trim()})
  })
    .then(async r=>{const body=await r.json().catch(()=>({}));if(!r.ok)throw new Error(body.detail||("Resolve HTTP "+r.status));return body;})
    .then(()=>load())
    .catch(err=>window.alert("Противоречие не разрешено: "+(err.message||err)));
}

function manualQuery(){
  const input=q("#research-query");const text=(input&&input.value||"").trim();if(!text)return;
  runQuery(text,null,true).then(()=>{if(input)input.value="";});
}
function cycle(){
  const b=q("#research-cycle");if(b){b.disabled=true;b.textContent="Исследую…";}
  fetchScope("/api/assistant/research/cycle",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({scope:scopeValue(),max_sessions:2,synthesize:false})})
    .then(r=>{if(!r.ok)throw new Error("Research cycle HTTP "+r.status);return r.json();})
    .then(()=>load()).catch(err=>window.alert("Цикл исследований не выполнен: "+(err.message||err)))
    .finally(()=>{if(b){b.disabled=false;b.textContent="Исследовать пробелы";}});
}

function boot(){
  q("#research-cycle")?.addEventListener("click",cycle);
  q("#research-query-btn")?.addEventListener("click",manualQuery);
  q("#research-query")?.addEventListener("keydown",e=>{if(e.key==="Enter")manualQuery();});
  load();
}
window.AISHIN_RESEARCH_REFRESH=load;
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();