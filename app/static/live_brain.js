(function () {
  "use strict";

  var current = null;
  var loading = false;
  var lastLoadedAt = 0;

  function el(selector) {
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
    if (value == null || value === "") return "—";
    var number = Number(value);
    if (!Number.isFinite(number)) return "—";
    if (number <= 1) number = number * 100;
    return number.toFixed(number < 10 ? 1 : 0) + "%";
  }

  function timeText(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(11, 19);
    return date.toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  }

  function compact(value) {
    var number = n(value);
    if (number >= 1000000) return (number / 1000000).toFixed(1) + "M";
    if (number >= 1000) return (number / 1000).toFixed(1) + "K";
    return String(Math.round(number));
  }

  function ensureObservatory() {
    var content = el(".technical-content");
    if (!content || el("#live-brain-observatory")) return;

    var host = document.createElement("section");
    host.id = "live-brain-observatory";
    host.className = "live-brain-observatory";
    host.innerHTML = [
      '<div class="live-brain-top">',
        '<div class="live-brain-title">',
          '<div id="live-brain-orb" class="live-brain-orb" aria-hidden="true"></div>',
          '<div>',
            '<p class="overline">AISHIN 00.00.06 · LIVE BRAIN</p>',
            '<h3>Нейронная обсерватория Айшин</h3>',
            '<p>Живые события, память, связи, проверки, качество и безопасная техническая трасса.</p>',
          '</div>',
        '</div>',
        '<div class="live-brain-actions">',
          '<span id="live-brain-runtime" class="live-brain-badge">runtime —</span>',
          '<span id="live-brain-status" class="live-brain-status-pill initializing">инициализация</span>',
          '<button id="live-brain-export" class="live-brain-export" type="button">Экспорт JSON</button>',
        '</div>',
      '</div>',
      '<div class="live-brain-metrics">',
        '<article class="live-brain-metric"><span>События · 1 час</span><strong id="lb-events-hour">0</strong><small id="lb-events-5m">0 за 5 минут</small></article>',
        '<article class="live-brain-metric"><span>Каналы</span><strong id="lb-active-channels">0/24</strong><small id="lb-attention-channels">0 требуют внимания</small></article>',
        '<article class="live-brain-metric"><span>Память</span><strong id="lb-memory-count">0</strong><small>активных записей</small></article>',
        '<article class="live-brain-metric"><span>Граф знаний</span><strong id="lb-entity-count">0</strong><small id="lb-relation-count">0 связей</small></article>',
        '<article class="live-brain-metric"><span>Развитие</span><strong id="lb-development-score">—</strong><small id="lb-development-delta">история накапливается</small></article>',
        '<article class="live-brain-metric"><span>Интеллект</span><strong id="lb-intelligence-score">—</strong><small id="lb-intelligence-route">router ещё не работал</small></article>',
      '</div>',
      '<div class="live-brain-columns">',
        '<article class="live-brain-panel">',
          '<div class="live-brain-panel-head"><strong>24 когнитивных контура</strong><span id="lb-current-phase">фаза: idle</span></div>',
          '<svg id="live-brain-topology" class="live-brain-topology" viewBox="0 0 720 330" role="img" aria-label="Живая карта когнитивных контуров Айшин"></svg>',
        '</article>',
        '<article class="live-brain-panel">',
          '<div class="live-brain-panel-head"><strong>Поток событий</strong><span id="lb-event-total">0 всего</span></div>',
          '<div id="live-brain-stream" class="live-brain-stream"><div class="live-brain-skeleton">Собираю телеметрию…</div></div>',
        '</article>',
      '</div>',
      '<article class="live-brain-trace">',
        '<div class="live-brain-panel-head"><strong>Безопасная трасса последнего решения</strong><span id="lb-trace-id">нет трассы</span></div>',
        '<p id="lb-trace-policy" class="live-brain-trace-note">Показываются только технические сигналы и источники.</p>',
        '<div id="live-brain-trace-grid" class="live-brain-trace-grid"></div>',
      '</article>',
      '<div class="live-brain-columns">',
        '<article class="live-brain-panel">',
          '<div class="live-brain-panel-head"><strong>Живой граф знаний</strong><span id="lb-graph-caption">0 сущностей</span></div>',
          '<svg id="live-brain-graph" class="live-brain-graph" viewBox="0 0 520 230" role="img" aria-label="Фрагмент графа знаний"></svg>',
        '</article>',
        '<article class="live-brain-panel">',
          '<div class="live-brain-panel-head"><strong>Целостность контура</strong><span>только реальные данные</span></div>',
          '<div id="lb-integrity-list" class="live-brain-stream"></div>',
        '</article>',
      '</div>'
    ].join("");

    var flow = el("#brain-flow");
    if (flow) {
      content.insertBefore(host, flow);
    } else {
      content.appendChild(host);
    }

    var exportButton = el("#live-brain-export");
    if (exportButton) exportButton.addEventListener("click", exportBrain);
  }

  function ensureDevelopmentStrip() {
    var hero = el("#development-module .development-hero");
    if (!hero || el("#live-brain-dev-strip")) return;
    var strip = document.createElement("section");
    strip.id = "live-brain-dev-strip";
    strip.className = "live-brain-dev-strip";
    strip.innerHTML = [
      '<article><span>Активные контуры</span><strong id="lb-dev-active">0 / 24</strong></article>',
      '<article><span>События за час</span><strong id="lb-dev-events">0</strong></article>',
      '<article><span>Качество решения</span><strong id="lb-dev-quality">—</strong></article>',
      '<article><span>Целостность мозга</span><strong id="lb-dev-integrity">—</strong></article>'
    ].join("");
    hero.insertAdjacentElement("afterend", strip);
  }

  function ensureSettingsCard() {
    var settings = el(".settings-page");
    if (!settings || el("#live-brain-settings-card")) return;
    var card = document.createElement("article");
    card.id = "live-brain-settings-card";
    card.className = "settings-card live-brain-settings-card";
    card.innerHTML = [
      '<div class="settings-card-head">',
        '<div><span class="settings-icon">⌘</span><div><h3>Диагностика мозга Айшин</h3><p>Машиночитаемый отчёт реального состояния когнитивных контуров.</p></div></div>',
        '<span id="lb-settings-status" class="settings-badge">—</span>',
      '</div>',
      '<p class="settings-note">Экспорт содержит события, безопасную трассу, метрики развития, граф знаний и состояние 24 контуров. Скрытая цепочка рассуждений в отчёт не включается.</p>',
      '<div class="settings-actions"><button id="lb-settings-export" class="primary-button" type="button">Скачать отчёт мозга JSON</button></div>'
    ].join("");
    settings.appendChild(card);
    var button = el("#lb-settings-export");
    if (button) button.addEventListener("click", exportBrain);
  }

  function setText(selector, value) {
    var node = el(selector);
    if (node) node.textContent = value;
  }

  function renderTopology(data) {
    var svg = el("#live-brain-topology");
    if (!svg) return;
    var channels = Array.isArray(data.channels) ? data.channels : [];
    var cx = 360;
    var cy = 165;
    var rx = 270;
    var ry = 118;
    var edges = [];
    var nodes = [];

    channels.forEach(function (channel, index) {
      var angle = (Math.PI * 2 * index / Math.max(1, channels.length)) - Math.PI / 2;
      var x = cx + Math.cos(angle) * rx;
      var y = cy + Math.sin(angle) * ry;
      var status = channel.status || "idle";
      var edgeClass = status === "active" ? "live-brain-edge active" : "live-brain-edge";
      edges.push('<line class="' + edgeClass + '" x1="' + cx + '" y1="' + cy + '" x2="' + x.toFixed(1) + '" y2="' + y.toFixed(1) + '"></line>');
      nodes.push(
        '<g><circle class="live-brain-node-dot ' + esc(status) + '" cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="13"><title>' +
        esc(channel.label + " — " + channel.detail) + '</title></circle>' +
        '<text class="live-brain-node-index" x="' + x.toFixed(1) + '" y="' + (y - 2).toFixed(1) + '">' + String(channel.index).padStart(2, "0") + '</text>' +
        '<text class="live-brain-node-label" x="' + x.toFixed(1) + '" y="' + (y + 24).toFixed(1) + '">' + esc(channel.label) + '</text></g>'
      );
    });

    var phase = (data.pulse && data.pulse.phase) || "idle";
    svg.innerHTML = edges.join("") +
      '<circle class="live-brain-core-ring" cx="' + cx + '" cy="' + cy + '" r="56"></circle>' +
      '<circle class="live-brain-core-ring" cx="' + cx + '" cy="' + cy + '" r="43" opacity=".55"></circle>' +
      '<text class="live-brain-core-text" x="' + cx + '" y="' + (cy - 2) + '">АЙШИН</text>' +
      '<text class="live-brain-core-sub" x="' + cx + '" y="' + (cy + 13) + '">' + esc(phase) + '</text>' +
      nodes.join("");
  }

  function renderLegacyChannels(data) {
    var channels = Array.isArray(data.channels) ? data.channels : [];
    channels.forEach(function (channel) {
      var node = document.querySelector('[data-brain-node="' + channel.id + '"]');
      if (!node) return;
      node.classList.toggle("active", channel.status === "active");
      node.classList.toggle("attention", channel.status === "attention");
      var detail = node.querySelector("em");
      if (detail) detail.textContent = channel.detail || "ожидание";
    });
    if (data.pulse) {
      setText("#brain-focus-value", data.pulse.phase || "idle");
    }
  }

  function renderEvents(data) {
    var host = el("#live-brain-stream");
    if (!host) return;
    var events = Array.isArray(data.event_stream) ? data.event_stream : [];
    if (!events.length) {
      host.innerHTML = '<div class="live-brain-empty">События ещё не накоплены.</div>';
      return;
    }
    host.innerHTML = events.slice(0, 22).map(function (item) {
      var summary = item.summary || {};
      var phase = summary.phase ? " · " + summary.phase : "";
      var extra = summary.mode ? " · " + summary.mode : "";
      var importance = n(item.importance);
      var cls = item.event_type === "cognition.phase" ? " live" : (importance >= 0.8 ? " high" : "");
      return '<article class="live-brain-event' + cls + '">' +
        '<span class="live-brain-event-dot"></span>' +
        '<div><strong>' + esc(item.event_type || "event") + '</strong><small>' +
        esc((summary.intent || summary.status || "") + phase + extra) +
        '</small></div><time>' + esc(timeText(item.created_at)) + '</time></article>';
    }).join("");
  }

  function renderTrace(data) {
    var host = el("#live-brain-trace-grid");
    var trace = data.safe_trace || {};
    if (!host) return;
    setText("#lb-trace-policy", trace.policy || data.trace_policy || "");
    setText("#lb-trace-id", trace.available ? ("trace " + String(trace.request_id || "").slice(0, 8)) : "нет трассы");
    if (!trace.available) {
      host.innerHTML = '<div class="live-brain-empty">Трасса появится после первого обработанного запроса.</div>';
      return;
    }
    var cards = [
      ["Режим", trace.mode || "—"],
      ["Уверенность", pct(trace.logic_confidence)],
      ["Источники памяти", String(n(trace.memory_sources))],
      ["Доказательства", String(n(trace.evidence_items))],
      ["Перепроверка", trace.verification_ran ? ("да · " + n(trace.verification_unresolved) + " нереш.") : "не требовалась"],
      ["Качество", pct(trace.decision_quality)],
      ["Провайдер", trace.provider || "fallback"],
      ["Задержка", trace.total_ms != null ? (n(trace.total_ms) + " мс") : "—"],
      ["Узкое место", trace.bottleneck || "—"],
      ["Метакогниция", trace.metacognition_status || "—"],
      ["Противоречия", String(n(trace.contradictions))],
      ["Нерешённое", String(n(trace.unresolved))],
      ["Тип задачи", trace.task_family || "—"],
      ["Adaptive mode", trace.adapted_mode ? ((trace.base_mode || "—") + " → " + trace.adapted_mode) : "—"],
      ["Route confidence", trace.route_confidence == null ? "—" : pct(trace.route_confidence)],
      ["Перенос опыта", trace.transfer_used ? "да" : "нет"]
    ];
    host.innerHTML = cards.map(function (item) {
      return '<article><span>' + esc(item[0]) + '</span><strong>' + esc(item[1]) + '</strong></article>';
    }).join("");
  }

  function renderGraph(data) {
    var svg = el("#live-brain-graph");
    if (!svg) return;
    var graph = data.knowledge_graph || {};
    var entities = Array.isArray(graph.entities) ? graph.entities : [];
    var relations = Array.isArray(graph.relations) ? graph.relations : [];
    var stats = graph.stats || {};
    setText("#lb-graph-caption", compact(stats.entities) + " сущностей · " + compact(stats.relations) + " связей");
    if (!entities.length) {
      svg.innerHTML = '<text x="260" y="115" text-anchor="middle" fill="#9a908c" font-size="9">Граф знаний ещё пуст</text>';
      return;
    }

    var positions = {};
    var cx = 260;
    var cy = 115;
    var rx = 190;
    var ry = 78;
    entities.forEach(function (item, index) {
      var angle = (Math.PI * 2 * index / entities.length) - Math.PI / 2;
      positions[String(item.id)] = {
        x: cx + Math.cos(angle) * rx,
        y: cy + Math.sin(angle) * ry
      };
    });

    var lines = [];
    relations.forEach(function (item) {
      var a = positions[String(item.source_id)];
      var b = positions[String(item.target_id)];
      if (!a || !b) return;
      lines.push('<line class="live-graph-edge" x1="' + a.x.toFixed(1) + '" y1="' + a.y.toFixed(1) + '" x2="' + b.x.toFixed(1) + '" y2="' + b.y.toFixed(1) + '"><title>' + esc(item.type || "связь") + '</title></line>');
    });

    var nodes = entities.map(function (item) {
      var p = positions[String(item.id)];
      var name = String(item.name || "сущность");
      var shortName = name.length > 18 ? name.slice(0, 16) + "…" : name;
      return '<g><circle class="live-graph-node" cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="10"><title>' +
        esc((item.type || "entity") + ": " + name) + '</title></circle>' +
        '<text class="live-graph-label" x="' + p.x.toFixed(1) + '" y="' + (p.y + 20).toFixed(1) + '">' + esc(shortName) + '</text></g>';
    });

    svg.innerHTML = lines.join("") + nodes.join("");
  }

  function renderIntegrity(data) {
    var host = el("#lb-integrity-list");
    if (!host) return;
    var integrity = data.integrity || {};
    var pulse = data.pulse || {};
    var rows = [
      ["Состояние", integrity.status || "—"],
      ["Ошибки подсистем", String(n(integrity.module_errors))],
      ["Нерешённые сигналы", String(n(integrity.unresolved_signals))],
      ["События внимания · 1ч", String(n(integrity.attention_events_1h))],
      ["Открытые задачи", String(n(pulse.open_tasks))],
      ["Открытые цели", String(n(pulse.open_goals))]
    ];
    host.innerHTML = rows.map(function (row, index) {
      return '<article class="live-brain-event' + (index > 0 && n(row[1]) > 0 ? " high" : "") + '">' +
        '<span class="live-brain-event-dot"></span><div><strong>' + esc(row[0]) + '</strong><small>' + esc(row[1]) + '</small></div></article>';
    }).join("");

    var errors = Array.isArray(integrity.errors) ? integrity.errors : [];
    if (errors.length) {
      host.innerHTML += errors.slice(0, 4).map(function (item) {
        return '<article class="live-brain-event high"><span class="live-brain-event-dot"></span><div><strong>' +
          esc(item.subsystem || "subsystem") + '</strong><small>' + esc(item.error || "error") + ": " + esc(item.message || "") +
          '</small></div></article>';
      }).join("");
    }
  }

  function renderDevelopmentStrip(data) {
    var pulse = data.pulse || {};
    var trace = data.safe_trace || {};
    var integrity = data.integrity || {};
    setText("#lb-dev-active", n(pulse.active_channels) + " / 24");
    setText("#lb-dev-events", compact(pulse.events_1h));
    setText("#lb-dev-quality", trace.available ? pct(trace.decision_quality) : "—");
    setText("#lb-dev-integrity", integrity.status || "—");
  }

  function render(data) {
    current = data;
    var pulse = data.pulse || {};
    var integrity = data.integrity || {};
    var graph = data.knowledge_graph || {};
    var stats = graph.stats || {};
    var development = data.development || {};
    var counters = development.counters || {};
    var intelligence = data.cognitive_intelligence || {};
    var intelligenceCurrent = intelligence.current || {};
    var intelligenceRoute = intelligence.latest_route || {};

    setText("#live-brain-runtime", data.runtime_version || "runtime");
    setText("#live-brain-status", integrity.status || "—");
    setText("#lb-events-hour", compact(pulse.events_1h));
    setText("#lb-events-5m", compact(pulse.events_5m) + " за 5 минут");
    setText("#lb-active-channels", n(pulse.active_channels) + "/24");
    setText("#lb-attention-channels", n(pulse.attention_channels) + " требуют внимания");
    setText("#lb-memory-count", compact(counters.active_memories));
    setText("#lb-entity-count", compact(stats.entities));
    setText("#lb-relation-count", compact(stats.relations) + " связей");
    setText("#lb-development-score", development.overall_score == null ? "—" : Number(development.overall_score).toFixed(1) + "%");
    setText("#lb-development-delta", development.monthly_delta == null ? "история накапливается" : ((n(development.monthly_delta) >= 0 ? "+" : "") + n(development.monthly_delta).toFixed(1) + " п.п. / 30 дней"));
    setText("#lb-intelligence-score", intelligenceCurrent.overall_score == null ? "—" : n(intelligenceCurrent.overall_score).toFixed(1) + "%");
    setText("#lb-intelligence-route", intelligenceRoute.id ? ((intelligenceRoute.task_family || "general") + " · " + (intelligenceRoute.adapted_mode || intelligenceRoute.base_mode || "—")) : "router ещё не работал");
    setText("#lb-current-phase", "фаза: " + (pulse.phase || "idle"));
    setText("#lb-event-total", compact(pulse.events_total) + " всего");

    var status = el("#live-brain-status");
    var orb = el("#live-brain-orb");
    if (status) {
      status.classList.remove("healthy", "attention", "initializing");
      status.classList.add(integrity.status || "initializing");
    }
    if (orb) {
      orb.classList.remove("healthy", "attention", "initializing");
      orb.classList.add(integrity.status || "initializing");
    }

    var settingsStatus = el("#lb-settings-status");
    if (settingsStatus) {
      settingsStatus.textContent = integrity.status || "—";
      settingsStatus.classList.toggle("ok", integrity.status === "healthy");
      settingsStatus.classList.toggle("error", integrity.status === "attention");
    }

    renderTopology(data);
    renderLegacyChannels(data);
    renderEvents(data);
    renderTrace(data);
    renderGraph(data);
    renderIntegrity(data);
    renderDevelopmentStrip(data);
  }

  function shouldRefresh() {
    var technical = el(".technical-brain");
    var development = el("#development-module");
    var settings = el("#settings-module");
    if (document.hidden) return false;
    return Boolean(
      (technical && technical.open) ||
      (development && development.classList.contains("active")) ||
      (settings && settings.classList.contains("active"))
    );
  }

  function loadBrain(force) {
    if (loading) return Promise.resolve(current);
    if (!force && Date.now() - lastLoadedAt < 1800) return Promise.resolve(current);
    loading = true;
    return fetch("/api/assistant/live-brain?scope=personal&event_limit=50&graph_limit=20", {
      cache: "no-store"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("Live Brain HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        lastLoadedAt = Date.now();
        render(data);
        return data;
      })
      .catch(function (error) {
        var status = el("#live-brain-status");
        if (status) {
          status.textContent = "ошибка телеметрии";
          status.classList.add("attention");
        }
        var stream = el("#live-brain-stream");
        if (stream && !current) {
          stream.innerHTML = '<div class="live-brain-empty">' + esc(error.message || error) + '</div>';
        }
        return null;
      })
      .finally(function () {
        loading = false;
      });
  }

  function exportBrain() {
    fetch("/api/assistant/live-brain/export?scope=personal", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("Export HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        var blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json;charset=utf-8"
        });
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        var stamp = new Date().toISOString().replace(/[:.]/g, "-");
        a.href = url;
        a.download = "AISHIN_LIVE_BRAIN_" + stamp + ".json";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 500);
      })
      .catch(function (error) {
        window.alert("Не удалось создать отчёт мозга: " + (error.message || error));
      });
  }

  function boot() {
    ensureObservatory();
    ensureDevelopmentStrip();
    ensureSettingsCard();

    var technical = el(".technical-brain");
    if (technical) {
      technical.addEventListener("toggle", function () {
        if (technical.open) loadBrain(true);
      });
    }

    var form = el("#chat-form");
    if (form) {
      form.addEventListener("submit", function () {
        setTimeout(function () { loadBrain(true); }, 250);
        setTimeout(function () { loadBrain(true); }, 1600);
      });
    }

    var developmentOpen = el("#development-open");
    if (developmentOpen) {
      developmentOpen.addEventListener("click", function () {
        setTimeout(function () { loadBrain(true); }, 80);
      });
    }

    loadBrain(true);
    window.setInterval(function () {
      if (shouldRefresh()) loadBrain(false);
    }, 5000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
