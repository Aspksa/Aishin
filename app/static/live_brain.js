(function () {
  "use strict";

  var current = null;
  var loading = false;
  var lastLoadedAt = 0;
  var eventSource = null;
  var reconnectTimer = null;
  var lastPulseSequence = -1;
  var lastFinishedSequence = -1;
  var selectedFlowNodeId = "";

  function scopeValue() {
    return window.AISHIN_SCOPE?.get?.() || "personal";
  }

  function scopeUrl(url) {
    return window.AISHIN_SCOPE?.url?.(url) || url;
  }

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
            '<p class="overline">AISHIN 00.00.15 · CANONICAL FACTS</p>',
            '<h3>Нейронная обсерватория Айшин</h3>',
            '<p>Реальные переходы между модулями, текущая выполняемая фаза и безопасная техническая телеметрия в реальном времени.</p>',
          '</div>',
        '</div>',
        '<div class="live-brain-actions">',
          '<span id="lb-stream-state" class="live-brain-badge">LIVE · подключение…</span>',
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
        '<article class="live-brain-metric"><span>Осведомлённость</span><strong id="lb-awareness-score">—</strong><small id="lb-awareness-incidents">0 ситуаций</small></article>',
        '<article class="live-brain-metric"><span>Эволюция</span><strong id="lb-evolution-score">—</strong><small id="lb-evolution-generation">G1 · 0 champions</small></article>',
        '<article class="live-brain-metric"><span>Исследования</span><strong id="lb-research-score">—</strong><small id="lb-research-status">0 gaps · 0 trusted</small></article>',
        '<article class="live-brain-metric"><span>Общение</span><strong id="lb-communication-score">—</strong><small id="lb-communication-status">0 evidence · persona —</small></article>',
        '<article class="live-brain-metric"><span>Документы</span><strong id="lb-documents-score">—</strong><small id="lb-documents-status">0 studied · 0 OCR</small></article>',
        '<article class="live-brain-metric"><span>Grounding ответа</span><strong id="lb-grounding-score">—</strong><small id="lb-grounding-status">ещё не измерялся</small></article>',
        '<article class="live-brain-metric"><span>Жизненный цикл знаний</span><strong id="lb-knowledge-verified">0</strong><small id="lb-knowledge-status">0 confirmed hypotheses</small></article>',
        '<article class="live-brain-metric"><span>Канонические факты</span><strong id="lb-canonical-verified">0</strong><small id="lb-canonical-status">0 conflicts · 0 history</small></article>',
      '</div>',
      '<div class="live-brain-columns">',
        '<article class="live-brain-panel">',
          '<div class="live-brain-panel-head"><strong>Нервная карта выполнения</strong><span id="lb-current-phase">фаза: idle</span></div>',
          '<div class="brain-flow-meta">',
            '<div><span>request</span><strong id="lb-flow-request">—</strong></div>',
            '<div><span>время</span><strong id="lb-flow-elapsed">—</strong></div>',
            '<div><span>параллельно</span><strong id="lb-flow-concurrency">0</strong></div>',
            '<div class="brain-flow-legend" aria-label="Легенда состояний">',
              '<span class="executing"><i></i>сейчас</span>',
              '<span class="recent"><i></i>недавно</span>',
              '<span class="idle"><i></i>ожидание</span>',
              '<span class="attention"><i></i>внимание</span>',
            '</div>',
          '</div>',
          '<svg id="live-brain-topology" class="live-brain-topology" viewBox="0 0 1080 620" role="img" aria-label="Настоящая карта переходов между модулями Айшин"></svg>',
          '<div id="lb-node-inspector" class="brain-flow-inspector" aria-live="polite"><span>Выберите узел карты, чтобы увидеть его техническое состояние.</span></div>',
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

  function stateLabel(value) {
    return ({
      executing: "выполняется",
      recent: "недавно",
      idle: "ожидание",
      attention: "внимание",
      running: "выполняется",
      completed: "завершено",
      fallback: "завершено · fallback",
      error: "ошибка",
      executed: "выполнено",
      executed_read_only: "выполнено · read-only",
      execution_failed: "ошибка исполнения",
      approval_required: "нужно подтверждение",
      blocked_by_permission: "заблокировано разрешениями",
      proposal_only: "только предложение",
      arguments_unresolved: "аргументы не подтверждены",
      preview_failed: "preview не прошёл",
      no_candidate: "кандидат не выбран",
      unknown_tool: "неизвестный инструмент"
    })[String(value || "")] || String(value || "ожидание");
  }

  function renderTopology(data) {
    var svg = el("#live-brain-topology");
    if (!svg) return;
    var topology = data.topology || {};
    var nodes = Array.isArray(topology.nodes) ? topology.nodes : [];
    var edges = Array.isArray(topology.edges) ? topology.edges : [];
    if (!nodes.length) {
      svg.innerHTML = '<text x="540" y="310" text-anchor="middle" class="live-brain-topology-empty">Телеметрия нервной карты ещё не поступила</text>';
      return;
    }

    var width = 1080;
    var height = 620;
    var padX = 58;
    var padY = 58;
    var layerValues = nodes.map(function (item) { return Number(item.layer || 0); });
    var maxLayer = Math.max.apply(null, layerValues.concat([1]));
    var grouped = {};
    nodes.forEach(function (node) {
      var layer = Number(node.layer || 0);
      if (!grouped[layer]) grouped[layer] = [];
      grouped[layer].push(node);
    });

    var positions = {};
    Object.keys(grouped).forEach(function (layerKey) {
      var layer = Number(layerKey);
      var items = grouped[layer];
      var x = padX + (width - padX * 2) * (layer / Math.max(1, maxLayer));
      items.forEach(function (node, index) {
        var count = items.length;
        var y = count === 1
          ? height / 2
          : padY + (height - padY * 2) * ((index + 1) / (count + 1));
        positions[node.id] = {x:x, y:y};
      });
    });

    var defs = [
      '<defs>',
      '<marker id="lb-arrow-idle" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z"></path></marker>',
      '<marker id="lb-arrow-recent" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z"></path></marker>',
      '<marker id="lb-arrow-executing" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z"></path></marker>',
      '</defs>'
    ].join("");

    var edgeSvg = edges.map(function (edge) {
      var a = positions[edge.source];
      var b = positions[edge.target];
      if (!a || !b) return "";
      var dx = Math.max(30, Math.abs(b.x - a.x) * 0.42);
      var d = "M" + a.x.toFixed(1) + "," + a.y.toFixed(1) +
        " C" + (a.x + dx).toFixed(1) + "," + a.y.toFixed(1) +
        " " + (b.x - dx).toFixed(1) + "," + b.y.toFixed(1) +
        " " + b.x.toFixed(1) + "," + b.y.toFixed(1);
      var status = edge.status || "idle";
      return '<path class="brain-wire ' + esc(status) + '" d="' + d +
        '" marker-end="url(#lb-arrow-' + (status === "executing" ? "executing" : status === "recent" ? "recent" : "idle") + ')">' +
        '<title>' + esc(edge.source + " → " + edge.target + " · " + (edge.label || "") +
        " · " + status + " · " + n(edge.count) + " переходов") + '</title></path>';
    }).join("");

    var nodeSvg = nodes.map(function (node) {
      var p = positions[node.id];
      if (!p) return "";
      var status = node.status || "idle";
      var w = 88;
      var h = 44;
      var label = String(node.label || node.id);
      var short = label.length > 16 ? label.slice(0, 15) + "…" : label;
      var age = node.age_ms == null ? "" : " · " + Math.round(n(node.age_ms)) + " ms";
      return '<g class="brain-flow-node ' + esc(status) + '" data-flow-node-id="' +
        esc(node.id) + '" tabindex="0" role="button" aria-label="' +
        esc(label + " · " + stateLabel(status)) + '" transform="translate(' +
        (p.x - w / 2).toFixed(1) + ',' + (p.y - h / 2).toFixed(1) + ')">' +
        '<rect width="' + w + '" height="' + h + '" rx="12"></rect>' +
        '<circle cx="11" cy="11" r="4"></circle>' +
        '<text class="brain-flow-node-label" x="' + (w / 2) + '" y="22">' + esc(short) + '</text>' +
        '<text class="brain-flow-node-state" x="' + (w / 2) + '" y="35">' + esc(stateLabel(status)) + '</text>' +
        '<title>' + esc(label + " · " + stateLabel(status) + age + " · visits=" + n(node.visits)) + '</title>' +
        '</g>';
    }).join("");

    svg.innerHTML = defs + edgeSvg + nodeSvg;

    var byId = {};
    nodes.forEach(function (node) { byId[String(node.id)] = node; });
    function inspectNode(node) {
      if (!node) return;
      selectedFlowNodeId = String(node.id || "");
      var inspector = el("#lb-node-inspector");
      if (!inspector) return;
      var detail = node.detail && typeof node.detail === "object"
        ? Object.keys(node.detail).slice(0, 6).map(function (key) {
            return '<span><b>' + esc(key) + '</b> ' + esc(String(node.detail[key])) + '</span>';
          }).join("")
        : "";
      var age = node.age_ms == null ? "нет сигнала" : (Math.round(n(node.age_ms)) + " мс назад");
      inspector.innerHTML =
        '<strong>' + esc(node.label || node.id) + '</strong>' +
        '<span class="brain-flow-inspector-status ' + esc(node.status || "idle") + '">' +
        esc(stateLabel(node.status || "idle")) + '</span>' +
        '<span>проходов: ' + n(node.visits) + '</span>' +
        '<span>' + esc(age) + '</span>' +
        detail;
    }

    svg.querySelectorAll("[data-flow-node-id]").forEach(function (element) {
      function activate() {
        inspectNode(byId[String(element.dataset.flowNodeId || "")]);
      }
      element.addEventListener("click", activate);
      element.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    });

    var selected = byId[selectedFlowNodeId];
    var executingNode = nodes.find(function (node) {
      return node.status === "executing";
    });
    inspectNode(selected || executingNode || nodes[0]);
  }

  function renderLegacyChannels(data) {
    var channels = Array.isArray(data.channels) ? data.channels : [];
    channels.forEach(function (channel) {
      var node = document.querySelector('[data-brain-node="' + channel.id + '"]');
      if (!node) return;
      node.classList.toggle("active", channel.status === "executing");
      node.classList.toggle("recent", channel.status === "recent");
      node.classList.toggle("attention", channel.status === "attention");
      var detail = node.querySelector("em");
      if (detail) detail.textContent = channel.detail || "ожидание";
    });
    if (data.pulse) {
      setText("#brain-focus-value", data.pulse.phase || "idle");
    }
  }

  function renderRealtimePulse(data) {
    if (!data) return;
    var pulse = data.pulse || {};
    var topology = data.topology || {};
    lastPulseSequence = Number(topology.sequence ?? pulse.sequence ?? lastPulseSequence);
    setText("#lb-current-phase", "фаза: " + (topology.current_phase || pulse.phase || "idle"));
    setText("#lb-flow-request", topology.request_id ? String(topology.request_id).slice(0,12) : "—");
    setText("#lb-flow-elapsed", topology.elapsed_ms == null ? "—" : (n(topology.elapsed_ms) + " мс"));
    setText(
      "#lb-flow-concurrency",
      n(topology.active_requests) + (
        n(topology.active_requests) === 1 ? " запрос" : " запросов"
      )
    );
    setText("#lb-events-hour", compact(pulse.events_1h));
    setText("#lb-events-5m", compact(pulse.events_5m) + " за 5 минут");

    var executing = (topology.nodes || []).filter(function (node) {
      return node.status === "executing";
    }).length;
    var attention = (topology.nodes || []).filter(function (node) {
      return node.status === "attention";
    }).length;
    setText("#lb-active-channels", executing + "/24");
    setText("#lb-attention-channels", attention + " требуют внимания");

    var stream = el("#lb-stream-state");
    if (stream) {
      var status = topology.status || "idle";
      var elapsed = topology.elapsed_ms == null ? "" : " · " + n(topology.elapsed_ms) + " ms";
      stream.textContent = "LIVE · " + stateLabel(status) + elapsed;
      stream.classList.toggle("executing", status === "running");
      stream.classList.toggle("attention", status === "error");
    }

    renderTopology({topology: topology, pulse: pulse});

    var sequence = Number(topology.sequence || 0);
    if (
      topology.status &&
      topology.status !== "running" &&
      sequence !== lastFinishedSequence
    ) {
      lastFinishedSequence = sequence;
      window.setTimeout(function () { loadBrain(true); }, 120);
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
      ["Документальные chunks", String(n(trace.document_sources))],
      ["Документы", Array.isArray(trace.document_ids) && trace.document_ids.length ? trace.document_ids.join(", ") : "—"],
      ["Research evidence", String(n(trace.research_logic_evidence))],
      ["Research conflicts", String(n(trace.research_logic_contradictions))],
      ["Перепроверка", trace.verification_ran ? ("да · " + n(trace.verification_unresolved) + " нереш.") : "не требовалась"],
      ["Качество выбора", pct(trace.decision_quality)],
      ["Grounding ответа", trace.grounding_applicable ? pct(trace.response_grounding) : "не применимо"],
      ["Подтверждено claims", String(n(trace.grounded_claims))],
      ["Частично claims", String(n(trace.partial_grounded_claims))],
      ["Без опоры claims", String(n(trace.unsupported_response_claims))],
      ["Source groups", String(n(trace.grounding_source_groups))],
      ["Исполнение", trace.execution_state ? stateLabel(trace.execution_state) : "—"],
      ["Инструмент", trace.execution_tool || "—"],
      ["Фактически выполнено", trace.execution_executed ? "да" : "нет"],
      ["Approval", trace.approval_decision_id == null ? "—" : ("#" + trace.approval_decision_id)],
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
      svg.innerHTML = '<text x="260" y="115" text-anchor="middle" fill="#9a908c" font-size="11">Граф знаний ещё пуст</text>';
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
    var proactive = data.proactive_intelligence || {};
    var proactiveSummary = proactive.summary || {};
    var evolution = data.evolution || {};
    var evolutionSummary = evolution.summary || {};
    var research = data.research || {};
    var researchSummary = research.summary || {};
    var communication = data.communication || {};
    var communicationSummary = communication.summary || {};
    var documents = data.documents || {};
    var documentsSummary = documents.summary || {};
    var quality = data.quality || {};
    var grounding = quality.response_grounding || {};
    var lifecycle = data.knowledge_lifecycle || {};
    var lifecycleSummary = lifecycle.summary || {};
    var canonical = data.canonical_facts || {};
    var canonicalSummary = canonical.summary || {};
    var canonicalStates = canonicalSummary.states || {};

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
    setText("#lb-awareness-score", proactiveSummary.awareness_score == null ? "—" : n(proactiveSummary.awareness_score).toFixed(1) + "%");
    setText("#lb-awareness-incidents", n(proactiveSummary.active_incidents) + " ситуаций · " + n(proactiveSummary.requires_attention) + " внимание");
    setText("#lb-evolution-score", evolutionSummary.evolution_score == null ? "—" : n(evolutionSummary.evolution_score).toFixed(1) + "%");
    setText("#lb-evolution-generation", "G" + Math.max(1, n(evolutionSummary.generation)) + " · " + n(evolutionSummary.champions) + " champions · " + n(evolutionSummary.challengers) + " challengers");
    setText("#lb-research-score", researchSummary.research_score == null ? "—" : n(researchSummary.research_score).toFixed(1) + "%");
    setText("#lb-research-status", n(researchSummary.open_gaps) + " gaps · " + n(researchSummary.trusted_claims) + " trusted · " + n(researchSummary.open_contradictions) + " conflicts");
    setText("#lb-communication-score", communicationSummary.communication_score == null ? "—" : n(communicationSummary.communication_score).toFixed(1) + "%");
    setText("#lb-communication-status", n(communicationSummary.evaluated_turns) + " evidence · persona " + n(communicationSummary.persona_stability).toFixed(0) + "% · explain " + n(communicationSummary.explanation_success).toFixed(0) + "%");
    setText("#lb-documents-score", documentsSummary.ingestion_score == null ? "—" : n(documentsSummary.ingestion_score).toFixed(1) + "%");
    setText("#lb-documents-status", n(documentsSummary.studied_documents) + " studied · " + n(documentsSummary.ocr_required_documents) + " OCR · " + n(documentsSummary.contradiction_count) + " conflicts");
    setText(
      "#lb-grounding-score",
      grounding.applicable && grounding.overall != null
        ? pct(grounding.overall)
        : "—"
    );
    setText(
      "#lb-grounding-status",
      grounding.id
        ? ((grounding.status || "unscored") + " · " +
          n(grounding.claims_supported) + " подтверждено · " +
          n(grounding.claims_unsupported) + " без опоры")
        : "ещё не измерялся"
    );
    setText("#lb-knowledge-verified", compact(lifecycleSummary.verified_knowledge));
    setText(
      "#lb-knowledge-status",
      compact(lifecycleSummary.contradicted_knowledge) + " conflicts · " +
      compact(lifecycleSummary.confirmed_hypotheses) + " confirmed hypotheses · " +
      compact(lifecycleSummary.corrections_confirmed) + " corrections"
    );
    setText("#lb-canonical-verified", compact(canonicalStates.verified));
    setText(
      "#lb-canonical-status",
      compact(canonicalStates.conflicted) + " conflicts · " +
      compact(canonicalSummary.superseded_values) + " history · " +
      compact(canonicalSummary.independent_groups) + " evidence groups"
    );
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
    return fetch(scopeUrl("/api/assistant/live-brain?scope=personal&event_limit=50&graph_limit=20"), {
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
    fetch(scopeUrl("/api/assistant/live-brain/export?scope=personal"), { cache: "no-store" })
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

  function closeStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function connectStream() {
    closeStream();
    if (document.hidden || typeof EventSource === "undefined") return;
    var streamState = el("#lb-stream-state");
    if (streamState) streamState.textContent = "LIVE · подключение…";
    eventSource = new EventSource(
      scopeUrl("/api/assistant/live-brain/stream?scope=personal")
    );
    eventSource.addEventListener("open", function () {
      if (streamState) {
        streamState.textContent = "LIVE · подключено";
        streamState.classList.remove("attention");
      }
    });
    eventSource.addEventListener("pulse", function (event) {
      try {
        renderRealtimePulse(JSON.parse(event.data));
      } catch (error) {
        console.error("Live Brain pulse:", error);
      }
    });
    eventSource.addEventListener("error", function () {
      if (streamState) {
        streamState.textContent = "LIVE · переподключение";
        streamState.classList.add("attention");
      }
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
        // The live stream shows execution immediately; the full snapshot is
        // refreshed once the request finishes.
        window.setTimeout(function () { loadBrain(true); }, 2500);
      });
    }

    var developmentOpen = el("#development-open");
    if (developmentOpen) {
      developmentOpen.addEventListener("click", function () {
        window.setTimeout(function () { loadBrain(true); }, 80);
      });
    }

    document.addEventListener("aishin:scope-change", function () {
      lastFinishedSequence = -1;
      loadBrain(true);
      connectStream();
    });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) closeStream();
      else {
        connectStream();
        loadBrain(false);
      }
    });

    window.AISHIN_LIVE_BRAIN_REFRESH = function () {
      loadBrain(true);
      connectStream();
    };

    loadBrain(true);
    connectStream();
    window.setInterval(function () {
      if (shouldRefresh()) loadBrain(false);
    }, 45000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
