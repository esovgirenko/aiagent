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
const kpiBox = document.getElementById("kpi-box");
const approvalsBox = document.getElementById("approvals-box");
const kpiRefreshBtn = document.getElementById("kpi-refresh-btn");
const approvalsRefreshBtn = document.getElementById("approvals-refresh-btn");
const runsFilterBtn = document.getElementById("runs-filter-btn");
const runsVerifyFilter = document.getElementById("runs-verify-filter");
const runsProviderFilter = document.getElementById("runs-provider-filter");
const approvalDecisionForm = document.getElementById("approval-decision-form");
const selfEditPlanForm = document.getElementById("self-edit-plan-form");
const selfEditCheckBtn = document.getElementById("self-edit-check-btn");
const selfEditBox = document.getElementById("self-edit-box");

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
  const verify = encodeURIComponent(runsVerifyFilter.value || "");
  const provider = encodeURIComponent(runsProviderFilter.value || "");
  const res = await fetch(`/api/admin/agent/runs?verify=${verify}&provider=${provider}`);
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
        "REVIEW:",
        String(item.review_text || "").trim(),
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

async function refreshKpi() {
  const res = await fetch("/api/admin/agent/kpi");
  const data = await res.json();
  kpiBox.textContent =
    `PASS: ${data.passed}\n` +
    `FAIL: ${data.failed}\n` +
    `Success rate: ${data.success_rate}%`;
}

async function refreshApprovals() {
  const res = await fetch("/api/admin/approvals?status=pending");
  const data = await res.json();
  const items = data.items || [];
  if (!items.length) {
    approvalsBox.textContent = "Pending approvals: none";
    return;
  }
  approvalsBox.textContent = items
    .map((a) => `#${a.id} goal_id=${a.goal_id} risk=${a.risk_level}\nby=${a.requested_by}\naction=${a.action_text}`)
    .join("\n\n");
}

async function refreshSelfEditRuns() {
  const res = await fetch("/api/admin/agent/self-edit/runs");
  const data = await res.json();
  const items = data.items || [];
  if (!items.length) {
    selfEditBox.textContent = "Self-edit runs: none";
    return;
  }
  selfEditBox.textContent = items
    .map((r) => `#${r.id} [${r.status}] ${r.created_at}\ngoal: ${r.goal}\nplan: ${r.plan_text}\ncheck: ${r.check_output || "-"}`)
    .join("\n\n");
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

approvalDecisionForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const approvalId = Number(document.getElementById("approval-id-input").value || "0");
  const decision = document.getElementById("approval-decision").value;
  const note = document.getElementById("approval-note").value || "";
  const res = await fetch("/api/admin/approvals/decide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, approve: decision === "approve", note }),
  });
  if (!res.ok) {
    alert("Не удалось применить решение approval");
    return;
  }
  approvalDecisionForm.reset();
  await refreshApprovals();
  await refreshAudit();
});

selfEditPlanForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const goal = document.getElementById("self-edit-goal").value.trim();
  if (!goal) return;
  const res = await fetch("/api/admin/agent/self-edit/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal }),
  });
  if (!res.ok) {
    const data = await res.json();
    alert(data.detail || "Self-edit plan failed");
    return;
  }
  await refreshSelfEditRuns();
});

selfEditCheckBtn.addEventListener("click", async () => {
  const goal = document.getElementById("self-edit-goal").value.trim() || "self-edit check";
  const res = await fetch("/api/admin/agent/self-edit/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal }),
  });
  if (!res.ok) {
    const data = await res.json();
    alert(data.detail || "Self-edit check failed");
    return;
  }
  await refreshSelfEditRuns();
});

kpiRefreshBtn.addEventListener("click", refreshKpi);
approvalsRefreshBtn.addEventListener("click", refreshApprovals);
runsFilterBtn.addEventListener("click", refreshAgentRuns);

refreshUsers();
refreshAudit();
refreshAgentRuns();
refreshAgentQueue();
refreshWorkerStatus();
refreshKpi();
refreshApprovals();
refreshSelfEditRuns();

setInterval(() => {
  refreshAgentRuns();
  refreshAgentQueue();
  refreshWorkerStatus();
}, 5000);
