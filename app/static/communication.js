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
  const score=Math.max(0,Math.min(100,n(s.communication_score)));
  const ring=q("#communication-score-ring");if(ring)ring.style.setProperty("--communication-score",score);
  setText("#communication-score",pct(score));
  setText("#communication-understanding",pct(s.understanding_score));
  setText("#communication-adaptation",pct(s.adaptation_score));
  setText("#communication-persona",pct(s.persona_stability));
  setText("#communication-diversity",pct(s.diversity_score));
  setText("#communication-explanation",pct(s.explanation_success));
  setText("#communication-evaluated",n(s.evaluated_turns));
}

function outcomeClass(x){
  if(["useful"].includes(x))return"good";
  if(["clarification_needed","correction_needed","too_long","too_short","style_mismatch","repetitive"].includes(x))return"bad";
  return"info";
}

function renderTurns(items){
  const host=q("#communication-turns");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="communication-empty">Коммуникационные turn ещё не накоплены.</div>';return;}
  host.innerHTML=items.slice(0,24).map(x=>{
    const persona=Math.round(n(x.persona_score)*100);
    const reply=x.assistant_message||"";
    return '<article class="communication-turn" style="--persona:'+persona+'"><div><h4>'+esc(x.user_message||"")+'</h4><p>'+esc(reply)+'</p><div class="communication-tags"><span class="communication-tag info">'+esc(x.communication_intent)+'</span><span class="communication-tag">'+esc(x.strategy)+'</span><span class="communication-tag">'+esc(x.depth)+'</span><span class="communication-tag">'+esc(x.tone)+'</span><span class="communication-tag '+outcomeClass(x.outcome)+'">'+esc(x.outcome)+'</span><span class="communication-tag">repeat '+pct01(x.repetition_score)+'</span></div>'+
      (reply?'<div class="communication-feedback"><button class="primary" type="button" data-com-feedback="useful" data-turn="'+x.id+'">Полезно</button><button type="button" data-com-feedback="misunderstood" data-turn="'+x.id+'">Не поняла меня</button><button type="button" data-com-feedback="too_long" data-turn="'+x.id+'">Слишком длинно</button><button type="button" data-com-feedback="too_short" data-turn="'+x.id+'">Слишком коротко</button><button type="button" data-com-feedback="repetitive" data-turn="'+x.id+'">Повторяется</button></div>':'')+
      '</div><div class="communication-scorebox"><strong>'+persona+'%</strong><small>persona</small><small>'+dateText(x.completed_at||x.created_at)+'</small></div></article>';
  }).join("");
  host.querySelectorAll("[data-com-feedback]").forEach(btn=>btn.addEventListener("click",()=>sendFeedback(Number(btn.dataset.turn),btn.dataset.comFeedback)));
}

function renderSkills(items){
  const host=q("#communication-skills");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="communication-empty">Навыки ещё не получили outcome evidence.</div>';return;}
  host.innerHTML=items.map(x=>{
    const mastery=Math.round(n(x.mastery)*100);
    const trend=n(x.trend);
    return '<article class="communication-skill"><div class="communication-skill-head"><strong>'+esc(x.label)+'</strong><span>'+mastery+'%</span></div><small>'+n(x.sample_count)+' samples · success '+n(x.success_count)+' · failures '+n(x.failure_count)+' · trend '+(trend>=0?"+":"")+pct01(trend)+'</small><div class="communication-bar"><i style="--skill:'+mastery+'%"></i></div></article>';
  }).join("");
}

function renderPrefs(items){
  const host=q("#communication-prefs");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="communication-empty">Явных коммуникационных предпочтений пока нет.</div>';return;}
  host.innerHTML=items.map(x=>'<article class="communication-pref"><div><strong>'+esc(x.preference_key)+'</strong><small>'+esc(JSON.stringify(x.value))+' · '+n(x.evidence_count)+' evidence · '+esc(x.source)+'</small></div><span>'+pct01(x.confidence)+'</span></article>').join("");
}

function renderRuntime(data){
  const host=q("#communication-runtime");if(!host)return;
  const turns=data.turns||[];
  const latest=turns[0]||{};
  const p=latest.persona_runtime||{};
  const signals=latest.user_signals||{};
  const activeSignals=Object.keys(signals).filter(k=>signals[k]&&signals[k].active);
  const rows=[
    ["Intent",latest.communication_intent||"—"],
    ["Need",latest.user_need||"—"],
    ["Strategy",latest.strategy||"—"],
    ["Depth",latest.depth||"—"],
    ["Tone",latest.tone||"—"],
    ["Explanation",latest.explanation_style||"—"],
    ["Address",latest.address_policy||"—"],
    ["Playfulness",p.playfulness_allowed?"allowed":"off"],
    ["Signals",activeSignals.length?activeSignals.join(", "):"none"],
  ];
  host.innerHTML=rows.map(x=>'<article class="runtime-card"><span>'+esc(x[0])+'</span><strong>'+esc(x[1])+'</strong></article>').join("");
}

function renderEvents(items){
  const host=q("#communication-events");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="communication-empty">События общения ещё не накоплены.</div>';return;}
  host.innerHTML=items.slice(0,20).map(x=>'<article class="communication-event"><i></i><div><strong>'+esc(x.event_type)+'</strong><small>turn '+(x.turn_id||"—")+(x.score==null?"":" · score "+pct01(x.score))+'</small></div><time>'+esc(dateText(x.created_at))+'</time></article>').join("");
}

function renderPrinciples(items){
  const host=q("#communication-principles");if(!host)return;
  host.innerHTML=(items||[]).map(x=>'<article class="communication-principle">'+esc(x)+'</article>').join("");
}

function renderPersona(data){
  const persona=data.persona||{};
  setText("#communication-persona-source",(persona.profile_source||"—")+" · schema "+(persona.profile_schema_version||"—"));
}

function render(data){
  payload=data;renderSummary(data);renderTurns(data.turns);renderSkills(data.skills);
  renderPrefs(data.preferences);renderRuntime(data);renderEvents(data.events);
  renderPrinciples(data.principles);renderPersona(data);
}

function load(){
  if(loading)return Promise.resolve(payload);
  loading=true;
  return fetchScope("/api/assistant/communication?scope=personal&turn_limit=80&event_limit=100",{cache:"no-store"})
    .then(r=>{if(!r.ok)throw new Error("Communication HTTP "+r.status);return r.json();})
    .then(render)
    .catch(err=>{const h=q("#communication-turns");if(h&&!payload)h.innerHTML='<div class="communication-empty">'+esc(err.message||err)+'</div>';})
    .finally(()=>{loading=false;});
}

function sendFeedback(turnId,feedback){
  return fetchScope("/api/assistant/communication/turns/"+encodeURIComponent(turnId)+"/feedback",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({scope:scopeValue(),feedback:feedback,reason:"UI feedback"})
  }).then(r=>{if(!r.ok)throw new Error("Feedback HTTP "+r.status);return r.json();})
    .then(()=>load()).catch(err=>window.alert("Feedback не сохранён: "+(err.message||err)));
}

function boot(){
  const form=q("#chat-form");
  if(form)form.addEventListener("submit",()=>setTimeout(load,2800));
  load();
}
window.AISHIN_COMMUNICATION_REFRESH=load;
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();