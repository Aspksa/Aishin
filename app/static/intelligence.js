(function () {
  function scopeValue() {
    return window.AISHIN_SCOPE?.get?.() || "personal";
  }
  function scopeUrl(url) {
    return window.AISHIN_SCOPE?.url?.(url) || url;
  }
  const nativeFetch = window.fetch.bind(window);
  function fetchScope(url, options) {
    return nativeFetch(scopeUrl(url), options);
  }

  "use strict";

  var latestPayload = null;
  var loading = false;

  function q(selector) {
    return document.querySelector(selector);
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function n(value) {
    var number = Number(value || 0);
    return Number.isFinite(number) ? number : 0;
  }

  function pct(value) {
    if (value == null) return "—";
    var number = n(value);
    if (number <= 1) number *= 100;
    return number.toFixed(number < 10 ? 1 : 0) + "%";
  }

  function familyLabel(value) {
    return {
      documents: "Документы",
      fuel: "ГСМ",
      vehicles: "Автотранспорт",
      timesheet: "Табель",
      software: "Разработка",
      diagnostics: "Диагностика",
      planning: "Планирование",
      analysis: "Аналитика",
      knowledge: "Знания",
      general: "Общий контекст"
    }[value] || value || "—";
  }

  function setText(selector, value) {
    var node = q(selector);
    if (node) node.textContent = value;
  }

  function build() {
    var page = q("#development-module .development-page");
    if (!page || q("#cog-intel")) return;

    var root = document.createElement("section");
    root.id = "cog-intel";
    root.className = "cog-intel";
    root.innerHTML = [
      '<section class="cog-intel-hero">',
        '<div class="cog-intel-score-wrap">',
          '<div id="cog-intel-score" class="cog-intel-score"><strong id="cog-score-value">0.0%</strong><small>cognitive intelligence</small></div>',
          '<div class="cog-intel-score-label">не IQ · только измеримые способности системы</div>',
        '</div>',
        '<div class="cog-intel-copy">',
          '<p class="overline">AISHIN 00.00.06 · COGNITIVE INTELLIGENCE</p>',
          '<h3>Интеллект Айши</h3>',
          '<p>Восемь независимых способностей, рассчитанных из реальной памяти, качества решений, самопроверок, планирования, обучения и успешного применения навыков. Adaptive Skill Router теперь использует этот опыт перед каждым запросом.</p>',
          '<div class="cog-intel-badges">',
            '<span class="cog-intel-badge" id="cog-route-count">0 маршрутов</span>',
            '<span class="cog-intel-badge" id="cog-route-success">0% успешных</span>',
            '<span class="cog-intel-badge" id="cog-mode-changes">0 адаптаций режима</span>',
            '<span class="cog-intel-badge" id="cog-transfer-routes">0 переносов опыта</span>',
          '</div>',
        '</div>',
        '<div class="cog-intel-radar-wrap"><svg id="cog-radar" class="cog-intel-radar" viewBox="0 0 320 240" role="img" aria-label="Радар восьми когнитивных способностей Айши"></svg></div>',
      '</section>',
      '<div class="cog-intel-grid">',
        '<section class="cog-intel-panel wide">',
          '<div class="cog-intel-panel-head"><div><p class="overline">8 СПОСОБНОСТЕЙ</p><h4>Профиль интеллекта</h4></div><span id="cog-formula">formula —</span></div>',
          '<div id="cog-dimensions" class="cog-dimensions"></div>',
        '</section>',
        '<section class="cog-intel-panel">',
          '<div class="cog-intel-panel-head"><div><p class="overline">ADAPTIVE SKILL ROUTER</p><h4>Как обработан последний запрос</h4></div><span id="cog-route-time">—</span></div>',
          '<div id="cog-latest-route"></div>',
        '</section>',
        '<section class="cog-intel-panel">',
          '<div class="cog-intel-panel-head"><div><p class="overline">EVIDENCE</p><h4>Сильные стороны и точки роста</h4></div><span>почему именно такой score</span></div>',
          '<div id="cog-evidence-list" class="cog-evidence-list"></div>',
        '</section>',
        '<section class="cog-intel-panel">',
          '<div class="cog-intel-panel-head"><div><p class="overline">TRANSFER LEARNING</p><h4>Перенос опыта между задачами</h4></div><span id="cog-transfer-count">0 навыков</span></div>',
          '<div id="cog-transfer-list" class="cog-transfer-list"></div>',
        '</section>',
        '<section class="cog-intel-panel">',
          '<div class="cog-intel-panel-head"><div><p class="overline">RECENT ROUTES</p><h4>Последние адаптивные решения</h4></div><span id="cog-recent-count">0</span></div>',
          '<div id="cog-route-list" class="cog-route-list"></div>',
        '</section>',
        '<section class="cog-intel-panel wide">',
          '<div class="cog-intel-panel-head"><div><p class="overline">ИСТОРИЯ</p><h4>Развитие общего интеллекта</h4></div><span>снимки не чаще одного раза в час</span></div>',
          '<svg id="cog-history" class="cog-history" viewBox="0 0 900 190" role="img" aria-label="История когнитивного интеллекта Айши"></svg>',
        '</section>',
        '<section class="cog-intel-panel wide">',
          '<div class="cog-intel-panel-head"><div><p class="overline">ПРИНЦИПЫ</p><h4>Как защищаем интеллект от накрутки</h4></div></div>',
          '<div id="cog-principles" class="cog-principles"></div>',
        '</section>',
      '</div>'
    ].join("");

    var after = q("#long-growth") || q("#live-brain-dev-strip") || q("#development-module .development-hero");
    if (after) after.insertAdjacentElement("afterend", root);
    else page.appendChild(root);
  }

  function renderRadar(dimensions) {
    var svg = q("#cog-radar");
    if (!svg) return;
    var items = Object.keys(dimensions || {}).map(function (key) {
      var item = dimensions[key] || {};
      return {
        key: key,
        label: item.label || key,
        score: Math.max(0, Math.min(100, n(item.score)))
      };
    });
    if (!items.length) {
      svg.innerHTML = '<text x="160" y="120" text-anchor="middle" fill="#9a908c" font-size="11">Данные интеллекта ещё не накоплены</text>';
      return;
    }

    var cx = 160, cy = 119, radius = 82;
    var rings = [];
    [0.25, 0.5, 0.75, 1].forEach(function (scale) {
      var points = items.map(function (_, index) {
        var angle = -Math.PI / 2 + Math.PI * 2 * index / items.length;
        return [
          cx + Math.cos(angle) * radius * scale,
          cy + Math.sin(angle) * radius * scale
        ];
      });
      rings.push('<polygon class="grid" points="' + points.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ") + '"></polygon>');
    });

    var axes = [];
    var values = [];
    var labels = [];
    items.forEach(function (item, index) {
      var angle = -Math.PI / 2 + Math.PI * 2 * index / items.length;
      var ax = cx + Math.cos(angle) * radius;
      var ay = cy + Math.sin(angle) * radius;
      axes.push('<line class="axis" x1="' + cx + '" y1="' + cy + '" x2="' + ax.toFixed(1) + '" y2="' + ay.toFixed(1) + '"></line>');

      var vr = radius * (item.score / 100);
      values.push([
        cx + Math.cos(angle) * vr,
        cy + Math.sin(angle) * vr
      ]);

      var lr = radius + 22;
      var lx = cx + Math.cos(angle) * lr;
      var ly = cy + Math.sin(angle) * lr;
      labels.push(
        '<text class="label" x="' + lx.toFixed(1) + '" y="' + ly.toFixed(1) + '">' + esc(item.label) + '</text>' +
        '<text class="value" x="' + lx.toFixed(1) + '" y="' + (ly + 9).toFixed(1) + '">' + item.score.toFixed(1) + '%</text>'
      );
    });

    var shape = '<polygon class="shape" points="' + values.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ") + '"></polygon>';
    var dots = values.map(function (p, index) {
      return '<circle class="point" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="3"><title>' + esc(items[index].label) + ': ' + items[index].score.toFixed(1) + '%</title></circle>';
    }).join("");

    svg.innerHTML = rings.join("") + axes.join("") + shape + dots + labels.join("");
  }

  function renderDimensions(dimensions) {
    var host = q("#cog-dimensions");
    if (!host) return;
    var items = Object.keys(dimensions || {}).map(function (key) {
      var item = dimensions[key] || {};
      item.key = key;
      return item;
    });
    if (!items.length) {
      host.innerHTML = '<div class="cog-empty">Нет измерений.</div>';
      return;
    }
    host.innerHTML = items.map(function (item) {
      var score = Math.max(0, Math.min(100, n(item.score)));
      return '<article class="cog-dimension" style="--dimension-score:' + score + '">' +
        '<div class="cog-dimension-top"><span class="cog-dimension-icon">' + esc(item.icon || "·") + '</span><span class="cog-dimension-score">' + score.toFixed(1) + '%</span></div>' +
        '<strong>' + esc(item.label || item.key) + '</strong>' +
        '<p>' + esc(item.why || "Evidence ещё накапливается.") + '</p>' +
        '<span class="cog-dimension-weight">вес ' + n(item.weight).toFixed(0) + '%</span></article>';
    }).join("");
  }

  function renderLatestRoute(route) {
    var host = q("#cog-latest-route");
    if (!host) return;
    if (!route || !route.id) {
      host.innerHTML = '<div class="cog-empty">Маршрут появится после первого запроса в версии 00.00.06.</div>';
      setText("#cog-route-time", "нет маршрута");
      return;
    }
    setText("#cog-route-time", String(route.created_at || "").replace("T", " ").slice(0, 19));
    var skills = Array.isArray(route.selected_skill_ids) ? route.selected_skill_ids : [];
    var knowledge = Array.isArray(route.selected_knowledge_ids) ? route.selected_knowledge_ids : [];
    var transfer = Boolean(route.transfer_used);
    var outcome = route.outcome_score == null ? "—" : pct(route.outcome_score);
    var rationale = Array.isArray(route.rationale) ? route.rationale : [];
    host.innerHTML = '<article class="cog-route">' +
      '<div class="cog-route-main"><div><span class="overline">REQUEST ' + esc(String(route.request_id || "").slice(0, 8)) + '</span><h5>' + esc(familyLabel(route.task_family)) + '</h5><p>' + esc(route.intent || "conversation") + '</p></div>' +
      '<div class="cog-route-confidence"><span>route confidence</span><strong>' + pct(route.route_confidence) + '</strong></div></div>' +
      '<div class="cog-route-flow">' +
        '<div class="cog-route-step"><span>тип задачи</span><strong>' + esc(familyLabel(route.task_family)) + '</strong></div>' +
        '<div class="cog-route-step"><span>опыт</span><strong>' + skills.length + ' навыков</strong></div>' +
        '<div class="cog-route-step"><span>режим</span><strong>' + esc(route.base_mode || "—") + ' → ' + esc(route.adapted_mode || "—") + '</strong></div>' +
        '<div class="cog-route-step"><span>контекст</span><strong>×' + n(route.context_multiplier || 1).toFixed(2) + '</strong></div>' +
        '<div class="cog-route-step"><span>outcome</span><strong>' + outcome + '</strong></div>' +
      '</div>' +
      '<div class="cog-route-tags">' +
        '<span class="cog-route-tag">knowledge ' + knowledge.length + '</span>' +
        '<span class="cog-route-tag">unresolved ' + n(route.unresolved_count) + '</span>' +
        (transfer ? '<span class="cog-route-tag transfer">перенос опыта</span>' : '') +
        rationale.slice(0, 3).map(function (item) { return '<span class="cog-route-tag">' + esc(item) + '</span>'; }).join("") +
      '</div></article>';
  }

  function renderEvidence(payload) {
    var host = q("#cog-evidence-list");
    if (!host) return;
    var strengths = Array.isArray(payload.strengths) ? payload.strengths : [];
    var priorities = Array.isArray(payload.growth_priorities) ? payload.growth_priorities : [];
    var rows = strengths.map(function (item) {
      return { kind: "Сильная сторона", item: item };
    }).concat(priorities.map(function (item) {
      return { kind: "Точка роста", item: item };
    }));
    if (!rows.length) {
      host.innerHTML = '<div class="cog-empty">Evidence ещё накапливается.</div>';
      return;
    }
    host.innerHTML = rows.map(function (row) {
      return '<article class="cog-evidence"><span class="cog-evidence-score">' + n(row.item.score).toFixed(1) + '%</span><div><strong>' + esc(row.kind + " · " + row.item.label) + '</strong><small>' + esc(row.item.why || "") + '</small></div></article>';
    }).join("");
  }

  function renderTransfer(items) {
    var host = q("#cog-transfer-list");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    setText("#cog-transfer-count", items.length + " навыков");
    if (!items.length) {
      host.innerHTML = '<div class="cog-empty">Перенос будет засчитан только после успешного использования одного навыка минимум в двух типах задач.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 12).map(function (item) {
      return '<article class="cog-transfer-item"><div><strong>' + esc(item.title || ("skill:" + item.skill_id)) + '</strong><small>' +
        (item.families || []).map(familyLabel).map(esc).join(" ↔ ") +
        ' · ' + n(item.successful_uses) + ' успешных применений · outcome ' + pct(item.average_outcome) +
        '</small></div><span class="cog-transfer-breadth">' + n(item.family_count) + '×</span></article>';
    }).join("");
  }

  function renderRoutes(items) {
    var host = q("#cog-route-list");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    setText("#cog-recent-count", String(items.length));
    if (!items.length) {
      host.innerHTML = '<div class="cog-empty">Маршрутов пока нет.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 10).map(function (item) {
      var score = item.outcome_score == null ? "—" : pct(item.outcome_score);
      var state = item.successful == null ? "в процессе" : (item.successful ? "успешно" : "нужен рост");
      return '<article class="cog-transfer-item"><div><strong>' +
        esc(familyLabel(item.task_family) + " · " + (item.adapted_mode || "—")) +
        '</strong><small>' + esc((item.base_mode || "—") + " → " + (item.adapted_mode || "—")) +
        ' · confidence ' + pct(item.route_confidence) +
        ' · ' + esc(state) +
        (item.transfer_used ? ' · transfer' : '') +
        '</small></div><span class="cog-transfer-breadth">' + score + '</span></article>';
    }).join("");
  }

  function renderHistory(items) {
    var svg = q("#cog-history");
    if (!svg) return;
    items = Array.isArray(items) ? items.slice().reverse() : [];
    if (items.length < 2) {
      svg.innerHTML = '<text x="450" y="95" text-anchor="middle" fill="#9a908c" font-size="11">История интеллекта ещё накапливается</text>';
      return;
    }
    var width = 900, height = 190, px = 34, py = 22;
    var usableW = width - px * 2, usableH = height - py * 2;
    var values = items.map(function (item) { return n(item.overall_score); });
    var min = Math.max(0, Math.min.apply(null, values) - 5);
    var max = Math.min(100, Math.max.apply(null, values) + 5);
    if (max - min < 10) max = Math.min(100, min + 10);
    function X(i) { return px + usableW * i / Math.max(1, items.length - 1); }
    function Y(v) { return py + usableH - ((v - min) / Math.max(1, max - min)) * usableH; }

    var grid = [0, .25, .5, .75, 1].map(function (ratio) {
      var y = py + usableH * ratio;
      return '<line class="grid" x1="' + px + '" y1="' + y.toFixed(1) + '" x2="' + (width - px) + '" y2="' + y.toFixed(1) + '"></line>';
    }).join("");
    var path = values.map(function (value, index) {
      return (index ? "L" : "M") + X(index).toFixed(1) + " " + Y(value).toFixed(1);
    }).join(" ");
    var dots = values.map(function (value, index) {
      return '<circle class="dot" cx="' + X(index).toFixed(1) + '" cy="' + Y(value).toFixed(1) + '" r="3"><title>' + value.toFixed(1) + '%</title></circle>';
    }).join("");
    svg.innerHTML = grid + '<path class="line" d="' + path + '"></path>' + dots;
  }

  function renderPrinciples(items) {
    var host = q("#cog-principles");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    host.innerHTML = items.length
      ? items.map(function (item) { return '<article class="cog-principle">' + esc(item) + '</article>'; }).join("")
      : '<div class="cog-empty">Принципы не загружены.</div>';
  }

  function render(payload) {
    latestPayload = payload;
    var current = payload.current || {};
    var score = Math.max(0, Math.min(100, n(current.overall_score)));
    var scoreNode = q("#cog-intel-score");
    if (scoreNode) scoreNode.style.setProperty("--intel-score", score);
    setText("#cog-score-value", score.toFixed(1) + "%");
    setText("#cog-formula", current.formula_version || "formula —");

    var stats = current.route_stats || {};
    setText("#cog-route-count", n(stats.completed_routes) + " маршрутов");
    var successRate = n(stats.completed_routes)
      ? (n(stats.successful_routes) / n(stats.completed_routes)) * 100
      : 0;
    setText("#cog-route-success", successRate.toFixed(0) + "% успешных");
    setText("#cog-mode-changes", n(stats.mode_changes) + " адаптаций режима");
    setText("#cog-transfer-routes", n(stats.transfer_routes) + " переносов опыта");

    renderRadar(current.dimensions || {});
    renderDimensions(current.dimensions || {});
    renderLatestRoute(payload.latest_route || {});
    renderEvidence(payload);
    renderTransfer(payload.transfer_map || []);
    renderRoutes(payload.routes || []);
    renderHistory(payload.history || []);
    renderPrinciples(current.principles || []);
  }

  function load() {
    if (loading) return Promise.resolve(latestPayload);
    loading = true;
    return fetchScope("/api/assistant/intelligence?scope=personal&history_limit=90&route_limit=30", {
      cache: "no-store"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("Intelligence HTTP " + response.status);
        return response.json();
      })
      .then(function (payload) {
        render(payload);
        return payload;
      })
      .catch(function (error) {
        var host = q("#cog-dimensions");
        if (host && !latestPayload) {
          host.innerHTML = '<div class="cog-empty">' + esc(error.message || error) + '</div>';
        }
        return null;
      })
      .finally(function () {
        loading = false;
      });
  }

  function boot() {
    build();
    if (q("#development-module")?.classList.contains("active")) load();

    var open = q("#development-open");
    if (open) {
      open.addEventListener("click", function () {
        setTimeout(load, 160);
      });
    }

    var form = q("#chat-form");
    if (form) {
      form.addEventListener("submit", function () {
        if (q("#development-module")?.classList.contains("active")) {
          setTimeout(load, 2500);
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  window.AISHIN_INTELLIGENCE_REFRESH = load;
})();
