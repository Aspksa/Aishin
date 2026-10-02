(function(){
"use strict";
let payload=null,loading=false,selectedFile=null;

const q=(s)=>document.querySelector(s);
const n=(v)=>Number.isFinite(Number(v))?Number(v):0;
const esc=(v)=>String(v==null?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
const pct=(v)=>n(v).toFixed(1)+"%";
const pct01=(v)=>Math.round(n(v)*100)+"%";
const bytes=(v)=>{let x=n(v);if(x<1024)return x+" B";if(x<1048576)return(x/1024).toFixed(1)+" KB";return(x/1048576).toFixed(1)+" MB";};
const dateText=(v)=>{if(!v)return"—";const d=new Date(v);return Number.isNaN(d.getTime())?String(v).slice(0,19):d.toLocaleString("ru-RU",{day:"2-digit",month:"2-digit",year:"2-digit",hour:"2-digit",minute:"2-digit"});};
function setText(s,v){const e=q(s);if(e)e.textContent=v;}
function statusClass(v){return["studied","needs_ocr","quality_hold","failed"].includes(v)?v:"";}
function statusLabel(v){return({studied:"изучен",needs_ocr:"нужен OCR",quality_hold:"quality hold",failed:"ошибка",processing:"обработка",queued:"очередь"})[v]||v||"—";}

function renderSummary(data){
  const s=data.summary||{};
  const score=Math.max(0,Math.min(100,n(s.ingestion_score)));
  const ring=q("#documents-score-ring");if(ring)ring.style.setProperty("--documents-score",score);
  setText("#documents-score",pct(score));
  setText("#documents-studied",n(s.studied_documents));
  setText("#documents-ocr",n(s.ocr_required_documents));
  setText("#documents-duplicates",n(s.duplicate_documents));
  setText("#documents-facts-count",n(s.fact_count));
  setText("#documents-conflicts-count",n(s.contradiction_count));
  setText("#documents-quality-score",pct(s.extraction_quality));
  setText("#documents-semantic-score",pct(s.semantic_coverage));
}

function renderDocuments(items){
  const host=q("#documents-list");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="documents-empty">Библиотека пока пуста. Загрузите первый документ.</div>';return;}
  host.innerHTML=items.slice(0,60).map(x=>{
    const ext=(x.extension||"doc").replace(".","").slice(0,5);
    const duplicate=x.duplicate_of_id?'<span class="documents-tag duplicate">duplicate #'+x.duplicate_of_id+'</span>':"";
    const version=x.version_label?'<span class="documents-tag">'+esc(x.version_label)+'</span>':"";
    const prev=x.previous_version_id?'<span class="documents-tag">← version #'+x.previous_version_id+'</span>':"";
    return '<article class="document-card"><span class="document-icon">'+esc(ext)+'</span><div><strong>'+esc(x.filename)+'</strong><small>#'+x.id+' · '+bytes(x.size_bytes)+' · '+esc(x.parser||"parser pending")+' · '+dateText(x.created_at)+'</small><div class="documents-tags"><span class="documents-tag '+statusClass(x.status)+'">'+esc(statusLabel(x.status))+'</span>'+version+prev+duplicate+'<span class="documents-tag">'+n(x.page_count)+' pages</span><span class="documents-tag">'+n(x.chunk_count)+' chunks</span><span class="documents-tag">'+n(x.fact_count)+' facts</span></div></div><div class="documents-scorebox"><strong>'+pct01(x.quality_score)+'</strong><small>quality</small><button type="button" data-document-open="'+x.id+'">Открыть</button></div></article>';
  }).join("");
  host.querySelectorAll("[data-document-open]").forEach(btn=>btn.addEventListener("click",()=>openDocument(Number(btn.dataset.documentOpen))));
}

function renderFacts(items){
  const host=q("#documents-facts");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="documents-empty">Извлечённых фактов пока нет.</div>';return;}
  host.innerHTML=items.slice(0,40).map(x=>{
    const p=x.provenance||{};
    return '<article class="document-fact"><div><strong>'+esc(x.subject||"document")+' · '+esc(x.predicate||x.fact_type)+'</strong><small>'+esc(x.value)+'</small><div class="documents-tags"><span class="documents-tag '+(x.status==="grounded"?"studied":"quality_hold")+'">'+esc(x.status)+'</span><span class="documents-tag">'+esc(x.fact_type)+'</span></div><div class="document-provenance">D'+x.document_id+' · page '+(p.page||"—")+' · chunk '+(p.chunk_id||x.chunk_id||"—")+' · '+esc(x.filename||"")+'</div></div><div class="documents-scorebox"><strong>'+pct01(x.confidence)+'</strong><small>confidence</small></div></article>';
  }).join("");
}

function renderConflicts(items){
  const host=q("#documents-conflicts");if(!host)return;
  items=(items||[]).filter(x=>x.status==="open");
  if(!items.length){host.innerHTML='<div class="documents-empty">Открытых междокументных противоречий нет.</div>';return;}
  host.innerHTML=items.slice(0,30).map(x=>'<article class="document-conflict"><div><strong>Conflict #'+x.id+' · '+esc(x.fact_key)+'</strong><small>D'+x.left_document_id+': '+esc(x.left_value)+' ↔ D'+x.right_document_id+': '+esc(x.right_value)+'</small><div class="documents-tags"><span class="documents-tag failed">'+esc(x.status)+'</span><span class="documents-tag">'+esc(x.family_key)+'</span></div></div><div class="documents-scorebox"><strong>'+pct01(x.severity)+'</strong><small>severity</small></div></article>').join("");
}

function renderRuns(items){
  const host=q("#documents-runs");if(!host)return;
  items=items||[];
  if(!items.length){host.innerHTML='<div class="documents-empty">История ingestion ещё пуста.</div>';return;}
  host.innerHTML=items.slice(0,20).map(x=>'<article class="document-run"><div><strong>'+esc(x.filename)+' · '+esc(x.status)+'</strong><small>'+esc(x.trigger)+' · '+n(x.pages_extracted)+' pages · '+n(x.chunks_created)+' chunks · '+n(x.facts_created)+' facts · '+n(x.embeddings_created)+' vectors · '+n(x.duration_ms)+' ms</small></div><div class="documents-scorebox"><small>'+dateText(x.completed_at||x.created_at)+'</small></div></article>').join("");
}

function renderQuality(data){
  const host=q("#documents-quality");if(!host)return;
  const s=data.summary||{};
  const rows=[
    [pct01(s.quality_gate),"quality gate"],
    [pct01(s.coverage_gate),"coverage gate"],
    [pct(s.provenance_coverage),"extraction coverage"],
    [pct(s.semantic_coverage),"semantic coverage"],
  ];
  host.innerHTML=rows.map(x=>'<article><strong>'+esc(x[0])+'</strong><span>'+esc(x[1])+'</span></article>').join("");
}

function renderPrinciples(items){
  const host=q("#documents-principles");if(!host)return;
  host.innerHTML=(items||[]).map(x=>'<article class="documents-principle">'+esc(x)+'</article>').join("");
}

function render(data){
  payload=data;renderSummary(data);renderDocuments(data.documents);renderFacts(data.facts);renderConflicts(data.contradictions);renderRuns(data.runs);renderQuality(data);renderPrinciples(data.principles);
}

function load(){
  if(loading)return Promise.resolve(payload);
  loading=true;
  return fetch("/api/assistant/documents?scope=personal&document_limit=100&fact_limit=100&contradiction_limit=80&run_limit=60",{cache:"no-store"})
    .then(r=>{if(!r.ok)throw new Error("Documents HTTP "+r.status);return r.json();})
    .then(render)
    .catch(err=>{const h=q("#documents-list");if(h&&!payload)h.innerHTML='<div class="documents-empty">'+esc(err.message||err)+'</div>';})
    .finally(()=>{loading=false;});
}

function handleFile(file){
  selectedFile=file||null;
  setText("#documents-selected-file",selectedFile?(selectedFile.name+" · "+bytes(selectedFile.size)):"PDF, DOCX, XLSX, CSV, TXT, MD, HTML или изображение");
}
function upload(){
  if(!selectedFile){window.alert("Выберите документ.");return;}
  const button=q("#documents-upload-btn");if(button){button.disabled=true;button.textContent="Изучаю…";}
  const form=new FormData();
  form.append("file",selectedFile,selectedFile.name);
  form.append("scope","personal");
  form.append("enrich_with_ai",q("#documents-ai-enrich")?.checked?"true":"false");
  form.append("build_semantic_index",q("#documents-semantic-index")?.checked?"true":"false");
  fetch("/api/assistant/documents/upload",{method:"POST",body:form})
    .then(async r=>{const body=await r.json().catch(()=>({}));if(!r.ok)throw new Error(body.detail||("Upload HTTP "+r.status));return body;})
    .then(result=>{
      selectedFile=null;const input=q("#documents-file");if(input)input.value="";
      handleFile(null);return load().then(()=>openDocument(result.document_id));
    })
    .catch(err=>window.alert("Документ не изучен: "+(err.message||err)))
    .finally(()=>{if(button){button.disabled=false;button.textContent="Загрузить и изучить";}});
}

function openDocument(id){
  fetch("/api/assistant/documents/detail/"+encodeURIComponent(id)+"?scope=personal",{cache:"no-store"})
    .then(r=>{if(!r.ok)throw new Error("Document detail HTTP "+r.status);return r.json();})
    .then(renderDetail).catch(err=>window.alert("Карточка документа не открыта: "+(err.message||err)));
}
function renderDetail(data){
  const modal=q("#documents-modal");if(!modal)return;
  const d=data.document||{};
  setText("#documents-modal-title",d.filename||("Document #"+d.id));
  const meta=q("#documents-detail-meta");
  if(meta)meta.innerHTML=[
    ["Status",statusLabel(d.status)],["Quality",pct01(d.quality_score)],["Coverage",pct01(d.extraction_coverage)],["SHA-256",(d.sha256||"").slice(0,16)+"…"],
    ["Pages",n(d.page_count)],["Sections",n(d.section_count)],["Chunks",n(d.chunk_count)],["Facts",n(d.fact_count)]
  ].map(x=>'<article><span>'+esc(x[0])+'</span><strong>'+esc(x[1])+'</strong></article>').join("");
  const chunks=q("#documents-detail-chunks");
  if(chunks)chunks.innerHTML=(data.chunks||[]).slice(0,40).map(x=>{const p=x.provenance||{};return '<article class="documents-chunk"><strong>Chunk #'+x.id+' · page '+(p.page||"—")+' · '+esc(p.heading||"")+'</strong><p>'+esc(x.text_content)+'</p></article>';}).join("")||'<div class="documents-empty">Текстовых chunks нет.</div>';
  const facts=q("#documents-detail-facts");
  if(facts)facts.innerHTML=(data.facts||[]).slice(0,40).map(x=>'<article class="document-fact"><div><strong>'+esc(x.subject)+' · '+esc(x.predicate)+'</strong><small>'+esc(x.value)+'</small></div><div class="documents-scorebox"><strong>'+pct01(x.confidence)+'</strong></div></article>').join("")||'<div class="documents-empty">Фактов нет.</div>';
  const repro=q("#documents-reprocess");if(repro)repro.dataset.documentId=d.id;
  modal.classList.add("open");
}
function closeModal(){q("#documents-modal")?.classList.remove("open");}
function reprocess(){
  const id=Number(q("#documents-reprocess")?.dataset.documentId||0);if(!id)return;
  const b=q("#documents-reprocess");if(b){b.disabled=true;b.textContent="Переизучаю…";}
  fetch("/api/assistant/documents/"+id+"/reprocess",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({scope:"personal",enrich_with_ai:q("#documents-ai-enrich")?.checked||false,build_semantic_index:q("#documents-semantic-index")?.checked||false})})
    .then(async r=>{const body=await r.json().catch(()=>({}));if(!r.ok)throw new Error(body.detail||("Reprocess HTTP "+r.status));return body;})
    .then(()=>load().then(()=>openDocument(id))).catch(err=>window.alert("Переизучение не выполнено: "+(err.message||err)))
    .finally(()=>{if(b){b.disabled=false;b.textContent="Переизучить";}});
}

function search(){
  const input=q("#documents-search-input");const query=(input?.value||"").trim();if(!query)return;
  const host=q("#documents-results");if(host)host.innerHTML='<div class="documents-empty">Ищу по знаниям…</div>';
  fetch("/api/assistant/documents/search?scope=personal&limit=16&query="+encodeURIComponent(query),{cache:"no-store"})
    .then(r=>{if(!r.ok)throw new Error("Search HTTP "+r.status);return r.json();})
    .then(items=>{
      if(!host)return;
      host.innerHTML=(items||[]).map(x=>{const p=x.provenance||{};return '<article class="document-result"><strong>'+esc(x.filename)+' · D'+x.document_id+'/C'+x.chunk_id+'</strong><p>'+esc(x.text)+'</p><small>'+esc(x.method)+' · relevance '+pct01(x.score)+' · page '+(p.page||"—")+' · quality '+pct01(x.document_quality)+'</small></article>';}).join("")||'<div class="documents-empty">По запросу ничего не найдено.</div>';
    }).catch(err=>{if(host)host.innerHTML='<div class="documents-empty">'+esc(err.message||err)+'</div>';});
}

function boot(){
  q("#documents-file")?.addEventListener("change",e=>handleFile(e.target.files&&e.target.files[0]));
  q("#documents-upload-btn")?.addEventListener("click",upload);
  q("#documents-search-btn")?.addEventListener("click",search);
  q("#documents-search-input")?.addEventListener("keydown",e=>{if(e.key==="Enter")search();});
  q("#documents-modal-close")?.addEventListener("click",closeModal);
  q("#documents-modal")?.addEventListener("click",e=>{if(e.target.id==="documents-modal")closeModal();});
  q("#documents-reprocess")?.addEventListener("click",reprocess);
  load();
}
window.AISHIN_DOCUMENTS_REFRESH=load;
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();