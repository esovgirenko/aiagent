const form = document.getElementById("chat-form");
const chat = document.getElementById("chat");
const provider = document.getElementById("provider");
const messageInput = document.getElementById("message");

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function addFeedbackControls(conversationId) {
  const wrapper = document.createElement("div");
  wrapper.className = "feedback";
  const up = document.createElement("button");
  up.type = "button";
  up.textContent = "👍";
  const down = document.createElement("button");
  down.type = "button";
  down.textContent = "👎";

  const send = async (score) => {
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        score,
        comment: "",
      }),
    });
    wrapper.remove();
  };

  up.onclick = () => send(1);
  down.onclick = () => send(-1);
  wrapper.appendChild(up);
  wrapper.appendChild(down);
  chat.appendChild(wrapper);
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;

  addMessage("user", message);
  messageInput.value = "";

  const thinking = addMessage("assistant", "Думаю...");
  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: provider.value,
        message,
      }),
    });
    if (!res.ok) {
      const data = await res.json();
      thinking.textContent = `Ошибка: ${data.detail || "Неизвестная ошибка"}`;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let rendered = "";
    let conversationId = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";

      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        const payload = JSON.parse(part.slice(6));
        if (payload.type === "chunk") {
          rendered += payload.text;
          thinking.textContent = rendered;
        } else if (payload.type === "done") {
          conversationId = payload.conversation_id;
        } else if (payload.type === "error") {
          thinking.textContent = `Ошибка: ${payload.detail || "Неизвестная ошибка"}`;
        }
      }
    }
    if (conversationId) addFeedbackControls(conversationId);
  } catch (err) {
    thinking.textContent = `Ошибка сети: ${String(err)}`;
  }
});
