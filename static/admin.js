const usersBox = document.getElementById("users-box");
const auditBox = document.getElementById("audit-box");
const createUserForm = document.getElementById("create-user-form");
const agentRunsBox = document.getElementById("agent-runs-box");
const agentRunForm = document.getElementById("agent-run-form");
const queueForm = document.getElementById("agent-queue-form");
const queueBox = document.getElementById("agent-queue-box");
const workerStatusBox = document.getElementById("worker-status-box");
const workerStartBtn = document.getElementById("worker-start-btn");
const workerStopBtn = document.getElementById("worker-stop-btn");

async function refreshUsers() {
  const res = await fetch("/api/admin/users");
  const data = await res.json();
  usersBox.textContent = JSON.stringify(data.items, null, 2);
}

async function refreshAudit() {
  const res = await fetch("/api/admin/audit");
  const data = await res.json();
  auditBox.textContent = JSON.stringify(data.items, null, 2);
}

async function refreshAgentRuns() {
  const res = await fetch("/api/admin/agent/runs");
  const data = await res.json();
  const items = data.items || [];
  if (!items.length) {
    agentRunsBox.textContent = "Пока нет запусков автономного цикла.";
    return;
  }
  agentRunsBox.textContent = items
    .map((item) => {
      return [
        `# Запуск ${item.id} | goal_id=${item.goal_id} | ${item.created_at}`,
        `Провайдер: ${item.provider}`,
        "",
        "РЕЗУЛЬТАТ:",
        String(item.result_text || "").trim(),
        "",
        "ПЛАН:",
        String(item.plan_text || "").trim(),
        "",
        "ДЕЙСТВИЕ:",
        String(item.action_text || "").trim(),
        "",
        `ПРОВЕРКА: ${item.verify_status}`,
        "",
        "РЕТРОСПЕКТИВА:",
        String(item.reflection_text || "").trim(),
        "",
        "------------------------------------------------------------",
      ].join("\n");
    })
    .join("\n");
}

async function refreshAgentQueue() {
  const res = await fetch("/api/admin/agent/queue");
  const data = await res.json();
  const items = data.items || [];
  if (!items.length) {
    queueBox.textContent = "Очередь пуста.";
    return;
  }
  queueBox.textContent = items
    .map(
      (q) =>
        `#${q.id} [${q.status}] prio=${q.priority} tries=${q.attempts}\n` +
        `goal: ${q.goal}\nprovider: ${q.provider}\nerror: ${q.last_error || "-"}`
    )
    .join("\n\n");
}

async function refreshWorkerStatus() {
  const res = await fetch("/api/admin/agent/worker");
  const data = await res.json();
  workerStatusBox.textContent =
    `Состояние: ${data.running ? "RUNNING" : "STOPPED"}\n` +
    `Включен: ${data.enabled}\n` +
    `Итерации: ${data.iterations}/${data.max_iterations}\n` +
    `Серия ошибок: ${data.fail_streak}/${data.fail_streak_limit}\n` +
    `Интервал: ${data.interval_sec} сек`;
}

createUserForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("new-username").value.trim();
  const password = document.getElementById("new-password").value;
  const role = document.getElementById("new-role").value;
  const res = await fetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role }),
  });
  if (!res.ok) {
    const data = await res.json();
    alert(data.detail || "Ошибка создания пользователя");
    return;
  }
  createUserForm.reset();
  await refreshUsers();
  await refreshAudit();
});

agentRunForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const goal = document.getElementById("goal-input").value.trim();
  const provider = document.getElementById("agent-provider").value;
  if (!goal) return;
  const res = await fetch("/api/admin/agent/run-cycle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, provider }),
  });
  if (!res.ok) {
    const data = await res.json();
    alert(data.detail || "Ошибка запуска автономного цикла");
    return;
  }
  agentRunForm.reset();
  await refreshAgentRuns();
  await refreshAgentQueue();
  await refreshAudit();
});

queueForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const goal = document.getElementById("queue-goal-input").value.trim();
  const provider = document.getElementById("queue-provider").value;
  const priority = Number(document.getElementById("queue-priority").value || "3");
  if (!goal) return;
  const res = await fetch("/api/admin/agent/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, provider, priority }),
  });
  if (!res.ok) {
    const data = await res.json();
    alert(data.detail || "Ошибка добавления в очередь");
    return;
  }
  queueForm.reset();
  await refreshAgentQueue();
  await refreshAudit();
});

workerStartBtn.addEventListener("click", async () => {
  await fetch("/api/admin/agent/worker", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: true }),
  });
  await refreshWorkerStatus();
  await refreshAudit();
});

workerStopBtn.addEventListener("click", async () => {
  await fetch("/api/admin/agent/worker", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: false }),
  });
  await refreshWorkerStatus();
  await refreshAudit();
});

refreshUsers();
refreshAudit();
refreshAgentRuns();
refreshAgentQueue();
refreshWorkerStatus();
