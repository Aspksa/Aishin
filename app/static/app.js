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
    actions.append(
      actionButton("Одобрить", "approve", async () => {
        await decisionRequest(decision.id, "approve", {execute: false});
      }),
      actionButton("Отклонить", "reject", async () => {
        await decisionRequest(decision.id, "reject", {reason: "Отклонено Господином через Approval Center"});
      })
    );
  } else if (mode === "approved") {
    if (decision.tool_name) {
      actions.append(
        actionButton("Выполнить", "execute", async () => {
          await decisionRequest(decision.id, "execute", {});
        })
      );
    } else {
      actions.append(
        actionButton("Закрыть", "reject", async () => {
          await decisionRequest(decision.id, "reject", {reason: "Информационное решение просмотрено"});
        })
      );
    }
  }

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
  } else {
    addMessage(`Решение #${id} отклонено.`, "aishin");
  }

  await refreshDashboard(false);
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

    const memories = state.recent_memories || [];
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
