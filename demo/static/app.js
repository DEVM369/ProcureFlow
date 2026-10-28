"use strict";

// No framework, tracking, cookies, external network requests, or HTML injection.
const byId = (id) => document.getElementById(id);
const state = { threadId: null, approvalId: null, interruptType: null, busy: false };

function busy(value) {
  state.busy = value;
  byId("prompt").disabled = value;
  document.querySelector(".send").disabled = value;
  byId("submit-supplement").disabled = value;
  byId("reject").disabled = value;
  byId("approve").disabled = value;
}

function clearEmpty() {
  const empty = byId("messages").querySelector(".empty");
  if (empty) empty.remove();
}

function addMessage(role, text) {
  clearEmpty();
  const wrapper = document.createElement("div");
  wrapper.className = "message " + (role === "user" ? "user" : "assistant");
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "YOU" : "PF";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = String(text);
  wrapper.append(avatar, bubble);
  byId("messages").append(wrapper);
  byId("messages").scrollTop = byId("messages").scrollHeight;
}

function addTrace(title, detail, alert = false) {
  const empty = byId("trace").querySelector(".trace-empty");
  if (empty) empty.remove();
  const item = document.createElement("div");
  item.className = alert ? "trace-item alert" : "trace-item";
  const heading = document.createElement("strong");
  heading.textContent = title;
  const body = document.createElement("p");
  body.textContent = detail;
  item.append(heading, body);
  byId("trace").append(item);
  byId("trace").scrollTop = byId("trace").scrollHeight;
}

function hideInterrupt() {
  byId("interrupt").classList.add("hidden");
  byId("supplement-controls").classList.add("hidden");
  byId("approval-controls").classList.add("hidden");
  state.interruptType = null;
  state.approvalId = null;
}

function receiveEvent(event) {
  if (event.type === "tool_start") {
    addTrace("TOOL · " + String(event.tool_name || "unknown"), "模拟任务委派开始");
  } else if (event.type === "tool_end") {
    addTrace("TASK COMPLETE", "任务工具完成（固定模拟流程）");
  } else if (event.type === "token") {
    addMessage("assistant", event.content || "");
  } else if (event.type === "interrupt") {
    // Save the server's ID before any resume, including the first interrupt.
    if (event.thread_id) state.threadId = event.thread_id;
    state.approvalId = event.approval_id || null;
    state.interruptType = event.interrupt_type;
    byId("interrupt").classList.remove("hidden");
    if (event.interrupt_type === "order_info_supplement") {
      byId("interrupt-title").textContent = "补齐采购信息";
      byId("interrupt-caption").textContent = "当前流程已暂停；需先补充虚构物料、数量和价格。";
      byId("supplement-controls").classList.remove("hidden");
      byId("approval-controls").classList.add("hidden");
      addTrace("INTERRUPT · FIELD COMPLETION", "审批票据已创建，保存会话 ID", true);
    } else if (event.interrupt_type === "hitl_approval") {
      byId("interrupt-title").textContent = "人工审批采购订单";
      byId("interrupt-caption").textContent = "虚构物料 101 · 数量 50 · 单价 42；默认建议拒绝。";
      byId("supplement-controls").classList.add("hidden");
      byId("approval-controls").classList.remove("hidden");
      addTrace("INTERRUPT · HUMAN APPROVAL", "需要一次性审批票据，拒绝不产生订单", true);
    }
  } else if (event.type === "done") {
    if (event.thread_id) state.threadId = event.thread_id;
    addTrace(event.interrupted ? "CHECKPOINT · PAUSED" : "WORKFLOW · DONE",
      event.interrupted ? "等待用户选择后继续" : "本轮模拟执行结束");
  }
}

async function stream(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "HTTP " + response.status);
  }
  if (!response.body) throw new Error("Browser streaming is unavailable");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop();
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((part) => part.startsWith("data: "));
      if (line) receiveEvent(JSON.parse(line.slice(6)));
    }
    if (done) break;
  }
}

async function refreshOrders() {
  try {
    const response = await fetch("/api/demo/orders");
    const data = await response.json();
    byId("order-count").textContent = String(data.orders.length);
  } catch (_) {
    addTrace("ORDER COUNT UNAVAILABLE", "本地服务不可用", true);
  }
}

async function sendMessage(message) {
  if (state.busy || state.interruptType) return;
  busy(true);
  try {
    addMessage("user", message);
    await stream("/api/chat/stream", { message, thread_id: state.threadId });
  } catch (error) {
    addMessage("assistant", "演示请求失败：" + error.message);
    addTrace("REQUEST FAILED", error.message, true);
  } finally {
    busy(false);
  }
}

async function resumeWith(payload) {
  if (state.busy || !state.threadId || !state.approvalId) return;
  busy(true);
  try {
    const path = "/api/chat/" + encodeURIComponent(state.threadId) + "/resume";
    const ticket = state.approvalId;
    // Hide controls only after the server accepts the decision. A 403 must retain
    // the ticket so the user can still reject the same proposed operation.
    const response = await fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: ticket, resume: payload }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "HTTP " + response.status);
    }
    hideInterrupt();
    if (!response.body) throw new Error("Browser streaming is unavailable");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (value) buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop();
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((part) => part.startsWith("data: "));
        if (line) receiveEvent(JSON.parse(line.slice(6)));
      }
      if (done) break;
    }
    await refreshOrders();
  } catch (error) {
    addTrace("RESUME DENIED", error.message, true);
    addMessage("assistant", "操作未执行：" + error.message + "（可继续选择拒绝）");
  } finally {
    busy(false);
  }
}

byId("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const prompt = byId("prompt");
  const message = prompt.value.trim();
  if (!message) return;
  prompt.value = "";
  sendMessage(message);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
});
byId("new-chat").addEventListener("click", () => {
  if (state.busy) return;
  state.threadId = null;
  hideInterrupt();
  byId("messages").replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = "新会话已创建。请选择演示场景，或输入采购问题。";
  byId("messages").append(empty);
  addTrace("NEW CONVERSATION", "新对话不会自动复用之前的审批票据");
});
byId("submit-supplement").addEventListener("click", () => {
  const supplement = byId("supplement").value.trim();
  if (!supplement) return;
  addMessage("user", supplement);
  resumeWith({ supplement });
});
byId("reject").addEventListener("click", () => resumeWith({ decisions: [{ type: "reject" }] }));
byId("approve").addEventListener("click", () => resumeWith({ decisions: [{ type: "approve" }] }));

async function initialize() {
  try {
    const response = await fetch("/health");
    if (!response.ok) throw new Error("health unavailable");
    const health = await response.json();
    byId("server-status").textContent = "Offline service ready";
    byId("writes-status").textContent = health.writes_enabled ? "Mock RAM only" : "Disabled";
    await refreshOrders();
  } catch (_) {
    byId("server-status").textContent = "Offline service unavailable";
  }
}
initialize();
