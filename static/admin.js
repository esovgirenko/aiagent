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
  agentRunsBox.textContent = JSON.stringify(data.items, null, 2);
}

async function refreshAgentQueue() {
  const res = await fetch("/api/admin/agent/queue");
  const data = await res.json();
  queueBox.textContent = JSON.stringify(data.items, null, 2);
}

async function refreshWorkerStatus() {
  const res = await fetch("/api/admin/agent/worker");
  const data = await res.json();
  workerStatusBox.textContent = JSON.stringify(data, null, 2);
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
  if (!goal) return;
  const res = await fetch("/api/admin/agent/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, provider }),
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
