(() => {
  const app = document.getElementById("chat-app");
  if (!app) return;

  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const messagesElement = document.getElementById("chat-messages");
  const welcome = document.getElementById("chat-welcome");
  const sendButton = document.getElementById("chat-send");
  const characterCount = document.getElementById("chat-character-count");
  const status = document.getElementById("chat-status");
  const storageKey = app.dataset.chatKey;
  const messages = [];

  function safeHelplines(items) {
    if (!Array.isArray(items)) return [];
    return items.filter((item) => (
      item
      && typeof item.name === "string"
      && typeof item.phone === "string"
      && /^[+\d\s()-]+$/.test(item.phone)
      && typeof item.description === "string"
    ));
  }

  function addMessage(message, persist = true) {
    const normalized = {
      role: message.role === "user" ? "user" : "assistant",
      content: String(message.content || ""),
      helplines: safeHelplines(message.helplines),
    };
    messages.push(normalized);

    const row = document.createElement("article");
    row.className = `chat-message chat-message-${normalized.role}`;
    const author = document.createElement("span");
    author.className = "chat-message-author";
    author.textContent = normalized.role === "user" ? "You" : "MindTrack";
    const bubble = document.createElement("p");
    bubble.className = "chat-message-bubble";
    bubble.textContent = normalized.content;
    row.append(author, bubble);

    if (normalized.helplines.length) {
      const helplineList = document.createElement("div");
      helplineList.className = "chat-helplines";
      for (const helpline of normalized.helplines) {
        const card = document.createElement("div");
        card.className = "chat-helpline";
        const details = document.createElement("span");
        const name = document.createElement("strong");
        name.textContent = helpline.name;
        const description = document.createElement("small");
        description.textContent = helpline.description;
        details.append(name, description);
        const phone = document.createElement("a");
        phone.href = `tel:${helpline.phone.replace(/[^\d+]/g, "")}`;
        phone.textContent = helpline.phone;
        card.append(details, phone);
        helplineList.append(card);
      }
      row.append(helplineList);
    }

    welcome.hidden = true;
    messagesElement.append(row);
    messagesElement.scrollTop = messagesElement.scrollHeight;

    if (persist) {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(messages.slice(-100)));
      } catch (_error) {
        // Keep the current conversation available in memory if browser storage is disabled.
      }
    }
  }

  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "[]");
    if (Array.isArray(saved)) {
      for (const item of saved.slice(-100)) {
        if (
          item
          && (item.role === "user" || item.role === "assistant")
          && typeof item.content === "string"
        ) {
          addMessage(item, false);
        }
      }
    }
  } catch (_error) {
    try {
      sessionStorage.removeItem(storageKey);
    } catch (_storageError) {
      // Storage may be unavailable; the chat can still run in memory.
    }
  }

  input.addEventListener("input", () => {
    characterCount.textContent = `${input.value.length} / 500`;
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || sendButton.disabled) return;

    const context = messages.slice(-5).map(({ role, content }) => ({
      role,
      content: content.slice(-512),
    }));
    addMessage({ role: "user", content: text });
    input.value = "";
    characterCount.textContent = "0 / 500";
    status.textContent = "Sending…";
    sendButton.disabled = true;
    input.disabled = true;

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": app.dataset.csrf,
        },
        body: JSON.stringify({ message: text, history: context }),
      });
      const result = await response.json();
      if (result.reply) {
        addMessage({
          role: "assistant",
          content: result.reply,
          helplines: result.helplines,
        });
        status.textContent = "";
      } else {
        status.textContent = result.error || "Please try sending your message again.";
      }
    } catch (_error) {
      addMessage({
        role: "assistant",
        content: "Chat is unavailable right now. Please try again later.",
      });
      status.textContent = "";
    } finally {
      sendButton.disabled = false;
      input.disabled = false;
      input.focus();
    }
  });
})();
