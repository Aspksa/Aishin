const logo = window.AISHIN_LOGO;
document.getElementById("brand-logo").src = logo;
document.getElementById("hero-logo").src = logo;
const chatLogo = document.getElementById("chat-logo");
if (chatLogo) chatLogo.src = logo;

const scopeSelect = document.getElementById("scope-select");
const savedScope = localStorage.getItem("aishin.scope") || "personal";
if (scopeSelect) {
  scopeSelect.value = Array.from(scopeSelect.options).some(
    (option) => option.value === savedScope
  ) ? savedScope : "personal";
}

function activeScope() {
  return scopeSelect?.value || localStorage.getItem("aishin.scope") || "personal";
}

function scopeUrl(url) {
  const value = encodeURIComponent(activeScope());
  return String(url).replace(/([?&])scope=personal\b/g, "$1scope=" + value);
}

window.AISHIN_SCOPE = {
  get: activeScope,
  url: scopeUrl,
  withScope(payload = {}) {
    return {...payload, scope: activeScope()};
  }
};

function refreshScopeAwareUi() {
  refreshDashboard(false);

  const active = document.querySelector(".module-page.active")?.id || "";
  const refreshByModule = {
    "communication-module": ["AISHIN_COMMUNICATION_REFRESH"],
    "attention-module": ["AISHIN_PROACTIVE_REFRESH"],
    "evolution-module": ["AISHIN_EVOLUTION_REFRESH"],
    "research-module": ["AISHIN_RESEARCH_REFRESH"],
    "documents-module": ["AISHIN_DOCUMENTS_REFRESH"],
    "development-module": [
      "AISHIN_GROWTH_REFRESH",
      "AISHIN_INTELLIGENCE_REFRESH"
    ]
  };

  if (active === "development-module") {
    refreshDevelopmentDetails(developmentDays);
  }

  (refreshByModule[active] || []).forEach((name) => {
    if (typeof window[name] === "function") window[name]();
  });

  const technical = document.querySelector(".technical-brain");
  const needsLiveBrain = Boolean(
    (technical && technical.open) ||
    active === "development-module" ||
    active === "settings-module"
  );
  if (
    needsLiveBrain &&
    typeof window.AISHIN_LIVE_BRAIN_REFRESH === "function"
  ) {
    window.AISHIN_LIVE_BRAIN_REFRESH();
  }
}

function renderScopeLabel() {
  const label = document.getElementById("scope-context-label");
  if (!label) return;
  label.textContent = activeScope() === "personal"
    ? "ЛИЧНОЕ ПРОСТРАНСТВО"
    : "ПРОЕКТНОЕ ПРОСТРАНСТВО · AISHIN";
}

scopeSelect?.addEventListener("change", () => {
  localStorage.setItem("aishin.scope", activeScope());
  renderScopeLabel();
  document.dispatchEvent(new CustomEvent("aishin:scope-change", {
    detail: {scope: activeScope()}
  }));
  refreshScopeAwareUi();
});
renderScopeLabel();

const pages = {
  assistant: {
    title: "Aishin Kitsune",
    description: "Личная помощница"
  },
  communication: {
    title: "Общение Айшин",
    description: "Понимание, стиль, адаптация объяснений и навыки диалога."
  },
  attention: {
    title: "Айши заметила",
    description: "Ситуации, аномалии, сроки и проактивное внимание."
  },
  evolution: {
    title: "Эволюция Айшин",
    description: "Самообучение, champion/challenger, curriculum и перенос опыта."
  },
  research: {
    title: "Исследования Айши",
    description: "Пробелы знаний, Evidence Ledger, claims и противоречия."
  },
  documents: {
    title: "Библиотека знаний",
    description: "Документы, страницы, provenance, версии и извлечение знаний."
  },
  account: {
    title: "Личный кабинет",
    description: "Интерфейс владельца пока не имеет отдельного backend-модуля.",
    readiness: "ПЛАНИРУЕТСЯ · BACKEND НЕ ПОДКЛЮЧЁН",
    available: "Уже работают: личный scope, профиль Айшин, память отношений и системные настройки.",
    next: "Следующий этап: отдельные API профиля владельца, права доступа и персональные параметры."
  },
  mobile: {
    title: "Мобильное приложение",
    description: "Мобильный клиент и транспорт синхронизации пока не реализованы.",
    readiness: "ПЛАНИРУЕТСЯ · КЛИЕНТ НЕ ПОДКЛЮЧЁН",
    available: "Сейчас Aishin работает через локальный web-интерфейс с адаптивной мобильной компоновкой.",
    next: "Следующий этап: защищённая авторизация устройства, sync API и отдельный мобильный клиент."
  },
  workspace: {
    title: "Рабочее пространство",
    description: "Отдельный workspace-backend ещё не выделен как самостоятельный модуль.",
    readiness: "ЧАСТИЧНО ДОСТУПНО · PROJECT SCOPE РАБОТАЕТ",
    available: "Уже работают: project:aishin scope, документы, Research, Knowledge Graph и инструменты проекта.",
    next: "Следующий этап: реестр проектов, переключение нескольких project scopes и права на рабочие области."
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
    } else if (code === "communication") {
      document.getElementById("communication-module")?.classList.add("active");
      if (typeof window.AISHIN_COMMUNICATION_REFRESH === "function") {
        window.AISHIN_COMMUNICATION_REFRESH();
      }
    } else if (code === "attention") {
      document.getElementById("attention-module")?.classList.add("active");
      if (typeof window.AISHIN_PROACTIVE_REFRESH === "function") {
        window.AISHIN_PROACTIVE_REFRESH();
      }
    } else if (code === "evolution") {
      document.getElementById("evolution-module")?.classList.add("active");
      if (typeof window.AISHIN_EVOLUTION_REFRESH === "function") {
        window.AISHIN_EVOLUTION_REFRESH();
      }
    } else if (code === "research") {
      document.getElementById("research-module")?.classList.add("active");
      if (typeof window.AISHIN_RESEARCH_REFRESH === "function") {
        window.AISHIN_RESEARCH_REFRESH();
      }
    } else if (code === "documents") {
      document.getElementById("documents-module")?.classList.add("active");
      if (typeof window.AISHIN_DOCUMENTS_REFRESH === "function") {
        window.AISHIN_DOCUMENTS_REFRESH();
      }
    } else if (code === "settings") {
      document.getElementById("settings-module").classList.add("active");
      refreshCloudSettings();
      refreshUpdateMode();
    } else {
      const placeholder = pages[code] || {
        title: "Модуль",
        description: "Модуль пока не подключён.",
        readiness: "НЕ ПОДКЛЮЧЁН",
        available: "Рабочих API этого раздела пока нет.",
        next: "Функциональность будет добавлена отдельным проверяемым релизом."
      };
      document.getElementById("placeholder-title").textContent = placeholder.title;
      document.getElementById("placeholder-description").textContent = placeholder.description;
      document.getElementById("placeholder-readiness").textContent = placeholder.readiness || "НЕ ПОДКЛЮЧЁН";
      document.getElementById("placeholder-available").textContent = placeholder.available || "—";
      document.getElementById("placeholder-next").textContent = placeholder.next || "—";
      document.getElementById("placeholder-scope").textContent = activeScope();
      document.getElementById("placeholder-module").classList.add("active");
    }
  });
});

const developmentOpen = document.getElementById("development-open");
const developmentBack = document.getElementById("development-back");
let developmentDays = 30;

function openDevelopmentPage() {
  document.querySelectorAll(".nav-item[data-module]").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".module-page").forEach((page) => page.classList.remove("active"));
  document.getElementById("development-module")?.classList.add("active");
  document.getElementById("page-title").textContent = "Развитие Айшин";
  refreshDevelopmentDetails(developmentDays);
}

function closeDevelopmentPage() {
  document.querySelectorAll(".module-page").forEach((page) => page.classList.remove("active"));
  document.getElementById("assistant-module")?.classList.add("active");
  document.querySelector('.nav-item[data-module="assistant"]')?.classList.add("active");
  document.getElementById("page-title").textContent = pages.assistant.title;
}

developmentOpen?.addEventListener("click", openDevelopmentPage);
developmentBack?.addEventListener("click", closeDevelopmentPage);

document.querySelectorAll("[data-development-days]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-development-days]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    developmentDays = Number(button.dataset.developmentDays || 30);
    refreshDevelopmentDetails(developmentDays);
  });
});

function formatDevelopmentNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value || 0));
}

function developmentPhrase(score, delta) {
  if (score <= 0) return "Я только начинаю накапливать подтверждённый опыт.";
  if (delta > 0.2) return "Я расту на подтверждённом опыте и становлюсь точнее.";
  if (delta < -0.2) return "Я обнаружила слабые места и честно учитываю их в развитии.";
  return "Я продолжаю учиться на реальной работе.";
}

function setDevelopmentRing(element, score) {
  if (!element) return;
  const bounded = Math.max(0, Math.min(100, Number(score || 0)));
  element.style.setProperty("--development-score", String(bounded));
}

function renderDevelopmentCompact(development) {
  if (!development) return;
  const score = Number(development.overall_score || 0);
  const delta = Number(development.monthly_delta || 0);
  const scoreEl = document.getElementById("development-score");
  const deltaEl = document.getElementById("development-delta");
  const phraseEl = document.getElementById("development-phrase");
  if (scoreEl) scoreEl.textContent = `${score.toFixed(1)}%`;
  if (deltaEl) {
    const sign = delta > 0 ? "+" : "";
    deltaEl.textContent = `${sign}${delta.toFixed(1)}%`;
    deltaEl.classList.toggle("negative", delta < 0);
  }
  if (phraseEl) phraseEl.textContent = developmentPhrase(score, delta);
  setDevelopmentRing(document.getElementById("development-ring"), score);

  const mini = document.getElementById("development-mini-components");
  if (mini) {
    const keys = [
      ["memory", "◈", "Память"],
      ["accuracy", "✓", "Точность"],
      ["error_learning", "↻", "Ошибки"],
      ["strategies", "◇", "Стратегии"]
    ];
    mini.replaceChildren();
    keys.forEach(([key, icon, label]) => {
      const item = document.createElement("span");
      const iconEl = document.createElement("b");
      iconEl.textContent = icon;
      const text = document.createTextNode(` ${label} `);
      const value = document.createElement("strong");
      value.textContent = `${Number(development.components?.[key]?.score || 0).toFixed(0)}%`;
      item.append(iconEl, text, value);
      mini.appendChild(item);
    });
  }
}

function renderDevelopmentList(containerId, items, emptyText, formatter) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.replaceChildren();
  if (!items?.length) {
    const empty = document.createElement("p");
    empty.className = "brain-empty";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "development-list-item";
    const data = formatter(item);
    const icon = document.createElement("span");
    icon.className = "development-list-icon";
    icon.textContent = data.icon || "✦";
    const copy = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = data.title;
    const small = document.createElement("small");
    small.textContent = data.detail || "";
    copy.append(strong, small);
    row.append(icon, copy);
    container.appendChild(row);
  });
}

function renderDevelopmentDetails(current, history) {
  if (!current) return;
  const score = Number(current.overall_score || 0);
  const delta = Number(current.monthly_delta || 0);
  const detailScore = document.getElementById("development-detail-score");
  const detailDelta = document.getElementById("development-detail-delta");
  const detailTitle = document.getElementById("development-detail-title");
  if (detailScore) detailScore.textContent = `${score.toFixed(1)}%`;
  if (detailDelta) {
    const sign = delta > 0 ? "+" : "";
    detailDelta.textContent = `${sign}${delta.toFixed(1)}%`;
    detailDelta.classList.toggle("negative", delta < 0);
  }
  if (detailTitle) detailTitle.textContent = developmentPhrase(score, delta);
  const principle = document.getElementById("development-principle");
  if (principle) principle.textContent = current.principle || "";
  setDevelopmentRing(document.getElementById("development-detail-ring"), score);

  const componentContainer = document.getElementById("development-components");
  if (componentContainer) {
    componentContainer.replaceChildren();
    const order = [
      "memory", "knowledge", "connections", "analytics",
      "accuracy", "error_learning", "strategies", "user_help"
    ];
    order.forEach((key) => {
      const item = current.components?.[key];
      if (!item) return;
      const card = document.createElement("article");
      card.className = "development-component-card";
      const head = document.createElement("div");
      head.className = "development-component-head";
      const icon = document.createElement("span");
      icon.textContent = item.icon || "✦";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.label;
      const weight = document.createElement("small");
      weight.textContent = `вклад ${Number(item.weight || 0).toFixed(0)}%`;
      copy.append(title, weight);
      const value = document.createElement("b");
      value.textContent = `${Number(item.score || 0).toFixed(1)}%`;
      head.append(icon, copy, value);

      const bar = document.createElement("div");
      bar.className = "development-progress";
      const fill = document.createElement("i");
      fill.style.width = `${Math.max(0, Math.min(100, Number(item.score || 0)))}%`;
      bar.appendChild(fill);

      const evidence = document.createElement("p");
      evidence.textContent = item.evidence || "";
      card.append(head, bar, evidence);
      componentContainer.appendChild(card);
    });
  }

  renderDevelopmentList(
    "development-reasons",
    current.growth_reasons,
    "История ещё недостаточна для сравнения.",
    (item) => ({
      icon: Number(item.value || 0) < 0 ? "↓" : "↑",
      title: item.text || "Изменение",
      detail: item.kind === "history" ? "Нужны новые снимки развития." : "Подтверждено сохранёнными данными."
    })
  );
  renderDevelopmentList(
    "development-learning",
    current.learning_now,
    "Сейчас нет открытых целей обучения.",
    (item) => ({
      icon: "↻",
      title: item.topic || "Цель обучения",
      detail: `${item.rationale || "Обучение по накопленному опыту"} · приоритет ${Math.round(Number(item.priority || 0) * 100)}%`
    })
  );
  renderDevelopmentList(
    "development-mastered",
    current.mastered,
    "Trusted-навыки ещё накапливают доказательства.",
    (item) => ({
      icon: "✓",
      title: item.pattern_key || item.category || "Проверенный паттерн",
      detail: `${item.category || "опыт"} · качество ${Math.round(Number(item.effective_score || 0) * 100)}% · наблюдений ${item.observations || 0}`
    })
  );
  renderDevelopmentList(
    "development-needs",
    current.growth_needs,
    "Точки роста будут рассчитаны после появления данных.",
    (item) => ({
      icon: item.icon || "◇",
      title: `${item.label || "Направление"} — ${Number(item.score || 0).toFixed(1)}%`,
      detail: item.why || ""
    })
  );

  const counters = current.counters || {};
  const counterMap = {
    "dev-count-experience": counters.experience_events,
    "dev-count-knowledge": counters.knowledge_items,
    "dev-count-links": counters.connections,
    "dev-count-documents": counters.studied_documents,
    "dev-count-patterns": counters.trusted_patterns,
    "dev-count-hypotheses": counters.confirmed_hypotheses,
    "dev-count-errors": counters.error_signals,
    "dev-count-strategies": counters.trusted_strategies
  };
  Object.entries(counterMap).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = formatDevelopmentNumber(value);
  });

  renderDevelopmentChart(history || []);
}

function renderDevelopmentChart(history) {
  const svg = document.getElementById("development-chart");
  const empty = document.getElementById("development-chart-empty");
  if (!svg || !empty) return;
  svg.replaceChildren();

  if (!history?.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  const values = history.map((item) => Number(item.overall_score || 0));
  const width = 800;
  const height = 220;
  const padX = 42;
  const padY = 24;
  const usableW = width - padX * 2;
  const usableH = height - padY * 2;
  const min = Math.max(0, Math.min(...values) - 5);
  const max = Math.min(100, Math.max(...values) + 5);
  const span = Math.max(1, max - min);
  const ns = "http://www.w3.org/2000/svg";

  [0, 0.5, 1].forEach((ratio) => {
    const y = padY + usableH * ratio;
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", String(padX));
    line.setAttribute("x2", String(width - padX));
    line.setAttribute("y1", String(y));
    line.setAttribute("y2", String(y));
    line.setAttribute("class", "development-chart-grid");
    svg.appendChild(line);
  });

  const points = history.map((item, index) => {
    const x = history.length === 1
      ? width / 2
      : padX + (usableW * index) / (history.length - 1);
    const value = Number(item.overall_score || 0);
    const y = padY + usableH * (1 - (value - min) / span);
    return {x, y, value, created_at: item.created_at};
  });

  if (points.length > 1) {
    const path = document.createElementNS(ns, "polyline");
    path.setAttribute("points", points.map((p) => `${p.x},${p.y}`).join(" "));
    path.setAttribute("class", "development-chart-line");
    svg.appendChild(path);
  }

  points.forEach((point, index) => {
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", String(point.x));
    dot.setAttribute("cy", String(point.y));
    dot.setAttribute("r", index === points.length - 1 ? "5" : "3");
    dot.setAttribute("class", "development-chart-dot");
    const title = document.createElementNS(ns, "title");
    title.textContent = `${point.value.toFixed(1)}% · ${point.created_at || ""}`;
    dot.appendChild(title);
    svg.appendChild(dot);
  });
}

async function refreshDevelopmentDetails(days = 30) {
  try {
    const data = await fetchJson(scopeUrl(`/api/assistant/development?scope=personal&days=${days}`));
    renderDevelopmentCompact(data.current);
    renderDevelopmentDetails(data.current, data.history);
  } catch (error) {
    console.error("Development Metrics:", error);
  }
}

const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const messages = document.getElementById("messages");

function addMessage(text, who, meta = {}) {
  const el = document.createElement("div");
  el.className = `message ${who}`;

  if (who === "aishin") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    const img = document.createElement("img");
    img.src = logo;
    img.alt = "";
    avatar.appendChild(img);

    const body = document.createElement("div");
    body.className = "message-body";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    body.appendChild(bubble);

    if (meta.turnId) {
      const feedback = document.createElement("div");
      feedback.className = "chat-communication-feedback";
      [
        ["useful", "Полезно"],
        ["misunderstood", "Не поняла"],
        ["too_long", "Длинно"],
        ["too_short", "Коротко"]
      ].forEach(([code, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.addEventListener("click", async () => {
          feedback.querySelectorAll("button").forEach((item) => {
            item.disabled = true;
          });
          try {
            const response = await fetch(
              `/api/assistant/communication/turns/${meta.turnId}/feedback`,
              {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                  scope: activeScope(),
                  feedback: code,
                  reason: "inline chat feedback"
                })
              }
            );
            if (!response.ok) throw new Error("Feedback HTTP " + response.status);
            feedback.dataset.saved = "true";
            button.classList.add("selected");
            if (typeof window.AISHIN_COMMUNICATION_REFRESH === "function") {
              window.AISHIN_COMMUNICATION_REFRESH();
            }
          } catch (error) {
            feedback.querySelectorAll("button").forEach((item) => {
              item.disabled = false;
            });
            console.error("Communication feedback:", error);
          }
        });
        feedback.appendChild(button);
      });
      body.appendChild(feedback);
    }

    el.append(avatar, body);
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
      body: JSON.stringify({message, scope: activeScope()})
    });
    const data = await response.json();
    addMessage(
      data.reply || "Не удалось получить ответ.",
      "aishin",
      {turnId: data.communication?.turn?.id}
    );
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
      scope: activeScope(),
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
      await fetchJson(scopeUrl("/api/assistant/proactive/evaluate?scope=personal"), {
        method: "POST"
      });
    }

    const [state, pending, approved, sensors] = await Promise.all([
      fetchJson(scopeUrl("/api/assistant/state?scope=personal")),
      fetchJson(scopeUrl("/api/assistant/proactive/pending?scope=personal&limit=100")),
      fetchJson(scopeUrl("/api/assistant/proactive/history?scope=personal&status=approved&limit=100")),
      fetchJson(scopeUrl("/api/assistant/sensors?scope=personal"))
    ]);

    pendingCount.textContent = String(pending.length);
    approvedCount.textContent = String(approved.length);
    document.getElementById("metric-decisions").textContent = String(pending.length);

    const memories = state.working_memory?.memories || [];
    const tasks = state.planner?.open_items?.tasks || [];
    const entities = (
      state.knowledge_graph?.current?.entities
      ?? state.knowledge_graph?.personal?.entities
      ?? 0
    );

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
    renderDevelopmentCompact(state.development);
    if (document.getElementById("development-module")?.classList.contains("active")) {
      refreshDevelopmentDetails(developmentDays);
    }

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

function syncTechnicalBrainHash() {
  if (!technicalBrain || window.location.hash !== "#technical-brain") return;
  technicalBrain.open = true;
  requestAnimationFrame(() => {
    renderNeuralLinks();
    technicalBrain.scrollIntoView({ block: "start", behavior: "auto" });
  });
}

technicalBrain?.addEventListener("toggle", () => {
  if (technicalBrain.open) {
    refreshDashboard(false);
    requestAnimationFrame(renderNeuralLinks);
  }
});
window.addEventListener("hashchange", syncTechnicalBrainHash);
window.addEventListener("resize", () => requestAnimationFrame(renderNeuralLinks));
syncTechnicalBrainHash();

async function liveRefreshLoop() {
  if (!document.hidden) {
    await refreshDashboard(false);
  }
  // Live Brain now uses a lightweight SSE pulse. The heavy aggregate snapshot
  // is intentionally refreshed slowly to avoid SQLite/UI pressure.
  const delay = document.hidden ? 60000 : 45000;
  window.setTimeout(liveRefreshLoop, delay);
}

refreshCloudSettings();
refreshUpdateMode();
liveRefreshLoop();
