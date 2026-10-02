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
