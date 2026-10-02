const logo = window.AISHIN_LOGO;
document.getElementById("brand-logo").src = logo;
document.getElementById("hero-logo").src = logo;
const chatLogo = document.getElementById("chat-logo");
if (chatLogo) chatLogo.src = logo;

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
  },
  settings: {
    title: "Настройки",
    description: "Подключение Cloud.ru и параметры системы."
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
    } else if (code === "settings") {
      document.getElementById("settings-module").classList.add("active");
      refreshCloudSettings();
      refreshUpdateMode();
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

  if (who === "aishin") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    const img = document.createElement("img");
    img.src = logo;
    img.alt = "";
    avatar.appendChild(img);

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    el.append(avatar, bubble);
  } else {
    el.textContent = text;
  }

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
  status.textContent = "Проверяю обновление...";
  try {
    const response = await fetch("/api/system/update", {method: "POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Ошибка обновления");
    const mode = data.mode === "zip" ? "ZIP" : "Git";
    status.textContent = `Обновлено через ${mode}. Перезапустите Aishin.bat`;
  } catch (error) {
    status.textContent = "Ошибка: " + error.message;
  }
});


const cloudApiKey = document.getElementById("cloud-api-key");
const cloudSaveBtn = document.getElementById("cloud-save-btn");
const cloudTestBtn = document.getElementById("cloud-test-btn");
const cloudStatusBadge = document.getElementById("cloud-status-badge");
const cloudSettingsMessage = document.getElementById("cloud-settings-message");

function renderCloudStatus(data) {
  if (!cloudStatusBadge) return;
  const configured = Boolean(data.configured);
  const available = Boolean(data.available);
  cloudStatusBadge.className = "settings-badge " + (available ? "ok" : configured ? "error" : "");
  cloudStatusBadge.textContent = available
    ? "подключено"
    : configured
      ? "ключ сохранён · нет связи"
      : "ключ не настроен";
  const model = document.getElementById("cloud-model");
  const embedding = document.getElementById("cloud-embedding-model");
  if (model) model.textContent = data.model || "—";
  if (embedding) embedding.textContent = data.embedding_model || "—";
}

async function refreshCloudSettings() {
  if (!cloudStatusBadge) return;
  try {
    const data = await fetchJson("/api/settings/cloudru");
    renderCloudStatus(data);
    if (cloudSettingsMessage) {
      cloudSettingsMessage.textContent = data.error || (data.available ? "Cloud.ru готов." : "");
    }
  } catch (error) {
    cloudStatusBadge.className = "settings-badge error";
    cloudStatusBadge.textContent = "ошибка";
    if (cloudSettingsMessage) cloudSettingsMessage.textContent = error.message;
  }
}

async function refreshUpdateMode() {
  const badge = document.getElementById("update-mode-badge");
  if (!badge) return;
  try {
    const data = await fetchJson("/api/system/update/status");
    badge.textContent = data.mode === "zip" ? "ZIP-режим" : "Git-режим";
    badge.className = "settings-badge ok";
  } catch (error) {
    badge.textContent = "не определено";
    badge.className = "settings-badge error";
  }
}

cloudSaveBtn?.addEventListener("click", async () => {
  const key = cloudApiKey?.value.trim() || "";
  if (!key) {
    cloudSettingsMessage.textContent = "Вставьте API-ключ Cloud.ru.";
    return;
  }
  cloudSaveBtn.disabled = true;
  cloudSettingsMessage.textContent = "Сохраняю и проверяю...";
  try {
    const data = await fetchJson("/api/settings/cloudru", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({api_key: key})
    });
    if (cloudApiKey) cloudApiKey.value = "";
    renderCloudStatus({
      ...data.settings,
      available: Boolean(data.health?.available),
      error: data.health?.error
    });
    cloudSettingsMessage.textContent = data.health?.available
      ? "Ключ сохранён. Cloud.ru подключён."
      : `Ключ сохранён, но проверка не прошла: ${data.health?.error || "нет связи"}`;
  } catch (error) {
    cloudSettingsMessage.textContent = "Ошибка: " + error.message;
  } finally {
    cloudSaveBtn.disabled = false;
  }
});

cloudTestBtn?.addEventListener("click", async () => {
  cloudTestBtn.disabled = true;
  cloudSettingsMessage.textContent = "Проверяю Cloud.ru...";
  try {
    const data = await fetchJson("/api/settings/cloudru/test", {method: "POST"});
    const health = data.health || {};
    renderCloudStatus({
      configured: Boolean(health.configured),
      available: Boolean(health.available),
      model: health.model,
      embedding_model: document.getElementById("cloud-embedding-model")?.textContent
    });
    cloudSettingsMessage.textContent = health.available
      ? `Подключение работает · ${health.latency_ms || 0} мс`
      : `Подключение не работает: ${health.error || "неизвестная ошибка"}`;
  } catch (error) {
    cloudSettingsMessage.textContent = "Ошибка: " + error.message;
  } finally {
    cloudTestBtn.disabled = false;
  }
});

const pendingContainer = document.getElementById("pending-decisions");
const approvedContainer = document.getElementById("approved-decisions");
const pendingCount = document.getElementById("pending-count");
const approvedCount = document.getElementById("approved-count");
const sensorState = document.getElementById("sensor-state");
const refreshApproval = document.getElementById("refresh-approval");

function humanLearningMode(mode) {
  const names = {
    REALTIME: "в разговоре",
    BACKGROUND: "учу в фоне",
    IDLE: "спокойно",
    MAINTENANCE: "обслуживание"
  };
  return names[mode] || "спокойно";
}

function humanMetaStatus(status) {
  const names = {
    confident: "уверена",
    cautious: "проверяю",
    needs_verification: "нужна перепроверка",
    insufficient_data: "мало данных"
  };
  return names[status] || "спокойно";
}

function humanLogicMode(mode) {
  const names = {
    FAST: "быстро",
    DEEP: "глубоко",
    VERIFY: "перепроверяю",
    PLAN: "планирую",
    DIAGNOSE: "диагностика"
  };
  return names[mode] || "ожидание";
}

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


function renderNeuralLinks() {
  const reflectionQualityEl = document.getElementById("reflection-quality");
  const weakSpotsEl = document.getElementById("reflection-weak-spots");
  if (reflectionQualityEl) {
    reflectionQualityEl.textContent =
      latestReflection || reflectionSummary.samples
        ? `${Math.round(reflectionQuality * 100)}%`
        : "—";
  }
  if (weakSpotsEl) {
    weakSpotsEl.replaceChildren();
    const weakItems = reflectionWeak.length
      ? reflectionWeak.map((name) => [name, 1])
      : Object.entries(reflectionSummary.weak_spots || {});
    if (!weakItems.length) {
      const empty = document.createElement("p");
      empty.className = "brain-empty";
      empty.textContent = "Слабые места не обнаружены.";
      weakSpotsEl.appendChild(empty);
    } else {
      weakItems.slice(0, 6).forEach(([name, count]) => {
        weakSpotsEl.appendChild(
          brainStreamItem(
            String(name),
            Number(count) > 1 ? `повторений: ${count}` : "обнаружено в последнем анализе"
          )
        );
      });
    }
  }

  const learningPlanCount = document.getElementById("learning-plan-count");
  const learningPlanStream = document.getElementById("learning-plan-stream");
  if (learningPlanCount) learningPlanCount.textContent = String(learningPlans.length);
  if (learningPlanStream) {
    learningPlanStream.replaceChildren();
    if (!learningPlans.length) {
      const empty = document.createElement("p");
      empty.className = "brain-empty";
      empty.textContent = "Повторяющихся слабых мест пока недостаточно для цели.";
      learningPlanStream.appendChild(empty);
    } else {
      learningPlans.slice(0, 5).forEach((plan) => {
        learningPlanStream.appendChild(
          brainStreamItem(
            plan.topic || "цель обучения",
            `${plan.rationale || ""} · приоритет ${Math.round(Number(plan.priority || 0) * 100)}%`
          )
        );
      });
    }
  }

  const experimentCount = document.getElementById("experiment-count");
  const experimentStream = document.getElementById("experiment-stream");
  if (experimentCount) experimentCount.textContent = String(experiments.length);
  if (experimentStream) {
    experimentStream.replaceChildren();
    if (!experiments.length) {
      const empty = document.createElement("p");
      empty.className = "brain-empty";
      empty.textContent = "Shadow-эксперименты появятся из целей обучения.";
      experimentStream.appendChild(empty);
    } else {
      experiments.slice(0, 5).forEach((item) => {
        const baseline = Math.round(Number(item.baseline_score || 0) * 100);
        const candidate = Math.round(Number(item.candidate_score || 0) * 100);
        experimentStream.appendChild(
          brainStreamItem(
            item.name || "эксперимент",
            `${item.status || "shadow"} · ${item.observed_samples || 0}/${item.required_samples || 0} · baseline ${baseline}% → candidate ${candidate}%`
          )
        );
      });
    }
  }

  const budgetValue = document.getElementById("context-budget-value");
  const budgetDetail = document.getElementById("context-budget-detail");
  if (budgetValue) {
    budgetValue.textContent = contextBudget
      ? `${contextBudget.estimated_tokens_after || 0}/${contextBudget.token_budget || 0}`
      : "—";
  }
  if (budgetDetail) {
    budgetDetail.textContent = contextBudget
      ? `До: ~${contextBudget.estimated_tokens_before || 0} токенов\nПосле: ~${contextBudget.estimated_tokens_after || 0}\nСокращено символов: ${contextBudget.trimmed_chars || 0}\nИстория: ${contextBudget.history_before ?? "—"} → ${contextBudget.history_after ?? "—"}`
      : "Budgeter ещё не выполнялся.";
  }

  const flow = document.getElementById("brain-flow");
  const svg = document.getElementById("brain-links");
  if (!flow || !svg || !flow.closest("details")?.open) return;

  const nodes = [...flow.querySelectorAll(".brain-node")];
  const flowRect = flow.getBoundingClientRect();
  svg.setAttribute("viewBox", `0 0 ${Math.max(1, flowRect.width)} ${Math.max(1, flowRect.height)}`);
  svg.replaceChildren();

  const pairs = [];
  for (let i = 0; i < Math.min(nodes.length - 1, 18); i += 1) {
    pairs.push([i, i + 1]);
  }
  [[0,4],[1,5],[2,8],[4,9],[5,10],[8,14],[9,15],[10,16],
   [14,17],[15,17],[16,17],[17,18],
   [14,19],[19,20],[20,21],[21,22],[22,23],[23,14]]
    .forEach(([a,b]) => {
      if (nodes[a] && nodes[b]) pairs.push([a,b]);
    });

  pairs.forEach(([a,b]) => {
    const from = nodes[a];
    const to = nodes[b];
    const aRect = from.getBoundingClientRect();
    const bRect = to.getBoundingClientRect();
    const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const x1 = aRect.left + aRect.width / 2 - flowRect.left;
    const y1 = aRect.top + aRect.height / 2 - flowRect.top;
    const x2 = bRect.left + bRect.width / 2 - flowRect.left;
    const y2 = bRect.top + bRect.height / 2 - flowRect.top;
    const bend = Math.max(18, Math.abs(x2 - x1) * 0.28);
    const d = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
    line.setAttribute("d", d);
    line.setAttribute("class", "brain-link-line");
    if (from.classList.contains("active") && to.classList.contains("active")) {
      line.classList.add("active");
    }
    if (from.classList.contains("attention") || to.classList.contains("attention")) {
      line.classList.add("attention");
    }
    svg.appendChild(line);
  });
}

function renderLivingBrain(state, sensors, pending, approved) {
  const runtime = state.state || {};
  const memories = state.working_memory?.memories || [];
  const graph = state.knowledge_graph?.personal || {};
  const tasks = state.planner?.open_items?.tasks || [];
  const events = state.recent_events || [];
  const actions = state.tools?.recent_actions || [];

  const focusText = runtime.focus || runtime.activity || "ожидание";
  document.getElementById("brain-focus-value").textContent = focusText;

  const simpleFocus = document.getElementById("simple-focus");
  if (simpleFocus) {
    const focusNames = {
      conversation: "разговор",
      waiting: "ожидаю",
      idle: "спокойно"
    };
    simpleFocus.textContent = focusNames[focusText] || focusText;
  }

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
  const continuousLearning = state.continuous_learning || null;
  const reflectionSummary = state.self_reflection?.summary || {};
  const latestReflection =
    state.working_memory?.self_reflection ||
    state.self_reflection?.recent?.[0] ||
    null;
  const learningPlans = state.learning_planner?.open || [];
  const experiments = state.safe_experiments || [];
  const contextBudget =
    state.working_memory?.context_budget ||
    state.context_budget?.[0] ||
    null;
  const readyExperiments = experiments.filter(
    (item) => item.status === "ready_for_review"
  );

  const learningStatusSimple = continuousLearning?.status || {};
  const trustedSimple = (continuousLearning?.patterns || []).filter(
    (item) => item.lifecycle === "trusted"
  ).length;
  const simpleMode = document.getElementById("simple-mode");
  const simpleLearning = document.getElementById("simple-learning");
  const simpleTrusted = document.getElementById("simple-trusted");
  if (simpleMode) simpleMode.textContent = humanLearningMode(learningStatusSimple.mode);
  if (simpleLearning) {
    simpleLearning.textContent =
      learningStatusSimple.worker_status === "error"
        ? "нужна проверка"
        : humanLearningMode(learningStatusSimple.mode);
  }
  if (simpleTrusted) {
    simpleTrusted.textContent = `${trustedSimple} проверенных`;
  }

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
      ? `${humanLogicMode(logic.mode)} · сложность ${Math.round(Number(logic.complexity || 0) * 100)}%`
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
      ? `${causal.claims?.length || 0} связей · ${causal.unresolved?.length || 0} требуют проверки`
      : "причинные связи не требуются"
  );

  setBrainNode(
    "hypotheses",
    Boolean(hypotheses),
    Boolean(hypotheses?.selected_test && Object.keys(hypotheses.selected_test).length),
    hypotheses
      ? `${hypotheses.hypotheses?.length || 0} гипотез · анализ выполнен`
      : "гипотезы ещё не строились"
  );

  setBrainNode(
    "learning",
    Boolean(learning),
    false,
    learning?.feedback?.applied
      ? `обратная связь учтена · надёжность ${Math.round(Number(learning.feedback.reliability || 0) * 100)}%`
      : `${learning?.strategies?.length || 0} изученных стратегий`
  );

  setBrainNode(
    "counterfactual",
    Boolean(counterfactual),
    Boolean(counterfactual?.unresolved?.length),
    counterfactual
      ? `${counterfactual.scenarios?.length || 0} вариантов · ${counterfactual.unresolved?.length || 0} требуют проверки`
      : "альтернативы ещё не требовались"
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
      ? `полезность ${Math.round(Number(actionSelection.selected.utility || 0) * 100)}% · вариант выбран`
      : "действие ещё не выбиралось"
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
      ? `${activeApprovals.length} ждут подтверждения`
      : latestAttempt
        ? `последнее действие: ${latestAttempt.status}`
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

  const learningStatus = continuousLearning?.status || null;
  setBrainNode(
    "continuous-learning",
    Boolean(learningStatus),
    learningStatus?.worker_status === "error",
    learningStatus
      ? `${humanLearningMode(learningStatus.mode)} · очередь ${learningStatus.queue?.pending || 0} · проверено ${(continuousLearning?.patterns || []).filter((item) => item.lifecycle === "trusted").length}`
      : "самообучение ещё не запускалось"
  );

  const reflectionQuality = Number(
    latestReflection?.quality_score ?? reflectionSummary.average_quality ?? 0
  );
  const reflectionWeak = latestReflection?.weak_spots || [];
  setBrainNode(
    "reflection",
    Boolean(latestReflection || reflectionSummary.samples),
    reflectionQuality > 0 && reflectionQuality < 0.70,
    latestReflection || reflectionSummary.samples
      ? `качество ${Math.round(reflectionQuality * 100)}% · слабых мест ${reflectionWeak.length || Object.keys(reflectionSummary.weak_spots || {}).length}`
      : "самоанализ ещё не накопил данные"
  );

  setBrainNode(
    "learning-plan",
    learningPlans.length > 0,
    learningPlans.some((item) => Number(item.priority || 0) >= 0.8),
    learningPlans.length
      ? `${learningPlans.length} целей · приоритет ${Math.round(Number(learningPlans[0]?.priority || 0) * 100)}%`
      : "цели обучения ещё не сформированы"
  );

  setBrainNode(
    "experiment",
    experiments.length > 0,
    false,
    experiments.length
      ? `${experiments.length} shadow · наблюдений ${experiments.reduce((sum, item) => sum + Number(item.observed_samples || 0), 0)}`
      : "безопасные эксперименты ещё не запущены"
  );

  setBrainNode(
    "learning-check",
    experiments.length > 0,
    readyExperiments.length > 0,
    readyExperiments.length
      ? `${readyExperiments.length} готовы к ручной проверке`
      : experiments.length
        ? "сравнение baseline/candidate продолжается"
        : "проверять пока нечего"
  );

  setBrainNode(
    "consolidation",
    trustedSimple > 0,
    false,
    trustedSimple
      ? `${trustedSimple} trusted · закреплены качеством`
      : "доверенные паттерны ещё не закреплены"
  );

  const simpleSteps = {
    context: document.getElementById("simple-step-context"),
    memory: document.getElementById("simple-step-memory"),
    reason: document.getElementById("simple-step-reason"),
    answer: document.getElementById("simple-step-answer")
  };
  Object.values(simpleSteps).forEach((el) => el?.classList.remove("active"));
  if (contextTrace) simpleSteps.context?.classList.add("active");
  if (memories.length) simpleSteps.memory?.classList.add("active");
  if (logic || meta) simpleSteps.reason?.classList.add("active");
  if (runtime.activity === "conversation") simpleSteps.answer?.classList.add("active");

  const metaStatus = meta?.status || "нет оценки";
  const metaAttention = ["needs_verification", "insufficient_data"].includes(metaStatus);
  setBrainNode(
    "metacognition",
    Boolean(meta),
    metaAttention,
    meta
      ? `${humanMetaStatus(metaStatus)} · ${Math.round(Number(meta.confidence || 0) * 100)}%`
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
  requestAnimationFrame(renderNeuralLinks);

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
          `${memory.content || ""} · уверенность ${confidence}%`
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
          `важность ${Number(event.importance || 0).toFixed(2)} · ${event.created_at || ""}`
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
    `Уверенность: ${Math.round(Number(decision.confidence || 0) * 100)}%`,
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

const technicalBrain = document.querySelector(".technical-brain");
technicalBrain?.addEventListener("toggle", () => {
  if (technicalBrain.open) {
    refreshDashboard(false);
    requestAnimationFrame(renderNeuralLinks);
  }
});
window.addEventListener("resize", () => requestAnimationFrame(renderNeuralLinks));

async function liveRefreshLoop() {
  await refreshDashboard(false);
  const delay = technicalBrain?.open ? 3000 : 20000;
  window.setTimeout(liveRefreshLoop, delay);
}

refreshCloudSettings();
refreshUpdateMode();
liveRefreshLoop();
