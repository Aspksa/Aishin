(function () {
  "use strict";

  var data = null;
  var loading = false;

  function q(s) { return document.querySelector(s); }
  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
  function n(v) {
    var x = Number(v || 0);
    return Number.isFinite(x) ? x : 0;
  }
  function pct(v) { return n(v).toFixed(1) + "%"; }
  function pct01(v) { return (n(v) * 100).toFixed(0) + "%"; }
  function timeText(v) {
    if (!v) return "—";
    var d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v).slice(0, 19);
    return d.toLocaleString("ru-RU", {
      day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"
    });
  }
  function setText(s, v) {
    var el = q(s); if (el) el.textContent = v;
  }
  function familyLabel(v) {
    return {
      documents:"Документы", fuel:"ГСМ", vehicles:"Автотранспорт",
      timesheet:"Табель", software:"Разработка", diagnostics:"Диагностика",
      planning:"Планирование", analysis:"Аналитика",
      knowledge:"Память и знания", general:"Общий контекст"
    }[v] || v || "—";
  }

  function ensureHomeCard() {
    var panel = q(".today-panel");
    if (!panel || q("#evolution-home-card")) return;
    var card = document.createElement("button");
    card.type = "button";
    card.id = "evolution-home-card";
    card.className = "evolution-home-card";
    card.innerHTML =
      '<div class="evolution-home-head"><strong>Эволюция Айшин</strong><span>∞</span></div>' +
      '<div class="evolution-home-stats">' +
        '<div><strong id="eh-generation">G1</strong><small>поколение</small></div>' +
        '<div><strong id="eh-score">0%</strong><small>evolution</small></div>' +
        '<div><strong id="eh-champions">0</strong><small>champions</small></div>' +
      '</div>';
    card.addEventListener("click", function () {
      var nav = document.querySelector('.nav-item[data-module="evolution"]');
      if (nav) nav.click();
    });
    var proactive = q("#proactive-home-card");
    if (proactive) proactive.insertAdjacentElement("afterend", card);
    else panel.prepend(card);
  }

  function renderHero(payload) {
    var s = payload.summary || {};
    var score = Math.max(0, Math.min(100, n(s.evolution_score)));
    var orbit = q("#evolution-orbit");
    if (orbit) orbit.style.setProperty("--evo-score", score);
    setText("#evolution-score", score.toFixed(1) + "%");
    setText("#evolution-generation", "G" + Math.max(1, n(s.generation)));
    setText("#evolution-stability", pct(s.stability_score));
    setText("#evolution-plasticity", pct(s.plasticity_score));
    setText("#evolution-velocity", pct(s.learning_velocity));
    setText("#evolution-champions", n(s.champions));
    setText("#evolution-challengers", n(s.challengers));
    setText("#evolution-curriculum-count", n(s.open_curriculum));
    setText("#evolution-transfers-count", n(s.trusted_transfers));
    setText("#evolution-rollbacks", n(s.rollback_count));
    setText("#eh-generation", "G" + Math.max(1, n(s.generation)));
    setText("#eh-score", score.toFixed(0) + "%");
    setText("#eh-champions", n(s.champions));
  }

  function renderCapabilities(items) {
    var host = q("#evolution-capabilities");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    if (!items.length) {
      host.innerHTML = '<div class="evolution-empty">Для карты способностей пока недостаточно завершённых маршрутов.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 20).map(function (x) {
      var fit = Math.max(0, Math.min(100, n(x.fitness) * 100));
      var gap = Math.max(0, Math.min(100, n(x.learning_gap) * 100));
      var trend = n(x.trend);
      var trendClass = trend > .015 ? "up" : trend < -.015 ? "down" : "";
      var sign = trend > 0 ? "+" : "";
      return '<article class="capability-card">' +
        '<div><strong>' + esc(x.label || familyLabel(x.family)) + '</strong>' +
          '<small>' + n(x.sample_count) + ' samples · confidence ' + pct01(x.confidence) + '</small></div>' +
        '<div class="capability-bars">' +
          '<small>fitness ' + fit.toFixed(0) + '%</small>' +
          '<div class="capability-bar"><i style="width:' + fit.toFixed(1) + '%"></i></div>' +
          '<small>learning gap ' + gap.toFixed(0) + '%</small>' +
          '<div class="capability-bar"><i style="width:' + gap.toFixed(1) + '%"></i></div>' +
        '</div>' +
        '<div class="capability-meta"><strong>' + fit.toFixed(0) + '%</strong>' +
          '<small class="trend ' + trendClass + '">' + sign + (trend * 100).toFixed(1) + '% trend</small>' +
          '<small>unresolved ' + pct01(x.unresolved_rate) + '</small></div>' +
      '</article>';
    }).join("");
  }

  function policyText(policy) {
    policy = policy || {};
    var parts = [];
    if (policy.preferred_mode) parts.push("mode " + policy.preferred_mode);
    parts.push("context ×" + n(policy.context_multiplier || 1).toFixed(2));
    if (policy.verification_bias) parts.push("verification bias");
    return parts.join(" · ");
  }

  function renderVariants(items) {
    var host = q("#evolution-variants");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    var visible = items.filter(function (x) {
      return ["champion","challenger","rolled_back","retired"].indexOf(x.lifecycle) >= 0;
    });
    if (!visible.length) {
      host.innerHTML = '<div class="evolution-empty">Evolution policies появятся после достаточного outcome evidence.</div>';
      return;
    }
    host.innerHTML = visible.slice(0, 30).map(function (x) {
      var lifecycle = String(x.lifecycle || "shadow");
      var observed = n(x.observed_fitness);
      var baseline = n(x.baseline_fitness);
      var gain = observed - baseline;
      return '<article class="variant-card">' +
        '<div class="variant-badge ' + esc(lifecycle) + '">' + esc(lifecycle.toUpperCase()) + '<br>G' + n(x.generation) + '</div>' +
        '<div class="variant-main"><strong>' + esc(familyLabel(x.family)) + '</strong>' +
          '<p>' + esc(policyText(x.policy)) + '</p>' +
          '<div class="variant-tags">' +
            '<span class="variant-tag">evidence ' + n(x.evidence_count) + '</span>' +
            '<span class="variant-tag">wins ' + n(x.wins) + '</span>' +
            '<span class="variant-tag">losses ' + n(x.losses) + '</span>' +
            '<span class="variant-tag">unresolved ' + n(x.unresolved_total) + '</span>' +
          '</div></div>' +
        '<div class="variant-score"><strong>' + pct01(observed) + '</strong><small>' +
          (gain >= 0 ? "+" : "") + (gain * 100).toFixed(1) + '% vs baseline</small></div>' +
      '</article>';
    }).join("");
  }

  function renderCurriculum(items) {
    var host = q("#evolution-curriculum");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    var visible = items.filter(function (x) {
      return x.status === "open" || x.status === "active";
    });
    if (!visible.length) {
      host.innerHTML = '<div class="evolution-empty">Сейчас нет измеренных пробелов, требующих отдельного curriculum.</div>';
      return;
    }
    host.innerHTML = visible.slice(0, 24).map(function (x, index) {
      var progress = Math.max(0, Math.min(100, n(x.progress) * 100));
      return '<article class="curriculum-item">' +
        '<div class="curriculum-rank">' + (index + 1) + '</div>' +
        '<div><strong>' + esc(x.title) + '</strong><p>' + esc(x.reason) +
        '</p><p>metric: ' + esc(x.expected_metric) + ' · evidence ' + n(x.evidence_count) + '</p></div>' +
        '<div class="curriculum-progress"><strong>' + progress.toFixed(0) + '%</strong>' +
          '<small>progress · priority ' + n(x.priority).toFixed(2) + '</small></div>' +
      '</article>';
    }).join("");
  }

  function renderTransfers(items) {
    var host = q("#evolution-transfers");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    if (!items.length) {
      host.innerHTML = '<div class="evolution-empty">Подтверждённый перенос навыков между областями ещё накапливается.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 24).map(function (x) {
      return '<article class="transfer-item"><div>' +
        '<div class="transfer-path"><span>' + esc(familyLabel(x.source_family)) + '</span><i>→</i><span>' +
          esc(familyLabel(x.target_family)) + '</span></div>' +
        '<small>skill #' + esc(x.skill_id) + ' · ' + esc(x.status) + ' · evidence ' + n(x.evidence_count) + '</small>' +
        '</div><div class="transfer-score"><strong>' + pct01(x.success_rate) + '</strong>' +
          '<span>confidence ' + pct01(x.confidence) + '</span></div></article>';
    }).join("");
  }

  function renderHistory(cycles) {
    var svg = q("#evolution-history");
    cycles = Array.isArray(cycles) ? cycles : [];
    if (!svg) return;
    var ordered = cycles.slice(0, 70).reverse();
    if (ordered.length < 2) {
      svg.innerHTML = '<text x="450" y="88" text-anchor="middle" fill="#9b918c" font-size="9">История эволюции ещё накапливается</text>';
      return;
    }
    var W=900,H=175,px=30,py=18,uw=W-px*2,uh=H-py*2;
    function X(i){return px+uw*i/Math.max(1,ordered.length-1);}
    function Y(v){return py+uh-(Math.max(0,Math.min(100,n(v)))/100)*uh;}
    var grids=[0,.25,.5,.75,1].map(function(r){
      var y=py+uh*r; return '<line class="grid" x1="'+px+'" y1="'+y.toFixed(1)+'" x2="'+(W-px)+'" y2="'+y.toFixed(1)+'"></line>';
    }).join("");
    var scorePath=ordered.map(function(x,i){return (i?"L":"M")+X(i).toFixed(1)+" "+Y(x.evolution_score).toFixed(1);}).join(" ");
    var stablePath=ordered.map(function(x,i){return (i?"L":"M")+X(i).toFixed(1)+" "+Y(x.stability_score).toFixed(1);}).join(" ");
    var dots=ordered.map(function(x,i){return '<circle class="dot" cx="'+X(i).toFixed(1)+'" cy="'+Y(x.evolution_score).toFixed(1)+'" r="3"><title>G'+x.generation+' · '+n(x.evolution_score).toFixed(1)+'%</title></circle>';}).join("");
    svg.innerHTML=grids+'<path class="stable-line" d="'+stablePath+'"></path><path class="score-line" d="'+scorePath+'"></path>'+dots;
  }

  function renderEvents(items) {
    var host=q("#evolution-events"); if(!host)return;
    items=Array.isArray(items)?items:[];
    if(!items.length){host.innerHTML='<div class="evolution-empty">Evolution events пока отсутствуют.</div>';return;}
    host.innerHTML=items.slice(0,16).map(function(x){
      var type=String(x.event_type||"event");
      var cls=type.indexOf("promoted")>=0?"promoted":type.indexOf("rollback")>=0?"rollback":"";
      return '<article class="evolution-event '+cls+'"><i></i><div><strong>'+esc(type)+'</strong><small>'+
        esc(x.subject_key||"")+' · G'+n(x.generation)+(x.score!=null?' · score '+n(x.score).toFixed(3):'')+
        '</small></div><time>'+esc(timeText(x.created_at))+'</time></article>';
    }).join("");
  }

  function renderPrinciples(items) {
    var host=q("#evolution-principles"); if(!host)return;
    items=Array.isArray(items)?items:[];
    host.innerHTML=items.map(function(x){return '<article class="evolution-principle">'+esc(x)+'</article>';}).join("");
  }

  function render(payload) {
    data=payload;
    renderHero(payload);
    renderCapabilities(payload.capabilities);
    renderVariants(payload.variants);
    renderCurriculum(payload.curriculum);
    renderTransfers(payload.transfers);
    renderHistory(payload.cycles);
    renderEvents(payload.events);
    renderPrinciples(payload.principles);
  }

  function load() {
    if (loading) return Promise.resolve(data);
    loading=true;
    return fetch("/api/assistant/evolution?scope=personal&capability_limit=40&variant_limit=80&curriculum_limit=80&transfer_limit=80&cycle_limit=80",{cache:"no-store"})
      .then(function(r){if(!r.ok)throw new Error("Evolution HTTP "+r.status);return r.json();})
      .then(function(payload){render(payload);return payload;})
      .catch(function(err){
        var host=q("#evolution-capabilities");
        if(host&&!data)host.innerHTML='<div class="evolution-empty">'+esc(err.message||err)+'</div>';
        return null;
      })
      .finally(function(){loading=false;});
  }

  function runCycle() {
    var btn=q("#evolution-cycle-btn");
    if(btn){btn.disabled=true;btn.textContent="Эволюционирую…";}
    return fetch("/api/assistant/evolution/cycle?scope=personal",{method:"POST"})
      .then(function(r){if(!r.ok)throw new Error("Evolution cycle HTTP "+r.status);return r.json();})
      .then(load)
      .catch(function(err){window.alert("Не удалось выполнить Evolution Cycle: "+(err.message||err));})
      .finally(function(){if(btn){btn.disabled=false;btn.textContent="Запустить цикл эволюции";}});
  }

  function boot() {
    ensureHomeCard();
    q("#evolution-cycle-btn")?.addEventListener("click",runCycle);
    var form=q("#chat-form");
    if(form)form.addEventListener("submit",function(){setTimeout(load,3200);});
    load();
  }

  window.AISHIN_EVOLUTION_REFRESH=load;
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);
  else boot();
})();
