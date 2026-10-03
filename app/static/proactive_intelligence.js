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

  var payload = null;
  var loading = false;
  var currentFilter = "all";

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

  function pct01(value) {
    return Math.round(n(value) * 100) + "%";
  }

  function timeText(value) {
    if (!value) return "—";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
    return date.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  function severity(score) {
    score = n(score);
    if (score >= 0.84) return "critical";
    if (score >= 0.68) return "high";
    if (score >= 0.48) return "medium";
    return "low";
  }

  function severityLabel(level) {
    return {
      critical: "Критично",
      high: "Важно",
      medium: "Наблюдение",
      low: "Низкий"
    }[level] || level;
  }

  function sourceLabel(source) {
    return {
      planner: "Планировщик",
      sensor: "Сенсоры",
      verification: "Перепроверка",
      execution: "Исполнение",
      cognitive_intelligence: "Интеллект",
      learning: "Обучение",
      knowledge: "Знания",
      situation_delta: "Изменение состояния",
      system: "Система"
    }[source] || source || "—";
  }

  function setText(selector, value) {
    var node = q(selector);
    if (node) node.textContent = value;
  }

  function ensureHomeCard() {
    var panel = q(".today-panel");
    if (!panel || q("#proactive-home-card")) return;
    var card = document.createElement("button");
    card.id = "proactive-home-card";
    card.type = "button";
    card.className = "proactive-home-card";
    card.innerHTML = [
      '<div class="proactive-home-card-head"><strong>Айши заметила</strong><span>◎</span></div>',
      '<div class="proactive-home-numbers">',
        '<div><strong id="ph-active">0</strong><small>ситуаций</small></div>',
        '<div><strong id="ph-attention">0</strong><small>внимание</small></div>',
        '<div><strong id="ph-awareness">0%</strong><small>осведомлённость</small></div>',
      '</div>',
      '<div id="ph-status" class="proactive-home-status">Наблюдаю за изменениями системы.</div>'
    ].join("");
    card.addEventListener("click", function () {
      var nav = document.querySelector('.nav-item[data-module="attention"]');
      if (nav) nav.click();
    });
    var development = q("#development-open");
    if (development && development.parentElement === panel) {
      development.insertAdjacentElement("afterend", card);
    } else {
      panel.prepend(card);
    }
  }

  function renderHome(summary) {
    setText("#ph-active", n(summary.active_incidents));
    setText("#ph-attention", n(summary.requires_attention));
    setText("#ph-awareness", n(summary.awareness_score).toFixed(0) + "%");
    var status = q("#ph-status");
    if (!status) return;
    if (n(summary.critical) > 0) {
      status.textContent = "Есть критическая ситуация — откройте evidence.";
    } else if (n(summary.requires_attention) > 0) {
      status.textContent = "Есть ситуации, которые стоит проверить.";
    } else {
      status.textContent = "Сейчас нет активных сигналов выше порога внимания.";
    }
  }

  function renderHero(data) {
    var summary = data.summary || {};
    var score = Math.max(0, Math.min(100, n(summary.awareness_score)));
    var ring = q("#proactive-awareness-ring");
    if (ring) ring.style.setProperty("--awareness-score", score);
    setText("#proactive-awareness-score", score.toFixed(1) + "%");
    setText("#proactive-stat-objects", n(summary.observed_objects));
    setText("#proactive-stat-incidents", n(summary.active_incidents));
    setText("#proactive-stat-attention", n(summary.requires_attention));
    setText("#proactive-stat-expectations", n(summary.expectations));
    setText("#proactive-stat-overdue", n(summary.overdue_expectations) + " просрочено");
    setText("#proactive-stat-threshold", pct01(summary.attention_threshold));
    renderHome(summary);
  }

  function renderIncidents(items) {
    var host = q("#proactive-incidents");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    var visible = items.filter(function (item) {
      if (item.status !== "active") return false;
      if (currentFilter === "all") return true;
      return severity(item.risk_score) === currentFilter;
    });

    if (!visible.length) {
      host.innerHTML = '<div class="proactive-empty">Нет активных ситуаций в выбранной категории.</div>';
      return;
    }

    host.innerHTML = visible.slice(0, 40).map(function (item) {
      var level = severity(item.risk_score);
      var risk = Math.round(n(item.risk_score) * 100);
      var evidence = Array.isArray(item.evidence) ? item.evidence : [];
      return '<article class="proactive-incident ' + esc(level) + '" style="--risk:' + risk + '">' +
        '<div class="incident-risk"><strong>' + risk + '%</strong><small>risk</small></div>' +
        '<div class="incident-main">' +
          '<h4>' + esc(item.title || "Ситуация") + '</h4>' +
          '<p>' + esc(item.summary || "") + '</p>' +
          '<div class="incident-meta">' +
            '<span class="incident-tag">' + esc(severityLabel(level)) + '</span>' +
            '<span class="incident-tag">' + esc(sourceLabel(item.source)) + '</span>' +
            '<span class="incident-tag attention">attention ' + pct01(item.attention_score) + '</span>' +
            '<span class="incident-tag verify">' + esc(item.verification_state || "observed") + '</span>' +
            '<span class="incident-tag">evidence ' + evidence.length + '</span>' +
            '<span class="incident-tag">×' + n(item.occurrences) + '</span>' +
          '</div>' +
          (item.suggested_action ? '<p class="incident-action"><strong>Предлагаю:</strong> ' + esc(item.suggested_action) + '</p>' : '') +
        '</div>' +
        '<div class="incident-controls">' +
          '<button class="primary" type="button" data-incident-feedback="useful" data-incident-id="' + item.id + '">Полезно</button>' +
          '<button type="button" data-incident-feedback="handled" data-incident-id="' + item.id + '">Разобрался</button>' +
          '<button type="button" data-incident-feedback="snooze" data-incident-id="' + item.id + '">На 24 ч.</button>' +
          '<button type="button" data-incident-feedback="noisy" data-incident-id="' + item.id + '">Шум</button>' +
        '</div>' +
      '</article>';
    }).join("");

    host.querySelectorAll("[data-incident-feedback]").forEach(function (button) {
      button.addEventListener("click", function () {
        sendFeedback(
          Number(button.dataset.incidentId),
          button.dataset.incidentFeedback
        );
      });
    });
  }

  function renderSituation(situation) {
    situation = situation || {};
    var state = situation.state || {};
    var delta = situation.delta || {};
    setText("#proactive-snapshot-time", timeText(situation.created_at));

    var metrics = [
      ["entities", "Сущности"],
      ["relations", "Связи"],
      ["active_memories", "Память"],
      ["open_tasks", "Открытые задачи"],
      ["blocked_tasks", "Заблокировано"],
      ["overdue_tasks", "Просрочено"],
      ["unresolved_verifications", "Нерешённые проверки"],
      ["fading_skills", "Устаревающие навыки"],
      ["failed_routes_7d", "Слабые маршруты · 7д"],
      ["execution_failures_7d", "Ошибки исполнения · 7д"],
      ["stale_knowledge", "Устаревшие знания"],
      ["pending_decisions", "Ожидают решения"]
    ];
    var host = q("#proactive-situation-grid");
    if (host) {
      host.innerHTML = metrics.map(function (item) {
        var key = item[0], label = item[1];
        var change = n(delta[key]);
        var changed = Math.abs(change) > 0.001;
        var sign = change > 0 ? "+" : "";
        return '<article class="situation-metric' + (changed ? " changed" : "") + '">' +
          '<span>' + esc(label) + '</span><strong>' + n(state[key]) + '</strong>' +
          '<small>' + (changed ? (sign + change.toFixed(0) + " с прошлого снимка") : "без изменения") + '</small></article>';
      }).join("");
    }

    var health = state.source_health || {};
    var healthHost = q("#proactive-source-health");
    if (healthHost) {
      var keys = Object.keys(health);
      healthHost.innerHTML = keys.length
        ? keys.map(function (key) {
            var ok = Boolean(health[key]);
            return '<div class="source-health-item ' + (ok ? "ok" : "error") + '"><i></i><span>' + esc(key) + ' · ' + (ok ? "online" : "error") + '</span></div>';
          }).join("")
        : '<div class="proactive-empty">Нет данных о каналах наблюдения.</div>';
    }
  }

  function renderExpectations(items) {
    var host = q("#proactive-expectations");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    var active = items.filter(function (item) {
      return item.status === "pending" || item.status === "overdue";
    });
    setText("#proactive-expectation-count", String(active.length));
    if (!active.length) {
      host.innerHTML = '<div class="proactive-empty">Нет активных ожиданий по срокам и следующим шагам.</div>';
      return;
    }
    host.innerHTML = active.slice(0, 25).map(function (item) {
      return '<article class="expectation-item ' + esc(item.status) + '"><span class="expectation-dot"></span><div><strong>' +
        esc(item.title || item.expectation_key) +
        '</strong><small>' + esc(item.expected_state || "") +
        ' · confidence ' + pct01(item.confidence) +
        '</small></div><time>' + esc(item.due_at ? timeText(item.due_at) : item.status) + '</time></article>';
    }).join("");
  }

  function renderSignals(items) {
    var host = q("#proactive-signals");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    setText("#proactive-signal-count", String(items.length));
    if (!items.length) {
      host.innerHTML = '<div class="proactive-empty">Сигналы не обнаружены.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 28).map(function (item) {
      var level = severity(item.risk_score);
      return '<article class="signal-item ' + esc(level) + '"><span class="signal-dot"></span><div><strong>' +
        esc(item.title || item.signal_type) +
        '</strong><small>' + esc(sourceLabel(item.source)) +
        ' · risk ' + pct01(item.risk_score) +
        ' · attention ' + pct01(item.attention_score) +
        ' · ×' + n(item.occurrences) +
        '</small></div><time>' + esc(timeText(item.last_seen_at)) + '</time></article>';
    }).join("");
  }

  function renderCalibration(profile) {
    var host = q("#proactive-calibration");
    if (!host) return;
    profile = profile || {};
    var threshold = Math.max(0, Math.min(1, n(profile.calibrated_threshold || .48)));
    host.innerHTML = [
      '<div class="attention-threshold">',
        '<div class="threshold-ring" style="--threshold:' + Math.round(threshold * 100) + '"><strong>' + Math.round(threshold * 100) + '%</strong></div>',
        '<div class="threshold-copy"><h4>Порог внимания</h4><p>Чем больше сигналов отмечается как шум или false positive, тем осторожнее Айши поднимает новые уведомления. Полезные и обработанные сигналы снижают порог в безопасных пределах.</p></div>',
      '</div>',
      '<div class="feedback-stats">',
        '<article class="feedback-stat"><strong>' + n(profile.useful_count) + '</strong><span>полезно</span></article>',
        '<article class="feedback-stat"><strong>' + n(profile.handled_count) + '</strong><span>обработано</span></article>',
        '<article class="feedback-stat"><strong>' + n(profile.noisy_count) + '</strong><span>шум</span></article>',
        '<article class="feedback-stat"><strong>' + n(profile.false_positive_count) + '</strong><span>false positive</span></article>',
      '</div>'
    ].join("");
  }

  function renderHistory(runs) {
    var svg = q("#proactive-history-chart");
    var host = q("#proactive-runs");
    runs = Array.isArray(runs) ? runs : [];

    if (svg) {
      var ordered = runs.slice(0, 60).reverse();
      if (ordered.length < 2) {
        svg.innerHTML = '<text x="450" y="85" text-anchor="middle" fill="#9a908c" font-size="11">История наблюдений ещё накапливается</text>';
      } else {
        var width = 900, height = 170, px = 32, py = 20;
        var uw = width - px * 2, uh = height - py * 2;
        var values = ordered.map(function (item) { return n(item.awareness_score); });
        var min = Math.max(0, Math.min.apply(null, values) - 4);
        var max = Math.min(100, Math.max.apply(null, values) + 4);
        if (max - min < 10) max = Math.min(100, min + 10);
        function X(i) { return px + uw * i / Math.max(1, ordered.length - 1); }
        function Y(v) { return py + uh - ((v - min) / Math.max(1, max - min)) * uh; }

        var grid = [0,.25,.5,.75,1].map(function (ratio) {
          var y = py + uh * ratio;
          return '<line class="grid" x1="' + px + '" y1="' + y.toFixed(1) + '" x2="' + (width-px) + '" y2="' + y.toFixed(1) + '"></line>';
        }).join("");
        var path = values.map(function (value, index) {
          return (index ? "L" : "M") + X(index).toFixed(1) + " " + Y(value).toFixed(1);
        }).join(" ");
        var dots = values.map(function (value, index) {
          return '<circle class="dot" cx="' + X(index).toFixed(1) + '" cy="' + Y(value).toFixed(1) + '" r="3"><title>' + value.toFixed(1) + '%</title></circle>';
        }).join("");
        svg.innerHTML = grid + '<path class="line" d="' + path + '"></path>' + dots;
      }
    }

    if (host) {
      host.innerHTML = runs.length
        ? runs.slice(0, 8).map(function (item) {
            return '<article class="proactive-run"><span class="run-dot"></span><div><strong>' +
              esc(item.trigger || "scan") + ' · ' + n(item.awareness_score).toFixed(1) + '%</strong><small>' +
              n(item.signals_observed) + ' сигналов · ' +
              n(item.incidents_created) + ' новых · ' +
              n(item.incidents_resolved) + ' закрыто · ' +
              n(item.duration_ms) + ' мс</small></div><time>' +
              esc(timeText(item.created_at)) + '</time></article>';
          }).join("")
        : '<div class="proactive-empty">Сканирования ещё не выполнялись.</div>';
    }
  }

  function renderPrinciples(items) {
    var host = q("#proactive-principles");
    if (!host) return;
    items = Array.isArray(items) ? items : [];
    host.innerHTML = items.length
      ? items.map(function (item) {
          return '<article class="proactive-principle">' + esc(item) + '</article>';
        }).join("")
      : '<div class="proactive-empty">Правила не загружены.</div>';
  }

  function render(data) {
    payload = data;
    renderHero(data);
    renderIncidents(data.incidents || []);
    renderSituation(data.situation || {});
    renderExpectations(data.expectations || []);
    renderSignals(data.signals || []);
    renderCalibration(data.attention_profile || {});
    renderHistory(data.runs || []);
    renderPrinciples(data.principles || []);
  }

  function load() {
    if (loading) return Promise.resolve(payload);
    loading = true;
    return fetchScope(
      "/api/assistant/proactive-intelligence?scope=personal&incident_limit=100&signal_limit=100&run_limit=60",
      { cache: "no-store" }
    )
      .then(function (response) {
        if (!response.ok) throw new Error("Proactive Intelligence HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        render(data);
        return data;
      })
      .catch(function (error) {
        var host = q("#proactive-incidents");
        if (host && !payload) {
          host.innerHTML = '<div class="proactive-empty">' + esc(error.message || error) + '</div>';
        }
        return null;
      })
      .finally(function () {
        loading = false;
      });
  }

  function scan() {
    var button = q("#proactive-scan-btn");
    if (button) {
      button.disabled = true;
      button.textContent = "Проверяю…";
    }
    return fetchScope(
      "/api/assistant/proactive-intelligence/scan?scope=personal",
      { method: "POST" }
    )
      .then(function (response) {
        if (!response.ok) throw new Error("Scan HTTP " + response.status);
        return response.json();
      })
      .then(function () {
        return load();
      })
      .catch(function (error) {
        window.alert("Не удалось выполнить ситуационную проверку: " + (error.message || error));
      })
      .finally(function () {
        if (button) {
          button.disabled = false;
          button.textContent = "Проверить ситуацию сейчас";
        }
      });
  }

  function sendFeedback(incidentId, feedback) {
    return fetchScope(
      "/api/assistant/proactive-intelligence/incidents/" + encodeURIComponent(incidentId) + "/feedback",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: scopeValue(),
          feedback: feedback,
          reason: ""
        })
      }
    )
      .then(function (response) {
        if (!response.ok) throw new Error("Feedback HTTP " + response.status);
        return response.json();
      })
      .then(function () {
        return load();
      })
      .catch(function (error) {
        window.alert("Не удалось сохранить feedback: " + (error.message || error));
      });
  }

  function boot() {
    ensureHomeCard();

    q("#proactive-scan-btn")?.addEventListener("click", scan);

    document.querySelectorAll("[data-proactive-filter]").forEach(function (button) {
      button.addEventListener("click", function () {
        currentFilter = button.dataset.proactiveFilter || "all";
        document.querySelectorAll("[data-proactive-filter]").forEach(function (item) {
          item.classList.toggle("active", item === button);
        });
        renderIncidents((payload && payload.incidents) || []);
      });
    });

    var form = q("#chat-form");
    if (form) {
      form.addEventListener("submit", function () {
        setTimeout(load, 2800);
      });
    }

    load();
  }

  window.AISHIN_PROACTIVE_REFRESH = load;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
