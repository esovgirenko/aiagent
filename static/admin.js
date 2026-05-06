const usersBox = document.getElementById("users-box");
const auditBox = document.getElementById("audit-box");
const createUserForm = document.getElementById("create-user-form");
const approvalsBox = document.getElementById("approvals-box");
const approvalsRefreshBtn = document.getElementById("approvals-refresh-btn");
const memoryRefreshBtn = document.getElementById("memory-refresh-btn");
const memoryBox = document.getElementById("memory-box");
const reasoningRefreshBtn = document.getElementById("reasoning-refresh-btn");
const reasoningBox = document.getElementById("reasoning-box");
const approvalDecisionForm = document.getElementById("approval-decision-form");

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

async function refreshMemory() {
  const res = await fetch("/api/admin/memory");
  const data = await res.json();
  const items = data.items || [];
  const feedback = data.feedback_summary || "-";
  if (!items.length) {
    memoryBox.textContent = `Feedback: ${feedback}\n\nRecent memory: none`;
    return;
  }
  memoryBox.textContent = [
    `Feedback: ${feedback}`,
    "",
    "Recent memory:",
    ...items.map((m, i) => `#${i + 1} [${m.provider}]\nU: ${m.user_message}\nA: ${m.assistant_message}`),
  ].join("\n\n");
}

async function refreshReasoning() {
  const res = await fetch("/api/admin/agent/runs");
  const data = await res.json();
  const items = data.items || [];
  if (!items.length) {
    reasoningBox.textContent = "Рассуждения: пока нет запусков.";
    return;
  }
  reasoningBox.textContent = items
    .slice(0, 10)
    .map(
      (r) =>
        `#${r.id} | ${r.created_at} | provider=${r.provider}\n` +
        `План: ${r.plan_text || "-"}\n` +
        `Действие: ${r.action_text || "-"}\n` +
        `Выполнение: ${r.execution_text || "-"}\n` +
        `Проверка: ${r.verify_status}\n` +
        `Ревью: ${r.review_text || "-"}\n` +
        `Ретроспектива: ${r.reflection_text || "-"}`
    )
    .join("\n\n");
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

approvalsRefreshBtn.addEventListener("click", refreshApprovals);
memoryRefreshBtn.addEventListener("click", refreshMemory);
reasoningRefreshBtn.addEventListener("click", refreshReasoning);

refreshUsers();
refreshAudit();
refreshApprovals();
refreshMemory();
refreshReasoning();
