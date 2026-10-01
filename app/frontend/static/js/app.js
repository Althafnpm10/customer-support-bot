(function () {
  const chatToggle = document.getElementById("chat-toggle");
  const chatPanel = document.getElementById("chat-panel");
  const chatClose = document.getElementById("chat-close");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatMessages = document.getElementById("chat-messages");
  const chatReset = document.getElementById("chat-reset");
  const searchInput = document.getElementById("search-input");
  const searchButton = document.getElementById("search-btn");

  const plugin = new window.FrontendBackendChatPlugin({
    apiBase: "",
    storagePrefix: "cu_electronics_store",
  });
  const initialBotMessage =
    "Hello! Welcome to CU support main desk. Please tell me your problem, and I will direct you to the right support agent.";

  // Always start a fresh backend conversation on full page load/refresh.
  void plugin.resetConversation();

  function appendMessage(text, type) {
    const el = document.createElement("div");
    el.className = "msg " + type;
    el.textContent = text;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  async function sendToBackend(message) {
    appendMessage(message, "user");
    appendMessage("Typing...", "bot");
    const typingNode = chatMessages.lastElementChild;

    try {
      const data = await plugin.sendMessage(message);
      if (typingNode) {
        typingNode.remove();
      }
      appendMessage(data.response || "No response from support bot.", "bot");
    } catch (error) {
      if (typingNode) {
        typingNode.remove();
      }
      appendMessage("Support request failed: " + error.message, "bot");
    }
  }

  chatToggle.addEventListener("click", function () {
    chatPanel.classList.toggle("hidden");
    if (!chatPanel.classList.contains("hidden")) {
      chatInput.focus();
    }
  });

  chatClose.addEventListener("click", function () {
    chatPanel.classList.add("hidden");
  });

  chatForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    const message = chatInput.value.trim();
    if (!message) {
      return;
    }
    chatInput.value = "";
    await sendToBackend(message);
  });

  chatReset.addEventListener("click", async function () {
    await plugin.resetConversation();
    chatMessages.innerHTML = "";
    appendMessage(initialBotMessage, "bot");
    appendMessage("Session reset. Old conversation deleted.", "bot");
  });

  function filterCards() {
    const query = (searchInput.value || "").trim().toLowerCase();
    const cards = document.querySelectorAll(".card");
    cards.forEach(function (card) {
      const text = (card.textContent || "").toLowerCase();
      card.style.display = text.includes(query) ? "block" : "none";
    });
  }

  searchButton.addEventListener("click", filterCards);
  searchInput.addEventListener("input", filterCards);

})();
