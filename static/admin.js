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
const workerResetBtn = document.getElementById("worker-reset-btn");
const queueClearBtn = document.getElementById("queue-clear-btn");

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
    agentRunsBox.textContent = "Запуски автономного цикла: пока нет записей.";
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
        "ВЫПОЛНЕНИЕ:",
        String(item.execution_text || "").trim(),
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
    queueBox.textContent = "Очередь воркера пуста.";
    return;
  }
  queueBox.textContent = "Очередь воркера:\n\n" + items
    .map(
      (q) =>
        `#${q.id} [${q.status}] prio=${q.priority} tries=${q.attempts}/${q.target_iterations}\n` +
        `goal: ${q.goal}\nprovider: ${q.provider}\nnext_retry_at: ${q.next_retry_at}\nerror: ${q.last_error || "-"}`
    )
    .join("\n\n");
}

async function refreshWorkerStatus() {
  const res = await fetch("/api/admin/agent/worker");
  const data = await res.json();
  workerStatusBox.textContent =
    `Состояние: ${data.state}\n` +
    `Включен: ${data.enabled}\n` +
    `Итерации: ${data.iterations}/${data.max_iterations}\n` +
    `Серия ошибок: ${data.fail_streak}/${data.fail_streak_limit}\n` +
    `Успешно/ошибки: ${data.success_count}/${data.failure_count}\n` +
    `Холостой режим: ${data.idle_cycles}/${data.idle_stop_limit}\n` +
    `Интервал: ${data.interval_sec} сек\n` +
    `Интервал сводки: ${data.summary_interval_sec} сек`;
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
  const iterations = Number(document.getElementById("queue-iterations").value || "1");
  if (!goal) return;
  const res = await fetch("/api/admin/agent/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, provider, priority, iterations }),
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
  const res = await fetch("/api/admin/agent/worker", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: true }),
  });
  if (!res.ok) alert("Не удалось запустить воркер");
  await refreshWorkerStatus();
  await refreshAudit();
  await refreshAgentQueue();
});

workerStopBtn.addEventListener("click", async () => {
  const res = await fetch("/api/admin/agent/worker", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: false }),
  });
  if (!res.ok) alert("Не удалось остановить воркер");
  await refreshWorkerStatus();
  await refreshAudit();
});

workerResetBtn.addEventListener("click", async () => {
  const res = await fetch("/api/admin/agent/worker/reset-metrics", { method: "POST" });
  if (!res.ok) {
    alert("Не удалось сбросить метрики");
    return;
  }
  await refreshWorkerStatus();
  await refreshAudit();
});

queueClearBtn.addEventListener("click", async () => {
  const res = await fetch("/api/admin/agent/queue/clear", { method: "POST" });
  if (!res.ok) {
    alert("Не удалось очистить очередь");
    return;
  }
  await refreshAgentQueue();
  await refreshAudit();
});

refreshUsers();
refreshAudit();
refreshAgentRuns();
refreshAgentQueue();
refreshWorkerStatus();

setInterval(() => {
  refreshAgentRuns();
  refreshAgentQueue();
  refreshWorkerStatus();
}, 5000);
