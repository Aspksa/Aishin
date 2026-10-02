const logo = window.AISHIN_LOGO;
document.getElementById("brand-logo").src = logo;
document.getElementById("hero-logo").src = logo;

const pages = {
  assistant: {
    title: "Aishin Kitsune",
    description: "Личная помощница"
  },
  account: {
    title: "Личный кабинет",
    description: "Здесь будет профиль владельца, персональные настройки, доступы и параметры Айшин."
  },
  mobile: {
    title: "Мобильное приложение",
    description: "Здесь будет управление подключением мобильного клиента и синхронизацией."
  },
  workspace: {
    title: "Рабочее пространство",
    description: "Здесь будут проекты, документы, инструменты и рабочие контексты."
  }
};

document.querySelectorAll(".nav-item[data-module]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item[data-module]").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");

    const code = button.dataset.module;
    document.getElementById("page-title").textContent = pages[code].title;

    document.querySelectorAll(".module-page").forEach((page) => page.classList.remove("active"));
    if (code === "assistant") {
      document.getElementById("assistant-module").classList.add("active");
    } else {
      document.getElementById("placeholder-title").textContent = pages[code].title;
      document.getElementById("placeholder-description").textContent = pages[code].description;
      document.getElementById("placeholder-module").classList.add("active");
    }
  });
});

const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const messages = document.getElementById("messages");

function addMessage(text, who) {
  const el = document.createElement("div");
  el.className = `message ${who}`;
  el.textContent = text;
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage(message, "user");
  input.value = "";

  try {
    const response = await fetch("/api/assistant/message", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message})
    });
    const data = await response.json();
    addMessage(data.reply || "Не удалось получить ответ.", "aishin");
    await refreshDashboard(false);
  } catch {
    addMessage("Господин, связь с ядром прервалась. Я бы проверила сервер.", "aishin");
  }
});

document.getElementById("update-btn").addEventListener("click", async () => {
  const status = document.getElementById("update-status");
  status.textContent = "Проверяю GitHub...";
  try {
    const response = await fetch("/api/system/update", {method: "POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Ошибка обновления");
    status.textContent = "Обновление завершено";
  } catch (error) {
    status.textContent = "Ошибка: " + error.message;
  }
});

const pendingContainer = document.getElementById("pending-decisions");
const approvedContainer = document.getElementById("approved-decisions");
const pendingCount = document.getElementById("pending-count");
const approvedCount = document.getElementById("approved-count");
const sensorState = document.getElementById("sensor-state");
const refreshApproval = document.getElementById("refresh-approval");

function formatPriority(value) {
  const numeric = Number(value || 0);
  if (numeric >= 0.8) return {label: "Высокий", css: "high"};
  if (numeric >= 0.55) return {label: "Средний", css: "medium"};
  return {label: "Обычный", css: "normal"};
}

function humanTool(tool) {
  const names = {
    "planner.create_task": "Создать внутреннюю задачу",
    "planner.set_task_status": "Изменить статус задачи",
    "project.read_text": "Прочитать файл проекта",
    "project.write_text": "Записать файл проекта"
  };
  return names[tool] || tool || "Только уведомление";
}

function compactPreview(decision) {
  const preview = decision.preview || {};
  const output = preview.output || preview;
  if (output.would_create) {
    const item = output.would_create;
    return `Будет создана задача: ${item.title || "без названия"}`;
  }
  if (output.would_update) {
    const item = output.would_update;
    return `Будет изменена задача #${item.task_id}: ${item.status}`;
  }
  if (output.would_read) {
    return `Будет прочитан файл: ${output.would_read}`;
  }
  if (output.would_write) {
    return `Будет записан файл: ${output.would_write}`;
  }
  if (!decision.tool_name) {
    return "Информационное наблюдение — автоматического действия нет.";
  }
  return "Предпросмотр действия подготовлен.";
}

function metaSpan(text) {
  const el = document.createElement("span");
  el.textContent = text;
  return el;
}

function actionButton(label, css, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = css;
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await handler();
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function decisionCard(decision, mode) {
  const priority = formatPriority(decision.priority);
  const card = document.createElement("article");
  card.className = `decision-card ${priority.css}`;

  const top = document.createElement("div");
  top.className = "decision-top";

  const title = document.createElement("h4");
  title.textContent = decision.title || "Решение Айшин";

  const badge = document.createElement("span");
  badge.className = "priority-badge";
  badge.textContent = priority.label;

  top.append(title, badge);

  const rationale = document.createElement("p");
  rationale.className = "decision-rationale";
  rationale.textContent = decision.rationale || "Причина не указана.";

  const meta = document.createElement("div");
  meta.className = "decision-meta";
  meta.append(
    metaSpan(`#${decision.id}`),
    metaSpan(humanTool(decision.tool_name)),
    metaSpan(`confidence ${Math.round(Number(decision.confidence || 0) * 100)}%`),
    metaSpan(decision.source || "core")
  );

  const preview = document.createElement("div");
  preview.className = "preview-box";
  const previewTitle = document.createElement("strong");
  previewTitle.textContent = "Предпросмотр";
  const previewText = document.createElement("span");
  previewText.textContent = compactPreview(decision);
  preview.append(previewTitle, previewText);

  const actions = document.createElement("div");
  actions.className = "decision-actions";

  if (mode === "pending") {
    if (decision.tool_name) {
      actions.append(
        actionButton("Одобрить", "approve", async () => {
          await decisionRequest(decision.id, "approve", {execute: false});
        }),
        actionButton("Отклонить", "reject", async () => {
          await decisionRequest(decision.id, "reject", {reason: "Отклонено Господином через Approval Center"});
        })
      );
    } else {
      actions.append(
        actionButton("Принято", "approve", async () => {
          await decisionRequest(decision.id, "acknowledge", {reason: "Информационный сигнал принят Господином"});
        }),
        actionButton("Отклонить", "reject", async () => {
          await decisionRequest(decision.id, "reject", {reason: "Информационный сигнал отклонён Господином"});
        })
      );
    }
  } else if (mode === "approved") {
    if (decision.tool_name) {
      actions.append(
        actionButton("Выполнить", "execute", async () => {
          await decisionRequest(decision.id, "execute", {});
        })
      );
    }
  }

  card.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    showDecisionReasoning(decision);
  });

  card.append(top, rationale, meta, preview, actions);
  return card;
}

function renderDecisions(container, decisions, mode, emptyText) {
  container.replaceChildren();
  if (!decisions.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  decisions.forEach((decision) => {
    container.appendChild(decisionCard(decision, mode));
  });
}

async function decisionRequest(id, action, extra) {
  const response = await fetch(`/api/assistant/proactive/${id}/${action}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      scope: "personal",
      execute: false,
      reason: "",
      ...extra
    })
  });
  const data = await response.json();
  if (!response.ok) {
    addMessage(`Не удалось обработать решение #${id}: ${data.detail || "ошибка"}`, "aishin");
    return;
  }

  if (action === "approve") {
    addMessage(`Решение #${id} одобрено, Господин. Оно ещё не считается выполненным.`, "aishin");
  } else if (action === "execute") {
    const status = data.status || "unknown";
    if (status === "executed") {
      addMessage(`Решение #${id} выполнено и записано в журнал.`, "aishin");
    } else {
      addMessage(`Решение #${id}: результат — ${status}.`, "aishin");
    }
  } else if (action === "acknowledge") {
    addMessage(`Сигнал #${id} принят к сведению. Повторяться не будет, пока условие не исчезнет и не возникнет снова.`, "aishin");
  } else {
    addMessage(`Решение #${id} отклонено.`, "aishin");
  }

  await refreshDashboard(false);
}



function brainStreamItem(title, detail) {
  const item = document.createElement("div");
  item.className = "brain-stream-item";

  const strong = document.createElement("strong");
  strong.textContent = title;

  const span = document.createElement("span");
  span.textContent = detail;

  item.append(strong, span);
  return item;
}

function setBrainNode(name, active, attention, detail) {
  const node = document.querySelector(`[data-brain-node="${name}"]`);
  if (!node) return;
  node.classList.toggle("active", Boolean(active));
  node.classList.toggle("attention", Boolean(attention));

  const detailEl = document.getElementById(`brain-${name}-detail`);
  if (detailEl) detailEl.textContent = detail || "спокойно";
}

function renderLivingBrain(state, sensors, pending, approved) {
  const runtime = state.state || {};
  const memories = state.working_memory?.memories || [];
  const graph = state.knowledge_graph?.personal || {};
  const tasks = state.planner?.open_items?.tasks || [];
  const events = state.recent_events || [];
  const actions = state.tools?.recent_actions || [];

  document.getElementById("brain-focus-value").textContent =
    runtime.focus || runtime.activity || "waiting";

  const attentionSensors = sensors.filter((item) => item.status !== "ok");
  const activeDecisions = [...pending, ...approved];
  const meta = state.metacognition?.last || state.working_memory?.metacognition || null;
  const logic = state.working_memory?.logic || null;
  const contextTrace = state.working_memory?.context_orchestrator || null;
  const causal = state.working_memory?.causal || null;
  const hypotheses = state.working_memory?.hypotheses || null;
  const learning = state.working_memory?.logic_learning || null;
  const counterfactual = state.working_memory?.counterfactual || null;
  const quality = state.working_memory?.decision_quality || null;
  const actionSelection = state.working_memory?.action_selection || null;
  const executionGuard = state.execution_coordinator || {};
  const verification = state.working_memory?.verification || null;
  const performance = state.working_memory?.performance || (state.performance || [])[0] || null;

  setBrainNode(
    "sensors",
    sensors.length > 0,
    attentionSensors.length > 0,
    attentionSensors.length
      ? `${attentionSensors.length} требуют внимания`
      : `${sensors.length} каналов спокойно`
  );
  setBrainNode(
    "memory",
    memories.length > 0,
    false,
    `${memories.length} в рабочем контексте`
  );
  setBrainNode(
    "graph",
    Number(graph.entities || 0) > 0,
    false,
    `${graph.entities || 0} сущностей · ${graph.relations || 0} связей`
  );
  setBrainNode(
    "planner",
    tasks.length > 0,
    (state.planner?.notices || []).some((item) => item.severity === "warning"),
    `${tasks.length} открытых задач`
  );
  setBrainNode(
    "logic",
    Boolean(logic),
    Boolean(logic?.unresolved?.length),
    logic
      ? `${logic.mode} · complexity ${Math.round(Number(logic.complexity || 0) * 100)}%`
      : "режим ещё не выбран"
  );

  setBrainNode(
    "context",
    Boolean(contextTrace),
    false,
    contextTrace
      ? `${contextTrace.mode} · ~${contextTrace.estimated_chars || 0} chars`
      : "контекст ещё не собран"
  );

  setBrainNode(
    "causal",
    Boolean(causal),
    Boolean(causal?.unresolved?.length),
    causal
      ? `${causal.claims?.length || 0} claims · ${causal.unresolved?.length || 0} unresolved`
      : "причинных claims нет"
  );

  setBrainNode(
    "hypotheses",
    Boolean(hypotheses),
    Boolean(hypotheses?.selected_test && Object.keys(hypotheses.selected_test).length),
    hypotheses
      ? `${hypotheses.hypotheses?.length || 0} hypotheses · ${hypotheses.stop_reason || "testing"}`
      : "гипотезы ещё не строились"
  );

  setBrainNode(
    "learning",
    Boolean(learning),
    false,
    learning?.feedback?.applied
      ? `${learning.feedback.outcome} · reliability ${Math.round(Number(learning.feedback.reliability || 0) * 100)}%`
      : `${learning?.strategies?.length || 0} learned strategies`
  );

  setBrainNode(
    "counterfactual",
    Boolean(counterfactual),
    Boolean(counterfactual?.unresolved?.length),
    counterfactual
      ? `${counterfactual.scenarios?.length || 0} scenarios · ${counterfactual.unresolved?.length || 0} unresolved`
      : "what-if ещё не выполнялся"
  );

  setBrainNode(
    "quality",
    Boolean(quality),
    Number(quality?.overall || 0) < 0.58,
    quality
      ? `${Math.round(Number(quality.overall || 0) * 100)}% · ${quality.recommendation || "нет оценки"}`
      : "качество ещё не рассчитано"
  );

  setBrainNode(
    "action",
    Boolean(actionSelection?.selected && Object.keys(actionSelection.selected).length),
    ["approval_required", "blocked_by_permission"].includes(actionSelection?.selection_state),
    actionSelection?.selected
      ? `${Math.round(Number(actionSelection.selected.utility || 0) * 100)}% · ${actionSelection.selection_state}`
      : "кандидат ещё не выбран"
  );

  const activeApprovals = (executionGuard.approvals || []).filter(
    (item) => item.status === "active"
  );
  const latestAttempt = (executionGuard.attempts || [])[0] || null;
  setBrainNode(
    "execution",
    activeApprovals.length > 0 || Boolean(latestAttempt),
    activeApprovals.length > 0,
    activeApprovals.length
      ? `${activeApprovals.length} one-shot approval`
      : latestAttempt
        ? `last: ${latestAttempt.status}`
        : "нет активных разрешений"
  );

  setBrainNode(
    "performance",
    Boolean(performance),
    performance?.budget_status === "over_budget",
    performance
      ? `${performance.total_ms || 0} ms · ${performance.bottleneck || "—"}`
      : "замеров ещё нет"
  );

  const metaStatus = meta?.status || "нет оценки";
  const metaAttention = ["needs_verification", "insufficient_data"].includes(metaStatus);
  setBrainNode(
    "metacognition",
    Boolean(meta),
    metaAttention,
    meta
      ? `${metaStatus} · ${Math.round(Number(meta.confidence || 0) * 100)}%`
      : "оценка ещё не выполнялась"
  );
  setBrainNode(
    "verification",
    Boolean(verification?.ran),
    Boolean(verification?.unresolved?.length),
    verification?.ran
      ? `${verification.checks?.length || 0} проверок · ${verification.unresolved?.length || 0} нерешено`
      : "не требовалась"
  );
  setBrainNode(
    "decision",
    activeDecisions.length > 0,
    pending.length > 0,
    pending.length
      ? `${pending.length} ждут Господина`
      : `${approved.length} одобрено`
  );
  setBrainNode(
    "tool",
    actions.length > 0,
    actions.some((item) => item.status === "error" || item.status === "denied"),
    actions.length ? `последних действий: ${actions.length}` : "действий нет"
  );

  const flow = document.getElementById("brain-flow");
  flow.classList.toggle(
    "active",
    sensors.length > 0 || memories.length > 0 || tasks.length > 0
  );

  const memoryStream = document.getElementById("brain-memory-stream");
  memoryStream.replaceChildren();
  document.getElementById("brain-memory-count").textContent = String(memories.length);

  if (!memories.length) {
    const empty = document.createElement("p");
    empty.className = "brain-empty";
    empty.textContent = "Память пока не поднята в текущий контекст.";
    memoryStream.appendChild(empty);
  } else {
    memories.slice(0, 8).forEach((memory) => {
      const confidence = Math.round(Number(memory.confidence || 0) * 100);
      memoryStream.appendChild(
        brainStreamItem(
          memory.kind || "memory",
          `${memory.content || ""} · confidence ${confidence}%`
        )
      );
    });
  }

  const eventStream = document.getElementById("brain-event-stream");
  eventStream.replaceChildren();
  document.getElementById("brain-event-count").textContent = String(events.length);

  if (!events.length) {
    const empty = document.createElement("p");
    empty.className = "brain-empty";
    empty.textContent = "Жду событий ядра.";
    eventStream.appendChild(empty);
  } else {
    events.slice(0, 8).forEach((event) => {
      eventStream.appendChild(
        brainStreamItem(
          event.event_type || "event",
          `importance ${Number(event.importance || 0).toFixed(2)} · ${event.created_at || ""}`
        )
      );
    });
  }
}

function showDecisionReasoning(decision) {
  const reasoning = document.getElementById("brain-reasoning");
  const reasoningId = document.getElementById("brain-reasoning-id");

  reasoningId.textContent = `#${decision.id}`;

  const lines = [
    decision.rationale || "Причина не указана.",
    "",
    `Источник: ${decision.source || "core"}`,
    `Приоритет: ${Math.round(Number(decision.priority || 0) * 100)}%`,
    `Confidence: ${Math.round(Number(decision.confidence || 0) * 100)}%`,
    `Инструмент: ${humanTool(decision.tool_name)}`
  ];

  if (decision.capability) {
    lines.push(`Разрешение: ${decision.capability}`);
  }

  reasoning.textContent = lines.join("\n");
}

function renderSensors(sensors) {
  const grid = document.getElementById("sensor-cards");
  grid.replaceChildren();

  const labels = {
    runtime: "Runtime",
    planner: "Planner",
    modules: "Modules",
    filesystem: "Filesystem"
  };

  let attention = 0;
  sensors.forEach((sensor) => {
    if (sensor.status !== "ok") attention += 1;
    const card = document.createElement("article");
    card.className = "sensor-card";

    const label = document.createElement("span");
    label.textContent = labels[sensor.sensor] || sensor.sensor;

    const value = document.createElement("strong");
    const payload = sensor.payload || {};

    if (sensor.sensor === "runtime") {
      value.textContent = `${payload.status || "—"} · ${payload.activity || "—"}`;
    } else if (sensor.sensor === "planner") {
      value.textContent = `${payload.active_goals || 0} целей · ${payload.open_tasks || 0} задач`;
    } else if (sensor.sensor === "modules") {
      value.textContent = `${(payload.enabled || []).length} активных`;
    } else if (sensor.sensor === "filesystem") {
      value.textContent = `${payload.files || 0} файлов`;
    } else {
      value.textContent = sensor.status || "—";
    }

    card.append(label, value);
    grid.appendChild(card);
  });

  sensorState.textContent = attention
    ? `Сенсоры: ${attention} требуют внимания`
    : "Сенсоры: спокойно";
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

async function refreshDashboard(evaluate = false) {
  refreshApproval.disabled = true;
  try {
    if (evaluate) {
      await fetchJson("/api/assistant/proactive/evaluate?scope=personal", {
        method: "POST"
      });
    }

    const [state, pending, approved, sensors] = await Promise.all([
      fetchJson("/api/assistant/state"),
      fetchJson("/api/assistant/proactive/pending?scope=personal&limit=100"),
      fetchJson("/api/assistant/proactive/history?scope=personal&status=approved&limit=100"),
      fetchJson("/api/assistant/sensors?scope=personal")
    ]);

    pendingCount.textContent = String(pending.length);
    approvedCount.textContent = String(approved.length);
    document.getElementById("metric-decisions").textContent = String(pending.length);

    const memories = state.working_memory?.memories || [];
    const tasks = state.planner?.open_items?.tasks || [];
    const entities = state.knowledge_graph?.personal?.entities || 0;

    document.getElementById("metric-memory").textContent = String(memories.length);
    document.getElementById("metric-tasks").textContent = String(tasks.length);
    document.getElementById("metric-entities").textContent = String(entities);

    renderDecisions(
      pendingContainer,
      pending,
      "pending",
      "Сейчас нет решений, требующих Вашего подтверждения."
    );
    renderDecisions(
      approvedContainer,
      approved,
      "approved",
      "Нет одобренных действий, ожидающих выполнения."
    );
    renderSensors(sensors);
    renderLivingBrain(state, sensors, pending, approved);

    const center = document.querySelector(".approval-center");
    center.classList.remove("flash");
    void center.offsetWidth;
    center.classList.add("flash");
  } catch (error) {
    sensorState.textContent = "Связь с ядром нарушена";
    console.error("Approval Center:", error);
  } finally {
    refreshApproval.disabled = false;
  }
}

refreshApproval.addEventListener("click", () => refreshDashboard(true));

refreshDashboard(false);
setInterval(() => refreshDashboard(false), 30000);
