(function () {
  "use strict";

  var data = null;
  var loading = false;

  function q(s) { return document.querySelector(s); }
  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
  function n(v) {
    var x = Number(v || 0);
    return Number.isFinite(x) ? x : 0;
  }
  function pct01(v) {
    if (v == null) return "—";
    return Math.round(n(v) * 100) + "%";
  }
  function fixed(v) { return n(v).toFixed(1) + "%"; }
  function levelLabel(v) {
    return {
      mastered: "освоено",
      established: "устойчивый",
      forming: "формируется",
      fading: "устаревает",
      strong: "сильная",
      developing: "развивается",
      trusted: "доверенное",
      supported: "поддержано",
      provisional: "предварительное",
      stale: "устарело",
      weak: "слабое"
    }[v] || v || "—";
  }

  function build() {
    var page = q("#development-module .development-page");
    if (!page || q("#long-growth")) return;

    var root = document.createElement("section");
    root.id = "long-growth";
    root.className = "long-growth";
    root.innerHTML = [
      '<section class="long-growth-hero">',
        '<div id="long-growth-ring" class="long-growth-ring"><strong id="long-growth-score">0.0%</strong><small>долговременный рост</small></div>',
        '<div class="long-growth-copy">',
          '<p class="overline">AISHIN 00.00.05 · ДОЛГОВРЕМЕННОЕ РАЗВИТИЕ</p>',
          '<h3>Карта того, чему Айшин действительно научилась</h3>',
          '<p>Уровень строится по подтверждённым паттернам, стратегиям, качеству evidence, свежести опыта и доверию к сохранённым знаниям. Старый опыт не исчезает, но постепенно теряет вес.</p>',
          '<div class="long-growth-stats">',
            '<article class="long-growth-stat"><span>Устойчивые навыки</span><strong id="lt-durable">0</strong><small id="lt-skills-total">0 всего</small></article>',
            '<article class="long-growth-stat"><span>Освоено</span><strong id="lt-mastered">0</strong><small>только при сильном evidence</small></article>',
            '<article class="long-growth-stat"><span>Доверенные знания</span><strong id="lt-trusted">0</strong><small id="lt-avg-trust">0% среднее доверие</small></article>',
            '<article class="long-growth-stat"><span>Специализации</span><strong id="lt-specializations">0</strong><small id="lt-strong-specializations">0 сильных</small></article>',
          '</div>',
          '<div class="long-growth-toolbar"><button id="lt-refresh" class="long-growth-refresh" type="button">Пересчитать по фактам</button><span id="lt-status" class="long-growth-note">Загрузка…</span></div>',
        '</div>',
      '</section>',
      '<div class="long-growth-grid">',
        '<section class="long-growth-panel wide">',
          '<div class="long-growth-panel-head"><div><p class="overline">СПЕЦИАЛИЗАЦИИ</p><h4>Карта сильных областей</h4></div><span>глубина · ширина · доверие</span></div>',
          '<div id="lt-specialization-list" class="long-specializations"></div>',
        '</section>',
        '<section class="long-growth-panel">',
          '<div class="long-growth-panel-head"><div><p class="overline">НАВЫКИ</p><h4>Матрица мастерства</h4></div><span id="lt-skill-caption">0 навыков</span></div>',
          '<div id="lt-skill-list" class="long-skills"></div>',
        '</section>',
        '<section class="long-growth-panel">',
          '<div class="long-growth-panel-head"><div><p class="overline">ДОВЕРИЕ К ЗНАНИЯМ</p><h4>Что Айшин считает надёжным</h4></div><span id="lt-stale-caption">0 устаревших</span></div>',
          '<div id="lt-trust-list" class="long-trust-list"></div>',
        '</section>',
        '<section class="long-growth-panel wide">',
          '<div class="long-growth-panel-head"><div><p class="overline">ИСТОРИЯ</p><h4>Долговременный рост</h4></div><span>снимки не чаще раза в час</span></div>',
          '<svg id="lt-history-chart" class="long-growth-chart" viewBox="0 0 900 180" role="img" aria-label="История долговременного развития Айшин"></svg>',
        '</section>',
        '<section class="long-growth-panel wide">',
          '<div class="long-growth-panel-head"><div><p class="overline">ПРАВИЛА ЧЕСТНОГО РОСТА</p><h4>Почему этим цифрам можно верить</h4></div></div>',
          '<div id="lt-principles" class="long-growth-principles"></div>',
        '</section>',
      '</div>'
    ].join("");

    var after = q("#live-brain-dev-strip") || q("#development-module .development-hero");
    if (after) after.insertAdjacentElement("afterend", root);
    else page.appendChild(root);

    var refresh = q("#lt-refresh");
    if (refresh) refresh.addEventListener("click", function () {
      refresh.disabled = true;
      setStatus("Пересчитываю evidence, свежесть и доверие…");
      fetch("/api/assistant/growth/refresh?scope=personal", {
        method: "POST"
      })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function () { return load(); })
        .catch(function (e) { setStatus("Ошибка: " + e.message); })
        .finally(function () { refresh.disabled = false; });
    });
  }

  function setStatus(text) {
    var node = q("#lt-status");
    if (node) node.textContent = text;
  }

  function renderSummary(summary) {
    var score = n(summary.overall_score);
    var ring = q("#long-growth-ring");
    if (ring) ring.style.setProperty("--growth-score", Math.max(0, Math.min(100, score)));
    var scoreNode = q("#long-growth-score");
    if (scoreNode) scoreNode.textContent = score.toFixed(1) + "%";

    var skills = summary.skills || {};
    var knowledge = summary.knowledge || {};
    var specs = summary.specializations || {};
    q("#lt-durable").textContent = n(skills.durable);
    q("#lt-skills-total").textContent = n(skills.total) + " всего";
    q("#lt-mastered").textContent = n(skills.mastered);
    q("#lt-trusted").textContent = n(knowledge.trusted);
    q("#lt-avg-trust").textContent = pct01(knowledge.average_trust) + " среднее доверие";
    q("#lt-specializations").textContent = n(specs.total);
    q("#lt-strong-specializations").textContent = n(specs.strong) + " сильных";
    q("#lt-stale-caption").textContent = n(knowledge.stale) + " устаревших";
    q("#lt-skill-caption").textContent = n(skills.total) + " навыков";
    setStatus("Расчёт по сохранённым данным · " + (summary.version || ""));

    var principles = Array.isArray(summary.principles) ? summary.principles : [];
    q("#lt-principles").innerHTML = principles.length
      ? principles.map(function (p) {
          return '<article class="long-growth-principle">' + esc(p) + '</article>';
        }).join("")
      : '<div class="long-growth-empty">Правила не загружены.</div>';
  }

  function renderSpecializations(items) {
    var host = q("#lt-specialization-list");
    if (!host) return;
    if (!items || !items.length) {
      host.innerHTML = '<div class="long-growth-empty">Специализации появятся после накопления подтверждённых навыков.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 12).map(function (item) {
      var score = n(item.overall_score);
      var level = item.level || "forming";
      return '<article class="long-specialization" style="--spec-score:' + Math.max(0, Math.min(100, score)) + '">' +
        '<div class="spec-top"><strong>' + esc(item.label || item.specialization_key) + '</strong><b>' + score.toFixed(1) + '%</b></div>' +
        '<p>' + n(item.skill_count) + ' навыков · ' + n(item.mastered_skills) + ' освоено · evidence ' + n(item.evidence_count).toFixed(0) +
        '<br>глубина ' + pct01(item.depth_score) + ' · ширина ' + pct01(item.breadth_score) + ' · доверие ' + pct01(item.trust_score) + '</p>' +
        '<span class="long-level ' + esc(level) + '">' + esc(levelLabel(level)) + '</span></article>';
    }).join("");
  }

  function renderSkills(items) {
    var host = q("#lt-skill-list");
    if (!host) return;
    if (!items || !items.length) {
      host.innerHTML = '<div class="long-growth-empty">Навыки ещё не подтверждены learning evidence.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 18).map(function (item) {
      var score = n(item.mastery_score);
      return '<article class="long-skill">' +
        '<div class="long-skill-head"><strong>' + esc(item.title || item.skill_key) + '</strong><span class="long-skill-score">' + score.toFixed(1) + '%</span></div>' +
        '<div class="long-skill-meta"><span>' + esc(levelLabel(item.lifecycle)) + '</span><span>evidence ' + n(item.evidence_count).toFixed(0) + '</span><span>надёжность ' + pct01(item.reliability) + '</span><span>свежесть ' + pct01(item.freshness) + '</span></div>' +
        '<div class="long-skill-bar" style="--skill-score:' + Math.max(0, Math.min(100, score)) + '"><i></i></div></article>';
    }).join("");
  }

  function renderTrust(items) {
    var host = q("#lt-trust-list");
    if (!host) return;
    if (!items || !items.length) {
      host.innerHTML = '<div class="long-growth-empty">Нет знаний с явным confidence-сигналом.</div>';
      return;
    }
    var sorted = items.slice().sort(function (a, b) {
      var priority = { trusted: 0, supported: 1, provisional: 2, stale: 3, weak: 4 };
      var pa = priority[a.trust_level] == null ? 9 : priority[a.trust_level];
      var pb = priority[b.trust_level] == null ? 9 : priority[b.trust_level];
      if (pa !== pb) return pa - pb;
      return n(b.trust_score) - n(a.trust_score);
    });
    host.innerHTML = sorted.slice(0, 24).map(function (item) {
      var score = Math.round(n(item.trust_score) * 100);
      return '<article class="long-trust"><span class="long-trust-score">' + score + '%</span><div><strong>' +
        esc(item.label || item.category) + '</strong><small>' + esc(item.category || item.subject_type) +
        ' · свежесть ' + pct01(item.freshness) + ' · evidence ' + n(item.evidence_count) +
        '</small></div><span class="long-trust-level ' + esc(item.trust_level) + '">' +
        esc(levelLabel(item.trust_level)) + '</span></article>';
    }).join("");
  }

  function renderHistory(items) {
    var svg = q("#lt-history-chart");
    if (!svg) return;
    items = Array.isArray(items) ? items.slice().reverse() : [];
    if (items.length < 2) {
      svg.innerHTML = '<text x="450" y="90" text-anchor="middle" fill="#9a908c" font-size="9">История ещё накапливается</text>';
      return;
    }
    var width = 900, height = 180, px = 32, py = 20;
    var usableW = width - px * 2, usableH = height - py * 2;
    var values = items.map(function (x) { return n(x.overall_score); });
    var min = Math.max(0, Math.min.apply(null, values) - 5);
    var max = Math.min(100, Math.max.apply(null, values) + 5);
    if (max - min < 10) max = Math.min(100, min + 10);
    function X(i) { return px + (usableW * i / Math.max(1, items.length - 1)); }
    function Y(v) { return py + usableH - ((v - min) / Math.max(1, max - min)) * usableH; }
    var grid = [0, .25, .5, .75, 1].map(function (r) {
      var y = py + usableH * r;
      return '<line class="grid" x1="' + px + '" y1="' + y + '" x2="' + (width-px) + '" y2="' + y + '"></line>';
    }).join("");
    var path = values.map(function (v, i) { return (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1); }).join(" ");
    var dots = values.map(function (v, i) {
      return '<circle class="dot" cx="' + X(i).toFixed(1) + '" cy="' + Y(v).toFixed(1) + '" r="3"><title>' + v.toFixed(1) + '%</title></circle>';
    }).join("");
    svg.innerHTML = grid + '<path class="line" d="' + path + '"></path>' + dots;
  }

  function render(payload) {
    data = payload;
    renderSummary(payload.summary || {});
    renderSpecializations(payload.specializations || []);
    renderSkills(payload.skills || []);
    renderTrust(payload.knowledge || []);
    renderHistory(payload.history || []);
  }

  function load() {
    if (loading) return Promise.resolve(data);
    loading = true;
    return fetch("/api/assistant/growth?scope=personal&skill_limit=100&knowledge_limit=100&specialization_limit=50&history_limit=90", {
      cache: "no-store"
    })
      .then(function (r) {
        if (!r.ok) throw new Error("Growth HTTP " + r.status);
        return r.json();
      })
      .then(function (payload) {
        render(payload);
        return payload;
      })
      .catch(function (e) {
        setStatus("Ошибка загрузки: " + e.message);
        return null;
      })
      .finally(function () { loading = false; });
  }

  function boot() {
    build();
    load();
    var open = q("#development-open");
    if (open) open.addEventListener("click", function () {
      setTimeout(load, 120);
    });
    var form = q("#chat-form");
    if (form) form.addEventListener("submit", function () {
      setTimeout(load, 2200);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
