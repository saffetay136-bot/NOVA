const messagesElement = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const input = document.querySelector("#messageInput");
const locationButton = document.querySelector("#locationButton");

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value;
  return element.innerHTML;
}

function renderMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `<div class="bubble">${escapeHtml(content)}</div>`;
  messagesElement.appendChild(article);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

async function loadMessages() {
  const response = await fetch("/api/messages");
  if (!response.ok) return;
  const messages = await response.json();
  messagesElement.innerHTML = "";
  messages.forEach((message) => renderMessage(message.role, message.content));
  if (!messages.length) {
    renderMessage("assistant", "Merhaba. Nasıl yardımcı olabilirim?");
  }
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  input.style.height = "auto";
  renderMessage("user", message);
  renderMessage("assistant", "Yazıyor...");

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({message})
  });
  const data = await response.json();
  messagesElement.querySelector(".message.assistant:last-child")?.remove();
  renderMessage("assistant", data.answer || data.error || "Yanıt alınamadı.");
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
});
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

document.querySelector("#logoutButton").addEventListener("click", async () => {
  await fetch("/api/logout", {method: "POST"});
  location.href = "/login";
});

document.querySelector("#newChat").addEventListener("click", () => {
  messagesElement.innerHTML = "";
  renderMessage("assistant", "Yeni sohbet hazır.");
  input.focus();
});

locationButton.addEventListener("click", () => {
  if (!navigator.geolocation) {
    alert("Bu tarayıcı konum paylaşımını desteklemiyor.");
    return;
  }
  locationButton.textContent = "...";
  navigator.geolocation.getCurrentPosition(async (position) => {
    await fetch("/api/location", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy
      })
    });
    locationButton.textContent = "●";
  }, () => {
    locationButton.textContent = "◎";
    alert("Konum izni verilmedi veya konum alınamadı.");
  }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 60000});
});

loadMessages();
