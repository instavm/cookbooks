import * as store from "./history.js?v=20260722p";

const state = {
  config: null,
  guestId: localStorage.getItem("ivm_preview_guest") || "",
  sessionId: null,
  previewUrl: null,
  expiresAt: null,
  ttlTimer: null,
  building: false,
  planning: false,
  plan: null,
  buildAttachments: [],
  iterateAttachments: [],
  conversationId: store.getActiveId() || null,
  mode: null,
  opsVmId: null,
  opsPtyId: null,
  ptyTerm: null,
  ptySocket: null,
  ptyHeartbeat: null,
  opsExamples: [],
  opsTickerIndex: 0,
  opsTickerTimer: null,
};

const els = {
  form: document.getElementById("build-form"),
  prompt: document.getElementById("prompt"),
  buildBtn: document.getElementById("build-btn"),
  templates: document.getElementById("templates"),
  workspace: document.getElementById("workspace"),
  phases: document.getElementById("phases"),
  timeline: document.getElementById("timeline"),
  frame: document.getElementById("frame"),
  openPreview: document.getElementById("open-preview"),
  copyUrl: document.getElementById("copy-url"),
  ttl: document.getElementById("ttl"),
  usage: document.getElementById("usage"),
  iterateForm: document.getElementById("iterate-form"),
  iterate: document.getElementById("iterate"),
  iterateBtn: document.getElementById("iterate-btn"),
  error: document.getElementById("error"),
  quota: document.getElementById("quota"),
  claimLink: document.getElementById("claim-link"),
  billingLink: document.getElementById("billing-link"),
  hint: document.getElementById("hint"),
  attachInput: document.getElementById("attach-input"),
  attachThumbs: document.getElementById("attach-thumbs"),
  attachHint: document.getElementById("attach-hint"),
  iterateAttachInput: document.getElementById("iterate-attach-input"),
  iterateThumbs: document.getElementById("iterate-thumbs"),
  historyList: document.getElementById("history-list"),
  historyEmpty: document.getElementById("history-empty"),
  history: document.getElementById("history"),
  toggleHistory: document.getElementById("toggle-history"),
  openHistory: document.getElementById("open-history"),
  historyScrim: document.getElementById("history-scrim"),
  newChat: document.getElementById("new-chat"),
  convoMeta: document.getElementById("convo-meta"),
  buildStream: document.getElementById("build-stream"),
  buildStreamHead: document.getElementById("build-stream-head"),
  stageLabel: document.getElementById("stage-label"),
  planPanel: document.getElementById("plan-panel"),
  planLabel: document.getElementById("plan-label"),
  planSummary: document.getElementById("plan-summary"),
  planTodos: document.getElementById("plan-todos"),
  planDiscard: document.getElementById("plan-discard"),
  planApprove: document.getElementById("plan-approve"),
  planReviseBtn: document.getElementById("plan-revise-btn"),
  planUpdateBtn: document.getElementById("plan-update-btn"),
  planReviseBox: document.getElementById("plan-revise-box"),
  planFeedback: document.getElementById("plan-feedback"),
  ptyWrap: document.getElementById("pty-wrap"),
  ptyTerm: document.getElementById("pty-term"),
  opsResult: document.getElementById("ops-result"),
  iterateLabel: document.getElementById("iterate-label"),
  opsTicker: document.getElementById("ops-ticker"),
  opsTickerBtn: document.getElementById("ops-ticker-btn"),
  opsTickerText: document.getElementById("ops-ticker-text"),
};

function hasOpsContext() {
  return Boolean(state.sessionId && state.mode === "ops") || Boolean(state.opsVmId);
}

function setOpsChrome(active) {
  document.body.classList.toggle("is-ops", Boolean(active));
  if (els.iterateLabel) {
    els.iterateLabel.textContent = active ? "Next" : "Revise";
  }
  if (els.iterate) {
    els.iterate.placeholder = active
      ? "suspend this vm · resume · list my vms · kill this sandbox"
      : "Make the title larger — or attach a shot and say match this";
  }
  if (els.iterateBtn) {
    els.iterateBtn.textContent = active ? "Run" : "Apply";
  }
}

function disposePty() {
  if (state.ptyHeartbeat) {
    clearInterval(state.ptyHeartbeat);
    state.ptyHeartbeat = null;
  }
  if (state.ptySocket) {
    try {
      state.ptySocket.close();
    } catch {
      /* ignore */
    }
    state.ptySocket = null;
  }
  if (state.ptyTerm) {
    try {
      state.ptyTerm.dispose();
    } catch {
      /* ignore */
    }
    state.ptyTerm = null;
  }
  if (els.ptyTerm) els.ptyTerm.innerHTML = "";
  if (els.ptyWrap) els.ptyWrap.hidden = true;
}

async function connectPty(ptyPath) {
  if (!ptyPath || !els.ptyWrap || !els.ptyTerm) return;
  disposePty();
  showWorkspace();
  els.ptyWrap.hidden = false;
  els.frame.hidden = true;
  hideBuildStream();
  document.body.classList.add("is-ops", "has-workspace");
  if (els.stageLabel) els.stageLabel.textContent = "Terminal";

  let Terminal;
  try {
    ({ Terminal } = await import(
      "https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/+esm"
    ));
  } catch (err) {
    els.ptyTerm.textContent =
      "Terminal UI failed to load (CDN blocked). Retry or check network.";
    showError("Could not load terminal UI.");
    return;
  }

  const term = new Terminal({
    cursorBlink: true,
    fontFamily:
      '"JetBrains Mono", "IBM Plex Mono", "SF Mono", ui-monospace, monospace',
    fontSize: 14,
    fontWeight: "450",
    lineHeight: 1.35,
    letterSpacing: 0.3,
    theme: {
      background: "#0d0d0c",
      foreground: "#e8e8e3",
      cursor: "#e8e8e3",
      selectionBackground: "#3a3a36",
    },
    convertEol: true,
    scrollback: 1000,
  });
  term.open(els.ptyTerm);
  term.focus();
  state.ptyTerm = term;

  // Match dash PtyTerminal: BINARY = stdin/stdout, TEXT = JSON control.
  const decoder = new TextDecoder("utf-8", { fatal: false });
  const encoder = new TextEncoder();
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}${ptyPath}`);
  ws.binaryType = "arraybuffer";
  state.ptySocket = ws;

  ws.addEventListener("message", (ev) => {
    if (typeof ev.data === "string") return; // control / ping-pong
    if (ev.data instanceof ArrayBuffer) {
      term.write(decoder.decode(new Uint8Array(ev.data), { stream: true }));
    }
  });
  ws.addEventListener("open", () => {
    term.writeln("\x1b[2mconnected\x1b[0m");
    state.ptyHeartbeat = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 60000);
  });
  ws.addEventListener("close", () => {
    if (state.ptyHeartbeat) {
      clearInterval(state.ptyHeartbeat);
      state.ptyHeartbeat = null;
    }
    term.writeln("\r\n\x1b[2m[connection closed]\x1b[0m");
  });
  ws.addEventListener("error", () => {
    term.writeln("\r\n\x1b[31m[connection error]\x1b[0m");
    showError("Terminal connection failed.");
  });
  term.onData((data) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(encoder.encode(data));
    }
  });
}

function track(event, props = {}) {
  try {
    if (window.posthog && typeof window.posthog.capture === "function") {
      window.posthog.capture(event, props);
    }
  } catch {
    /* ignore */
  }
}

async function loadPostHog(key, host) {
  if (!key) return;
  const s = document.createElement("script");
  s.async = true;
  s.src = `${host.replace(/\/$/, "")}/static/array.js`;
  document.head.appendChild(s);
  window.posthog = window.posthog || [];
  window.posthog.init = window.posthog.init || function initStub() {};
  await new Promise((resolve) => {
    s.onload = resolve;
    s.onerror = resolve;
  });
  if (window.posthog && typeof window.posthog.init === "function") {
    window.posthog.init(key, {
      api_host: host,
      person_profiles: "identified_only",
      capture_pageview: true,
    });
  }
}

function showError(msg) {
  els.error.hidden = false;
  els.error.textContent = msg;
}

function clearError() {
  els.error.hidden = true;
  els.error.textContent = "";
}

function setQuota(status) {
  if (!status) return;
  els.quota.hidden = false;
  els.quota.textContent = `${status.builds_remaining}/${status.builds_limit} left`;
  if (status.guest_id) {
    state.guestId = status.guest_id;
    localStorage.setItem("ivm_preview_guest", status.guest_id);
  }
}

function maxAttachments() {
  return state.config?.max_attachments || 3;
}

function maxAttachmentBytes() {
  return state.config?.max_attachment_bytes || 4 * 1024 * 1024;
}

function allowedMimes() {
  return new Set(
    state.config?.allowed_attachment_mimes || [
      "image/png",
      "image/jpeg",
      "image/webp",
      "image/gif",
    ]
  );
}

function fileToAttachment(file) {
  return new Promise((resolve, reject) => {
    const mime = file.type === "image/jpg" ? "image/jpeg" : file.type;
    if (!allowedMimes().has(mime)) {
      reject(new Error(`Unsupported type: ${mime || file.name}`));
      return;
    }
    if (file.size > maxAttachmentBytes()) {
      reject(
        new Error(
          `Image too large (max ${Math.round(maxAttachmentBytes() / 1024 / 1024)}MB).`
        )
      );
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const comma = dataUrl.indexOf(",");
      const dataBase64 = comma >= 0 ? dataUrl.slice(comma + 1) : "";
      resolve({
        name: file.name || "screenshot.png",
        mime_type: mime,
        data_base64: dataBase64,
        preview_url: dataUrl,
      });
    };
    reader.onerror = () => reject(new Error("Could not read image."));
    reader.readAsDataURL(file);
  });
}

function renderAttachments(list, thumbsEl, key) {
  thumbsEl.innerHTML = "";
  if (!list.length) {
    thumbsEl.hidden = true;
    return;
  }
  thumbsEl.hidden = false;
  list.forEach((att, i) => {
    const wrap = document.createElement("div");
    wrap.className = "attach-thumb";
    const img = document.createElement("img");
    img.src = att.preview_url;
    img.alt = att.name;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("aria-label", "Remove");
    btn.textContent = "×";
    btn.addEventListener("click", () => {
      state[key] = state[key].filter((_, j) => j !== i);
      renderAttachments(state[key], thumbsEl, key);
    });
    wrap.appendChild(img);
    wrap.appendChild(btn);
    thumbsEl.appendChild(wrap);
  });
}

async function addFiles(files, key, thumbsEl) {
  const incoming = Array.from(files || []).filter((f) => f.type.startsWith("image/"));
  if (!incoming.length) return;
  clearError();
  const room = maxAttachments() - state[key].length;
  if (room <= 0) {
    showError(`At most ${maxAttachments()} screenshots.`);
    return;
  }
  try {
    const added = [];
    for (const file of incoming.slice(0, room)) {
      added.push(await fileToAttachment(file));
    }
    state[key] = [...state[key], ...added];
    renderAttachments(state[key], thumbsEl, key);
    track("preview_attachment_added", { count: added.length, target: key });
  } catch (err) {
    showError(err?.message || "Could not attach image.");
  }
}

function payloadAttachments(list) {
  return list.map(({ name, mime_type, data_base64 }) => ({
    name,
    mime_type,
    data_base64,
  }));
}

function renderTemplates(templates) {
  els.templates.innerHTML = "";
  templates.forEach((t, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "template";
    btn.textContent = `/${String(i + 1).padStart(2, "0")} ${t.title.toLowerCase()}`;
    btn.title = t.blurb;
    btn.addEventListener("click", () => {
      els.prompt.value = t.prompt;
      els.prompt.focus();
      track("preview_template_selected", { template_id: t.id });
      requestPlan({ templateId: t.id, prompt: t.prompt });
    });
    els.templates.appendChild(btn);
  });
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function showOpsTickerPrompt(index, { animate = true } = {}) {
  const items = state.opsExamples;
  if (!items.length || !els.opsTickerText) return;
  const item = items[((index % items.length) + items.length) % items.length];
  state.opsTickerIndex = ((index % items.length) + items.length) % items.length;
  const apply = () => {
    els.opsTickerText.textContent = item.prompt;
    els.opsTickerText.classList.remove("is-leave");
    if (animate && !prefersReducedMotion()) {
      els.opsTickerText.classList.remove("is-enter");
      void els.opsTickerText.offsetWidth;
      els.opsTickerText.classList.add("is-enter");
    }
  };
  if (animate && !prefersReducedMotion() && els.opsTickerText.textContent) {
    els.opsTickerText.classList.remove("is-enter");
    els.opsTickerText.classList.add("is-leave");
    window.setTimeout(apply, 320);
  } else {
    apply();
  }
}

function startOpsTicker(examples) {
  state.opsExamples = Array.isArray(examples)
    ? examples.filter((e) => e?.prompt)
    : [];
  if (state.opsTickerTimer) {
    clearInterval(state.opsTickerTimer);
    state.opsTickerTimer = null;
  }
  if (!els.opsTicker || !els.opsTickerBtn || !els.opsTickerText) return;
  if (!state.opsExamples.length) {
    els.opsTicker.hidden = true;
    return;
  }
  els.opsTicker.hidden = false;
  showOpsTickerPrompt(0, { animate: false });

  els.opsTickerBtn.onclick = () => {
    const item = state.opsExamples[state.opsTickerIndex];
    if (!item) return;
    els.prompt.value = item.prompt;
    els.prompt.focus();
    track("preview_ops_example_selected", { example_id: item.id || null });
    requestPlan({ prompt: item.prompt });
  };

  if (prefersReducedMotion() || state.opsExamples.length < 2) return;
  state.opsTickerTimer = setInterval(() => {
    if (document.body.classList.contains("has-workspace")) return;
    if (document.hidden) return;
    showOpsTickerPrompt(state.opsTickerIndex + 1, { animate: true });
  }, 4200);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function relativeTime(ts) {
  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

function isNarrowViewport() {
  return window.matchMedia("(max-width: 820px)").matches;
}

function applySidebarCollapsed(collapsed) {
  document.body.classList.toggle("history-collapsed", collapsed);
  els.openHistory.hidden = !collapsed;
  if (els.historyScrim) {
    els.historyScrim.hidden = collapsed || !isNarrowViewport();
  }
  // Persist desktop preference only; mobile always starts collapsed.
  if (!isNarrowViewport()) store.setSidebarCollapsed(collapsed);
}

function syncUrlConversation(id) {
  const url = new URL(location.href);
  if (id) url.searchParams.set("c", id);
  else url.searchParams.delete("c");
  window.history.replaceState({}, "", url);
}

function activePhaseLabel(convo) {
  const phases = convo?.phases || [];
  const active = phases.find((p) => p.status === "active");
  if (active) return (active.label || active.id || "building").toLowerCase();
  const lastDone = [...phases].reverse().find((p) => p.status === "done");
  if (convo?.status === "building" && lastDone) {
    return `${(lastDone.label || lastDone.id).toLowerCase()}…`;
  }
  return null;
}

function renderHistoryList() {
  const items = store.listConversations();
  els.historyList.innerHTML = "";
  els.historyEmpty.hidden = items.length > 0;
  items.forEach((c) => {
    const row = document.createElement("div");
    row.className = "history-item-row";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-item" + (c.id === state.conversationId ? " is-active" : "");
    let status =
      c.expiresAt && c.expiresAt < Date.now() && c.status === "ready"
        ? "expired"
        : c.status || "ready";
    const phase = activePhaseLabel(c);
    const statusText =
      status === "building" && phase ? phase : status;
    const idBits = [];
    if (c.vmId) idBits.push(c.vmId);
    else if (c.sessionId) idBits.push(`sess ${String(c.sessionId).slice(0, 8)}…`);
    btn.innerHTML = `
      <span class="h-title">${escapeHtml(c.title || "Untitled")}</span>
      ${
        idBits.length
          ? `<span class="h-ids mono">${escapeHtml(idBits.join(" · "))}</span>`
          : ""
      }
      <span class="h-meta">
        <span class="h-status" data-status="${escapeHtml(status)}">${escapeHtml(statusText)}</span>
        <span>${escapeHtml(relativeTime(c.updatedAt || c.createdAt))}</span>
      </span>`;
    btn.addEventListener("click", () => {
      openConversation(c.id);
      if (isNarrowViewport()) applySidebarCollapsed(true);
    });
    const del = document.createElement("button");
    del.type = "button";
    del.className = "history-delete";
    del.setAttribute("aria-label", "Delete conversation");
    del.textContent = "×";
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      store.deleteConversation(c.id);
      if (state.conversationId === c.id) startNewChat({ silent: true });
      renderHistoryList();
      track("preview_conversation_deleted");
    });
    row.appendChild(btn);
    row.appendChild(del);
    els.historyList.appendChild(row);
  });
}

function setBuildBusy(busy, label = "Building…") {
  state.building = busy;
  document.body.classList.toggle("is-building", busy);
  els.buildBtn.disabled = busy || state.planning;
  els.buildBtn.classList.toggle("is-busy", busy || state.planning);
  if (busy) els.buildBtn.textContent = label;
  else if (state.planning) els.buildBtn.textContent = "Planning…";
  else els.buildBtn.textContent = "Build";
  if (els.planApprove) els.planApprove.disabled = busy || state.planning;
  if (els.planUpdateBtn) els.planUpdateBtn.disabled = busy || state.planning;
  if (els.planReviseBtn) els.planReviseBtn.disabled = busy || state.planning;
}

function setPlanningBusy(busy) {
  state.planning = busy;
  document.body.classList.toggle("is-planning", busy);
  els.buildBtn.disabled = busy || state.building;
  els.buildBtn.classList.toggle("is-busy", busy || state.building);
  els.buildBtn.textContent = busy ? "Planning…" : state.building ? "Building…" : "Build";
  if (els.planApprove) els.planApprove.disabled = busy || state.building;
  if (els.planUpdateBtn) els.planUpdateBtn.disabled = busy || state.building;
  if (els.planReviseBtn) els.planReviseBtn.disabled = busy || state.building;
}

function hidePlanPanel() {
  if (!els.planPanel) return;
  els.planPanel.hidden = true;
  if (els.planReviseBox) els.planReviseBox.hidden = true;
  if (els.planUpdateBtn) els.planUpdateBtn.hidden = true;
  if (els.planReviseBtn) els.planReviseBtn.hidden = false;
  if (els.planFeedback) els.planFeedback.value = "";
  if (els.planLabel) els.planLabel.textContent = "Plan";
}

function renderPlanTodos(todos) {
  if (!els.planTodos) return;
  els.planTodos.innerHTML = "";
  (todos || []).forEach((t) => {
    const li = document.createElement("li");
    li.dataset.id = t.id;
    li.dataset.status = t.status || "pending";
    li.innerHTML = `<span class="plan-check" aria-hidden="true"></span><span>${escapeHtml(
      t.title || t.id
    )}</span>`;
    els.planTodos.appendChild(li);
  });
}

function showPlanPanel(plan) {
  if (!els.planPanel || !plan) return;
  state.plan = {
    summary: plan.summary,
    todos: (plan.todos || []).map((t) => ({
      id: t.id,
      title: t.title,
      status: t.status || "pending",
    })),
  };
  els.planSummary.textContent = state.plan.summary;
  renderPlanTodos(state.plan.todos);
  els.planPanel.hidden = false;
  if (els.planReviseBox) els.planReviseBox.hidden = true;
  if (els.planUpdateBtn) els.planUpdateBtn.hidden = true;
  if (els.planReviseBtn) els.planReviseBtn.hidden = false;
  if (els.planLabel) els.planLabel.textContent = "Plan";
  if (els.planApprove) els.planApprove.hidden = false;
}

function patchTodoStatus(id, status) {
  if (!state.plan?.todos) return;
  let found = false;
  state.plan.todos = state.plan.todos.map((t) => {
    if (t.id !== id) {
      if (status === "active" && t.status === "active") {
        return { ...t, status: "pending" };
      }
      return t;
    }
    found = true;
    return { ...t, status };
  });
  if (!found) return;
  renderPlanTodos(state.plan.todos);
  if (state.conversationId) {
    store.updateConversation(state.conversationId, { plan: state.plan });
  }
  const active = state.plan.todos.find((t) => t.status === "active");
  if (active && els.buildStreamHead && state.building) {
    els.buildStreamHead.textContent = active.title;
  }
}

function setPreviewLinks(visible, url = "") {
  if (els.copyUrl) els.copyUrl.hidden = !visible;
  if (els.openPreview) {
    els.openPreview.hidden = !visible;
    if (url) els.openPreview.href = url;
  }
}

function showWorkspace() {
  els.workspace.hidden = false;
  els.workspace.classList.add("is-open");
  document.body.classList.add("has-workspace");
}

function hideWorkspace() {
  els.workspace.hidden = true;
  els.workspace.classList.remove("is-open");
  document.body.classList.remove("has-workspace", "is-streaming", "is-ops");
  hideBuildStream();
  disposePty();
  if (els.opsResult) {
    els.opsResult.hidden = true;
    els.opsResult.textContent = "";
  }
  els.frame.hidden = true;
  els.frame.removeAttribute("src");
  els.frame.src = "about:blank";
  els.iterateForm.hidden = true;
  els.phases.hidden = true;
  els.phases.innerHTML = "";
  clearTimeline();
  setPreviewLinks(false);
  setOpsChrome(false);
  if (els.stageLabel) els.stageLabel.textContent = "Building";
  if (els.buildStreamHead) els.buildStreamHead.textContent = "Starting…";
}

function showBuildStream(head = "Starting…") {
  showWorkspace();
  document.body.classList.add("is-streaming");
  if (els.buildStream) {
    els.buildStream.hidden = false;
    els.buildStream.classList.add("is-visible");
  }
  if (els.buildStreamHead) els.buildStreamHead.textContent = head;
  if (els.stageLabel) els.stageLabel.textContent = "Building";
  els.frame.hidden = true;
  els.iterateForm.hidden = true;
  setPreviewLinks(false);
}

function hideBuildStream() {
  document.body.classList.remove("is-streaming");
  if (els.buildStream) {
    els.buildStream.hidden = true;
    els.buildStream.classList.remove("is-visible");
  }
  if (els.stageLabel) els.stageLabel.textContent = "Live";
}

function setPhases(list) {
  els.phases.hidden = false;
  els.phases.innerHTML = "";
  list.forEach((p, i) => {
    const row = document.createElement("div");
    row.className = "phase";
    row.dataset.id = p.id;
    row.dataset.status = p.status || "pending";
    const n = String(i + 1).padStart(2, "0");
    row.innerHTML = `<span class="dot"></span><span class="lbl">${n} ${escapeHtml(
      (p.label || "").toLowerCase()
    )}</span>`;
    els.phases.appendChild(row);
  });
  const active = list.find((p) => p.status === "active");
  if (active && els.buildStreamHead) {
    els.buildStreamHead.textContent = active.label || "Building";
  }
  if (active && state.building) {
    els.buildBtn.textContent = `${(active.label || "Building").split(" ")[0]}…`;
  }
}

function updatePhase(id, label, status) {
  const row = els.phases.querySelector(`[data-id="${id}"]`);
  if (!row) return;
  row.dataset.status = status;
  if (label) {
    const idx = [...els.phases.children].indexOf(row);
    const n = String(idx + 1).padStart(2, "0");
    row.querySelector(".lbl").textContent = `${n} ${label.toLowerCase()}`;
  }
  if (status === "active" && label) {
    if (els.buildStreamHead) els.buildStreamHead.textContent = label;
    if (state.building) {
      els.buildBtn.textContent = `${label.split(" ")[0]}…`;
    }
  }
  renderHistoryList();
}

function addStep(tag, body, { persist = true } = {}) {
  const div = document.createElement("div");
  div.className = "step";
  div.innerHTML = `<span class="tag">${escapeHtml(tag)}</span><div class="body"></div>`;
  div.querySelector(".body").textContent = body || "";
  div.addEventListener("click", () => {
    div.querySelector(".body").classList.toggle("open");
  });
  els.timeline.appendChild(div);
  els.timeline.scrollTop = els.timeline.scrollHeight;
  if (persist && state.conversationId) {
    store.appendStep(state.conversationId, tag, body);
    renderHistoryList();
  }
}

function clearTimeline() {
  els.timeline.innerHTML = "";
}

function formatTokens(n) {
  const v = Number(n) || 0;
  if (v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k`;
  return String(v);
}

function showUsage(usage) {
  if (!usage || !els.usage) return;
  const total = usage.total_tokens ?? 0;
  const inp = usage.input_tokens ?? 0;
  const out = usage.output_tokens ?? 0;
  els.usage.hidden = false;
  els.usage.textContent = `${formatTokens(total)} tok · ${formatTokens(inp)}↑ ${formatTokens(out)}↓`;
  els.usage.title = [
    `model: ${usage.model || state.config?.model || "gpt-5.4-nano"}`,
    `requests: ${usage.requests ?? "—"}`,
    `input: ${inp}`,
    `output: ${out}`,
    `total: ${total}`,
  ].join("\n");
}

function showConvoMeta(convo) {
  if (!convo || !els.convoMeta) return;
  const parts = [];
  if (convo.vmId) parts.push(`vm ${convo.vmId}`);
  if (convo.sessionId) parts.push(`session ${convo.sessionId}`);
  if (convo.ptyId) parts.push(`pty ${convo.ptyId}`);
  if (convo.previewUrl) parts.push(convo.previewUrl);
  if (convo.usage?.total_tokens) {
    parts.push(`${formatTokens(convo.usage.total_tokens)} tok`);
  }
  if (!parts.length) {
    els.convoMeta.hidden = true;
    return;
  }
  els.convoMeta.hidden = false;
  els.convoMeta.textContent = parts.join(" · ");
}

function showOpsResourceBar({ vmId, sessionId, ptyId } = {}) {
  const vid = vmId || state.opsVmId;
  const sid = sessionId || state.sessionId;
  const pid = ptyId || state.opsPtyId;
  if (!els.convoMeta) return;
  const parts = [];
  if (vid) parts.push(`vm ${vid}`);
  if (sid) parts.push(`session ${sid}`);
  if (pid) parts.push(`pty ${pid}`);
  if (!parts.length) return;
  els.convoMeta.hidden = false;
  els.convoMeta.textContent = parts.join(" · ");
}

function showPreview(url, ttlSeconds) {
  if (!/^https?:\/\//i.test(url)) {
    showError("Preview URL rejected.");
    return;
  }
  state.previewUrl = url;
  state.expiresAt =
    ttlSeconds != null
      ? Date.now() + Number(ttlSeconds) * 1000
      : state.expiresAt;
  showWorkspace();
  hideBuildStream();
  els.frame.hidden = false;
  els.frame.src = url;
  setPreviewLinks(true, url);
  els.iterateForm.hidden = false;
  tickTtl();
}

function tickTtl() {
  if (state.ttlTimer) clearTimeout(state.ttlTimer);
  if (!state.expiresAt) {
    els.ttl.textContent = "";
    return;
  }
  const remaining = Math.max(0, Math.floor((state.expiresAt - Date.now()) / 1000));
  const m = Math.floor(remaining / 60);
  const s = String(remaining % 60).padStart(2, "0");
  els.ttl.textContent = remaining ? `${m}:${s} left` : "expired";
  if (remaining <= 0 && state.conversationId) {
    store.updateConversation(state.conversationId, { status: "expired" });
    renderHistoryList();
  }
  if (remaining > 0) {
    state.ttlTimer = setTimeout(tickTtl, 1000);
  }
}

async function readSSE(response, onEvent) {
  const reader = response.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = frame.split("\n");
      let event = "message";
      const data = [];
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (event === "message" && !data.length) continue;
      let parsed;
      try {
        parsed = JSON.parse(data.join("\n") || "{}");
      } catch {
        parsed = { text: data.join("\n") };
      }
      onEvent(event, parsed);
    }
  }
}

function handleStreamEvent(event, data) {
  if (event === "phases") {
    setPhases(data.phases || []);
    if (state.conversationId) {
      store.setPhases(state.conversationId, data.phases || []);
      renderHistoryList();
    }
  } else if (event === "phase") {
    updatePhase(data.id, data.label, data.status);
    if (state.conversationId) {
      store.patchPhase(state.conversationId, data.id, data.label, data.status);
      renderHistoryList();
    }
  } else if (event === "session") {
    state.sessionId = data.session_id;
    if (data.vm_id) state.opsVmId = data.vm_id;
    if (data.guest_id) {
      state.guestId = data.guest_id;
      localStorage.setItem("ivm_preview_guest", data.guest_id);
    }
    if (state.conversationId) {
      store.updateConversation(state.conversationId, {
        sessionId: data.session_id,
        ...(data.vm_id ? { vmId: data.vm_id } : {}),
      });
      renderHistoryList();
    }
    if (data.vm_id || data.session_id) {
      showOpsResourceBar({
        vmId: data.vm_id,
        sessionId: data.session_id,
      });
    }
  } else if (event === "tool_called") {
    addStep(data.name || "tool", data.args || "");
  } else if (event === "tool_output") {
    addStep("output", (data.output || "").slice(0, 1500));
  } else if (event === "usage") {
    showUsage(data);
    if (state.conversationId) {
      store.updateConversation(state.conversationId, { usage: data });
      renderHistoryList();
    }
    track("preview_usage", {
      total_tokens: data.total_tokens || 0,
      input_tokens: data.input_tokens || 0,
      output_tokens: data.output_tokens || 0,
      model: data.model || null,
    });
  } else if (event === "ops") {
    state.mode = "ops";
    setOpsChrome(true);
    const todos = (data.actions || []).map((a) => ({
      id: a.id,
      title: a.label || a.id,
      status: a.status || "pending",
    }));
    showPlanPanel({
      summary: data.summary || "Sandbox",
      todos,
    });
    if (els.planApprove) els.planApprove.hidden = true;
    if (els.planLabel) els.planLabel.textContent = "Sandbox";
    if (els.planReviseBtn) els.planReviseBtn.hidden = true;
    if (els.planDiscard) els.planDiscard.hidden = true;
  } else if (event === "status") {
    if (els.buildStreamHead && data.message) {
      els.buildStreamHead.textContent = data.message;
    }
    if (els.stageLabel && state.mode === "ops") {
      els.stageLabel.textContent = "Sandbox";
    }
  } else if (event === "ops_result") {
    if (els.opsResult) {
      const title = data.title ? `${data.title}\n` : "";
      els.opsResult.hidden = false;
      els.opsResult.textContent = `${title}${data.text || ""}`.trim();
    }
  } else if (event === "ops_done") {
    state.mode = "ops";
    setOpsChrome(true);
    if (data.session_id) state.sessionId = data.session_id;
    if (data.vm_id) state.opsVmId = data.vm_id;
    if (data.pty_id) state.opsPtyId = data.pty_id;
    if (els.stageLabel) els.stageLabel.textContent = "Terminal";
    if (els.buildStreamHead) {
      els.buildStreamHead.textContent = data.message || "Ready";
    }
    els.frame.hidden = true;
    setPreviewLinks(false);
    showOpsResourceBar({
      vmId: data.vm_id,
      sessionId: data.session_id,
      ptyId: data.pty_id,
    });
    if (state.conversationId) {
      store.updateConversation(state.conversationId, {
        sessionId: data.session_id || state.sessionId,
        vmId: data.vm_id || state.opsVmId,
        ptyId: data.pty_id || state.opsPtyId,
        mode: "ops",
        status: "ready",
      });
      renderHistoryList();
    }
    if (data.pty_path) {
      connectPty(data.pty_path);
      els.iterateForm.hidden = false;
    } else {
      hideBuildStream();
      showWorkspace();
      els.iterateForm.hidden = !state.sessionId && !state.opsVmId;
    }
    track("preview_ops_done", {
      session_id: data.session_id || null,
      vm_id: data.vm_id || null,
      has_pty: Boolean(data.pty_path),
    });
  } else if (event === "todos") {
    const plan = {
      summary: data.summary || state.plan?.summary || "",
      todos: (data.todos || []).map((t) => ({
        id: t.id,
        title: t.title,
        status: t.status || "pending",
      })),
    };
    showPlanPanel(plan);
    if (els.planApprove) els.planApprove.hidden = true;
    if (els.planLabel) els.planLabel.textContent = "Checklist";
    if (state.conversationId) {
      store.updateConversation(state.conversationId, { plan });
    }
  } else if (event === "todo") {
    if (data.id && data.status) patchTodoStatus(data.id, data.status);
  } else if (event === "preview") {
    showPreview(data.url, data.ttl_seconds);
    if (data.usage) showUsage(data.session_usage || data.usage);
    if (data.session_id) state.sessionId = data.session_id;
    if (typeof data.builds_remaining === "number") {
      setQuota({
        builds_remaining: data.builds_remaining,
        builds_limit: state.config?.guest_builds_per_day || 5,
        guest_id: state.guestId,
      });
    }
    if (state.conversationId) {
      const patch = {
        status: "ready",
        previewUrl: data.url,
        sessionId: data.session_id || state.sessionId,
        expiresAt: state.expiresAt,
        remixPath: data.remix_path || null,
        error: null,
      };
      if (data.session_usage || data.usage) {
        patch.usage = data.session_usage || data.usage;
      }
      const convo = store.updateConversation(state.conversationId, patch);
      showConvoMeta(convo);
      renderHistoryList();
    }
    track("preview_ready", { session_id: state.sessionId });
  } else if (event === "error") {
    const msg = data.message || "Something went wrong.";
    showError(msg);
    if (state.conversationId) {
      const convo = store.updateConversation(state.conversationId, {
        status: "error",
        error: msg,
      });
      renderHistoryList();
      if (!conversationHasProgress(convo || {})) hideWorkspace();
      else showBuildStream(msg);
    } else {
      hideWorkspace();
    }
    track("preview_error", { message: data.message || "" });
  }
}

function resetWorkspaceForBuild() {
  clearError();
  clearTimeline();
  els.phases.innerHTML = "";
  els.phases.hidden = true;
  els.frame.hidden = true;
  els.frame.src = "about:blank";
  els.iterateForm.hidden = true;
  els.usage.hidden = true;
  els.ttl.textContent = "";
  if (els.convoMeta) els.convoMeta.hidden = true;
  setPreviewLinks(false);
  showBuildStream("Starting…");
}

async function requestPlan({ prompt, templateId, feedback = null } = {}) {
  if (state.building || state.planning) return;
  const text = (prompt ?? els.prompt.value).trim();
  const attachments = payloadAttachments(state.buildAttachments);
  if (!text && !attachments.length) {
    els.prompt.focus();
    showError("Add a prompt or attach a screenshot.");
    return;
  }

  clearError();
  setPlanningBusy(true);
  track("preview_plan_started", {
    template_id: templateId || null,
    has_feedback: Boolean(feedback),
  });

  try {
    const response = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: text,
        template_id: templateId || null,
        guest_id: state.guestId || null,
        feedback: feedback || null,
        previous: feedback && state.plan
          ? {
              summary: state.plan.summary,
              todos: state.plan.todos.map(({ id, title }) => ({ id, title })),
            }
          : null,
        attachments,
        session_id: hasOpsContext() ? state.sessionId : null,
        vm_id: hasOpsContext() ? state.opsVmId : null,
        has_ops_context: hasOpsContext(),
      }),
    });
    if (!response.ok) {
      let msg = "Planning failed.";
      try {
        msg = (await response.json()).detail || msg;
      } catch {
        /* ignore */
      }
      showError(typeof msg === "string" ? msg : JSON.stringify(msg));
      return;
    }
    const data = await response.json();
    if (data.guest_id) {
      state.guestId = data.guest_id;
      localStorage.setItem("ivm_preview_guest", data.guest_id);
    }
    if (data.usage) showUsage(data.usage);

    // InstaVM client ops → run immediately (no web-app plan)
    if (data.mode === "ops") {
      hidePlanPanel();
      track("preview_ops_routed", { action_count: data.actions?.length || 0 });
      setPlanningBusy(false);
      await startOps({
        prompt: text,
        summary: data.summary,
        actions: data.actions || [],
      });
      return;
    }

    if (!data.plan) {
      showError("No plan returned.");
      return;
    }
    showPlanPanel(data.plan);
    track("preview_plan_ready", {
      todo_count: data.plan?.todos?.length || 0,
    });
  } catch {
    showError("Connection failed while planning.");
  } finally {
    setPlanningBusy(false);
  }
}

async function startOps({
  prompt,
  summary = "",
  actions = [],
  reuseConversation = false,
} = {}) {
  if (state.building) return;
  const text = (prompt ?? els.prompt.value).trim();
  if (!text) return;

  let convoId = state.conversationId;
  if (!reuseConversation || !convoId) {
    const convo = store.createConversation({
      prompt: text,
      templateId: null,
      attachmentNames: [],
    });
    convoId = convo.id;
    state.conversationId = convo.id;
    store.setActiveId(convo.id);
    syncUrlConversation(convo.id);
  } else {
    store.appendMessage(convoId, "user", text, "ops");
  }

  state.mode = "ops";
  setOpsChrome(true);
  store.updateConversation(convoId, {
    status: "building",
    mode: "ops",
    plan: {
      summary: summary || "Sandbox",
      todos: (actions || []).map((a, i) => ({
        id: a.id || `a${i}`,
        title: a.label || a.op || `step ${i + 1}`,
        status: "pending",
      })),
    },
  });
  renderHistoryList();

  if (!reuseConversation) resetWorkspaceForBuild();
  else {
    showWorkspace();
    disposePty();
  }
  showBuildStream(summary || "Working…");
  if (els.opsResult) {
    els.opsResult.hidden = true;
    els.opsResult.textContent = "";
  }
  if (els.stageLabel) els.stageLabel.textContent = "Sandbox";
  if (summary || actions?.length) {
    showPlanPanel({
      summary: summary || "Sandbox",
      todos: (actions || []).map((a, i) => ({
        id: a.id || `a${i}`,
        title: a.label || a.op || `step ${i + 1}`,
        status: "pending",
      })),
    });
    if (els.planApprove) els.planApprove.hidden = true;
    if (els.planLabel) els.planLabel.textContent = "Sandbox";
    if (els.planReviseBtn) els.planReviseBtn.hidden = true;
  }
  setBuildBusy(true, "Running…");
  track("preview_ops_started", { action_count: actions?.length || 0 });

  try {
    const response = await fetch("/api/ops", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: text,
        guest_id: state.guestId || null,
        session_id: state.sessionId || null,
        vm_id: state.opsVmId || null,
      }),
    });
    if (!response.ok) {
      let msg = "Ops failed.";
      try {
        msg = (await response.json()).detail || msg;
      } catch {
        /* ignore */
      }
      showError(typeof msg === "string" ? msg : JSON.stringify(msg));
      store.updateConversation(convoId, {
        status: "error",
        error: typeof msg === "string" ? msg : "Ops failed",
      });
      if (!reuseConversation) hideWorkspace();
      renderHistoryList();
      return;
    }
    await readSSE(response, handleStreamEvent);
    store.updateConversation(convoId, {
      status: "ready",
      error: null,
      mode: "ops",
      sessionId: state.sessionId,
      vmId: state.opsVmId,
    });
    renderHistoryList();
  } catch {
    showError("Connection failed.");
    store.updateConversation(convoId, {
      status: "error",
      error: "Connection failed",
    });
    if (!reuseConversation) hideWorkspace();
    renderHistoryList();
  } finally {
    setBuildBusy(false);
    refreshGuest();
  }
}

async function startBuild({ prompt, templateId, plan = null } = {}) {
  if (state.building) return;
  const text = (prompt ?? els.prompt.value).trim();
  const attachments = payloadAttachments(state.buildAttachments);
  if (!text && !attachments.length) {
    els.prompt.focus();
    showError("Add a prompt or attach a screenshot.");
    return;
  }

  const approved =
    plan ||
    (state.plan
      ? {
          summary: state.plan.summary,
          todos: state.plan.todos.map(({ id, title }) => ({ id, title })),
        }
      : null);
  if (!approved) {
    await requestPlan({ prompt: text, templateId });
    return;
  }

  const convo = store.createConversation({
    prompt: text || "Screenshot build",
    templateId: templateId || null,
    attachmentNames: state.buildAttachments.map((a) => a.name),
  });
  state.conversationId = convo.id;
  store.setActiveId(convo.id);
  syncUrlConversation(convo.id);
  store.updateConversation(convo.id, { plan: approved, status: "building" });
  renderHistoryList();

  resetWorkspaceForBuild();
  showPlanPanel({
    ...approved,
    todos: (approved.todos || []).map((t) => ({ ...t, status: "pending" })),
  });
  if (els.planApprove) els.planApprove.hidden = true;
  if (els.planLabel) els.planLabel.textContent = "Checklist";
  setBuildBusy(true, "Building…");
  track("preview_build_started", {
    template_id: templateId || null,
    attachment_count: attachments.length,
    todo_count: approved.todos?.length || 0,
  });

  try {
    const response = await fetch("/api/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: text,
        template_id: templateId || null,
        guest_id: state.guestId || null,
        attachments,
        plan: approved,
      }),
    });
    if (!response.ok) {
      let msg = "Build failed.";
      try {
        msg = (await response.json()).detail || msg;
      } catch {
        /* ignore */
      }
      showError(typeof msg === "string" ? msg : JSON.stringify(msg));
      store.updateConversation(convo.id, {
        status: "error",
        error: typeof msg === "string" ? msg : "Build failed",
      });
      hideWorkspace();
      renderHistoryList();
      return;
    }
    await readSSE(response, handleStreamEvent);
    const after = store.getConversation(convo.id);
    if (after?.status === "building") {
      store.updateConversation(convo.id, {
        status: "error",
        error: "Build ended without a preview",
      });
      if (!conversationHasProgress(after)) hideWorkspace();
      else showBuildStream("Build ended without a preview");
      renderHistoryList();
    }
  } catch (err) {
    showError(
      err?.message?.includes("replaceState")
        ? "Build UI glitch recovered — retry if preview didn’t appear."
        : "Connection failed. Is the Preview service running?"
    );
    store.updateConversation(convo.id, {
      status: "error",
      error: "Connection failed",
    });
    hideWorkspace();
    renderHistoryList();
  } finally {
    setBuildBusy(false);
    refreshGuest();
  }
}

async function startIterate(e) {
  e.preventDefault();
  if (state.building) return;
  const instruction = els.iterate.value.trim();
  const attachments = payloadAttachments(state.iterateAttachments);

  if (state.mode === "ops" || hasOpsContext()) {
    if (!instruction) return;
    clearError();
    els.iterate.value = "";
    await startOps({
      prompt: instruction,
      reuseConversation: true,
    });
    return;
  }

  if (!state.sessionId) return;
  if (!instruction && !attachments.length) return;
  clearError();
  setBuildBusy(true, "Revising…");
  showBuildStream("Applying changes…");
  els.iterateBtn.disabled = true;
  if (state.conversationId && instruction) {
    store.appendMessage(state.conversationId, "user", instruction, "iterate");
    renderHistoryList();
  }
  track("preview_iterate_started", {
    session_id: state.sessionId,
    attachment_count: attachments.length,
  });
  try {
    const response = await fetch("/api/iterate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        instruction,
        guest_id: state.guestId || null,
        attachments,
      }),
    });
    if (!response.ok) {
      let msg = "Update failed.";
      try {
        msg = (await response.json()).detail || msg;
      } catch {
        /* ignore */
      }
      showError(typeof msg === "string" ? msg : JSON.stringify(msg));
      if (state.previewUrl) showPreview(state.previewUrl);
      return;
    }
    await readSSE(response, (event, data) => {
      handleStreamEvent(event, data);
      if (event === "preview" && data.url) {
        els.frame.src = data.url;
      }
    });
    if (state.previewUrl && els.frame.hidden) {
      showPreview(state.previewUrl);
    }
    els.iterate.value = "";
    state.iterateAttachments = [];
    renderAttachments(state.iterateAttachments, els.iterateThumbs, "iterateAttachments");
  } catch {
    showError("Connection failed while applying changes.");
    if (state.previewUrl) showPreview(state.previewUrl);
  } finally {
    setBuildBusy(false);
    els.iterateBtn.disabled = false;
  }
}

function conversationHasProgress(convo) {
  // Phases alone (agent plan) don't count — only a real feed, preview, or ops session
  return Boolean(
    (convo.steps && convo.steps.length) ||
      convo.previewUrl ||
      (convo.mode === "ops" && convo.sessionId)
  );
}

function openConversation(id) {
  let convo = store.getConversation(id);
  if (!convo) return;
  if (state.building) return;

  // Interrupted / failed with no feed → prompt only
  if (
    (convo.status === "building" || convo.status === "error") &&
    !conversationHasProgress(convo)
  ) {
    if (convo.status === "building") {
      convo =
        store.updateConversation(id, {
          status: "error",
          error: "Build interrupted — submit again",
        }) || convo;
    }
  }

  state.conversationId = id;
  store.setActiveId(id);
  syncUrlConversation(id);
  clearError();

  els.prompt.value = convo.prompt || "";
  state.sessionId = convo.sessionId || null;
  state.previewUrl = convo.previewUrl || null;
  state.expiresAt = convo.expiresAt || null;
  state.mode = convo.mode || null;
  state.opsVmId = convo.vmId || null;
  setOpsChrome(state.mode === "ops");
  disposePty();

  clearTimeline();
  (convo.steps || []).forEach((s) => addStep(s.tag, s.body, { persist: false }));
  if (convo.phases?.length && conversationHasProgress(convo)) setPhases(convo.phases);
  else {
    els.phases.hidden = true;
    els.phases.innerHTML = "";
  }

  if (convo.usage) showUsage(convo.usage);
  else els.usage.hidden = true;

  showConvoMeta(convo);

  const ttlSeconds = convo.expiresAt
    ? Math.max(0, Math.floor((convo.expiresAt - Date.now()) / 1000))
    : 0;

  if (convo.mode === "ops" && convo.sessionId && convo.status === "ready") {
    showWorkspace();
    hideBuildStream();
    els.frame.hidden = true;
    els.iterateForm.hidden = false;
    if (els.stageLabel) els.stageLabel.textContent = "Sandbox";
    if (els.buildStreamHead) els.buildStreamHead.textContent = "Ready";
    setPreviewLinks(false);
  } else if (convo.previewUrl && (convo.status === "ready" || convo.status === "expired")) {
    showPreview(convo.previewUrl, ttlSeconds || undefined);
    if (!ttlSeconds) {
      els.ttl.textContent = "expired";
      els.iterateForm.hidden = true;
      hideBuildStream();
      els.frame.hidden = true;
      showWorkspace();
      if (els.stageLabel) els.stageLabel.textContent = "Expired";
      setPreviewLinks(true, convo.previewUrl);
    } else {
      els.iterateForm.hidden = !convo.sessionId;
    }
  } else if (conversationHasProgress(convo) && convo.status !== "error") {
    els.frame.hidden = true;
    els.iterateForm.hidden = true;
    showBuildStream(
      convo.status === "building"
        ? "Interrupted — feed from last attempt"
        : activePhaseLabel(convo) || "Build log"
    );
  } else if (conversationHasProgress(convo) && convo.status === "error") {
    // Keep the failed feed so the user can see what happened
    els.frame.hidden = true;
    els.iterateForm.hidden = true;
    showBuildStream(convo.error || "Build failed");
  } else {
    hideWorkspace();
  }

  if (convo.error && convo.status === "error") showError(convo.error);

  renderHistoryList();
  track("preview_conversation_opened", { conversation_id: id, status: convo.status });
}

function startNewChat({ silent = false } = {}) {
  if (state.building || state.planning) return;
  state.conversationId = null;
  store.setActiveId("");
  syncUrlConversation(null);
  state.sessionId = null;
  state.previewUrl = null;
  state.expiresAt = null;
  state.plan = null;
  state.mode = null;
  state.opsVmId = null;
  state.opsPtyId = null;
  if (state.ttlTimer) clearTimeout(state.ttlTimer);
  clearError();
  clearTimeline();
  els.phases.innerHTML = "";
  els.phases.hidden = true;
  hideWorkspace();
  hidePlanPanel();
  els.usage.hidden = true;
  els.ttl.textContent = "";
  if (els.convoMeta) els.convoMeta.hidden = true;
  els.prompt.value = "";
  state.buildAttachments = [];
  state.iterateAttachments = [];
  renderAttachments([], els.attachThumbs, "buildAttachments");
  renderAttachments([], els.iterateThumbs, "iterateAttachments");
  renderHistoryList();
  if (!silent) {
    els.prompt.focus();
    track("preview_new_chat");
  }
}

async function refreshGuest() {
  try {
    const res = await fetch("/api/guest");
    const data = await res.json();
    setQuota(data);
  } catch {
    /* ignore */
  }
}

function wireAttachUi() {
  els.attachInput.addEventListener("change", async () => {
    await addFiles(els.attachInput.files, "buildAttachments", els.attachThumbs);
    els.attachInput.value = "";
  });
  els.iterateAttachInput.addEventListener("change", async () => {
    await addFiles(els.iterateAttachInput.files, "iterateAttachments", els.iterateThumbs);
    els.iterateAttachInput.value = "";
  });

  const onPaste = async (e, key, thumbsEl) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files = [];
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (!files.length) return;
    e.preventDefault();
    await addFiles(files, key, thumbsEl);
  };
  els.prompt.addEventListener("paste", (e) =>
    onPaste(e, "buildAttachments", els.attachThumbs)
  );
  els.iterate.addEventListener("paste", (e) =>
    onPaste(e, "iterateAttachments", els.iterateThumbs)
  );

  const dragTarget = els.form;
  ["dragenter", "dragover"].forEach((ev) => {
    dragTarget.addEventListener(ev, (e) => {
      e.preventDefault();
      dragTarget.classList.add("is-drag");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dragTarget.addEventListener(ev, (e) => {
      e.preventDefault();
      dragTarget.classList.remove("is-drag");
    });
  });
  dragTarget.addEventListener("drop", async (e) => {
    await addFiles(e.dataTransfer?.files, "buildAttachments", els.attachThumbs);
  });
}

function wireHistoryUi() {
  applySidebarCollapsed(isNarrowViewport() ? true : store.isSidebarCollapsed());
  els.toggleHistory.addEventListener("click", () => applySidebarCollapsed(true));
  els.openHistory.addEventListener("click", () => applySidebarCollapsed(false));
  els.historyScrim?.addEventListener("click", () => applySidebarCollapsed(true));
  els.newChat.addEventListener("click", () => {
    startNewChat();
    if (isNarrowViewport()) applySidebarCollapsed(true);
  });
  let wasNarrow = isNarrowViewport();
  window.addEventListener("resize", () => {
    const narrow = isNarrowViewport();
    if (narrow === wasNarrow) {
      if (els.historyScrim) {
        els.historyScrim.hidden =
          document.body.classList.contains("history-collapsed") || !narrow;
      }
      return;
    }
    wasNarrow = narrow;
    applySidebarCollapsed(narrow ? true : store.isSidebarCollapsed());
  });
  renderHistoryList();
}

function applyEmbedMode() {
  const params = new URLSearchParams(location.search);
  const embed =
    params.get("embed") === "1" ||
    params.get("dash") === "1" ||
    params.get("from") === "dash";
  document.body.classList.toggle("is-embed", Boolean(embed));
  return Boolean(embed);
}

async function boot() {
  // Prompt-first: never flash an empty Live stage on load
  const isEmbed = applyEmbedMode();
  hideWorkspace();
  clearError();

  const cfgRes = await fetch("/api/config");
  state.config = await cfgRes.json();
  if (els.claimLink) {
    els.claimLink.href = `${state.config.signup_url}?from=preview`;
  }
  if (els.billingLink) {
    els.billingLink.href = state.config.billing_url;
  }
  if (els.hint) {
    els.hint.textContent = isEmbed
      ? ""
      : `${state.config.guest_builds_per_day}/day · ~${Math.round(
          state.config.preview_ttl_seconds / 60
        )}m ttl`;
  }
  if (els.attachHint) {
    els.attachHint.textContent = `up to ${state.config.max_attachments} · paste ok`;
  }
  await loadPostHog(state.config.posthog_key, state.config.posthog_host);
  track("preview_page_view", { embed: isEmbed });
  wireAttachUi();
  wireHistoryUi();
  store.abandonInterruptedBuilds();
  renderHistoryList();

  const tmplRes = await fetch("/api/templates");
  const tmplData = await tmplRes.json();
  renderTemplates(tmplData.templates || []);
  startOpsTicker(tmplData.ops_examples || []);
  await refreshGuest();

  const params = new URLSearchParams(location.search);
  const remix = params.get("remix");
  const convoParam = params.get("c");

  const shouldOpen = (id) => {
    const c = store.getConversation(id);
    if (!c) return false;
    // Only restore when there is a preview or a real build feed
    if (c.previewUrl && (c.status === "ready" || c.status === "expired")) return true;
    if ((c.steps || []).length > 0) return true;
    return false;
  };

  if (remix) {
    track("preview_remix_open", { session_id: remix });
    hidePlanPanel();
    hideWorkspace();
    try {
      const res = await fetch(`/api/session/${encodeURIComponent(remix)}`);
      if (!res.ok) {
        showError("This remix link is no longer available.");
      } else {
        const session = await res.json();
        const convo = store.upsertFromRemix(session);
        state.conversationId = convo.id;
        store.setActiveId(convo.id);
        syncUrlConversation(convo.id);
        if (session.prompt) els.prompt.value = session.prompt;
        const live = session.live !== false && session.preview_url;
        if (live) {
          state.sessionId = session.owned ? session.session_id : null;
          state.previewUrl = session.preview_url;
          showPreview(
            session.preview_url,
            Math.max(
              60,
              Math.floor((session.expires_at * 1000 - Date.now()) / 1000)
            )
          );
          showConvoMeta(convo);
          if (!session.owned) {
            els.iterateForm.hidden = true;
            state.sessionId = null;
            els.hint.textContent =
              "Remix — edit the prompt or hit Build to make your own copy.";
          }
        } else {
          state.sessionId = null;
          state.previewUrl = null;
          hideWorkspace();
          els.hint.textContent =
            "Original preview expired — Build to remix from this prompt.";
        }
        renderHistoryList();
      }
    } catch {
      showError("Could not open remix link.");
    }
  } else if (convoParam && shouldOpen(convoParam)) {
    openConversation(convoParam);
  } else if (state.conversationId && shouldOpen(state.conversationId)) {
    openConversation(state.conversationId);
  } else {
    const draftId = convoParam || state.conversationId;
    const draft = draftId ? store.getConversation(draftId) : null;
    hideWorkspace();
    if (draft?.prompt) {
      els.prompt.value = draft.prompt;
      state.conversationId = draft.id;
      store.setActiveId(draft.id);
      syncUrlConversation(draft.id);
      renderHistoryList();
    } else {
      startNewChat({ silent: true });
    }
  }

  const templateParam = params.get("template");
  if (templateParam && !remix && !convoParam) {
    const match = (tmplData.templates || []).find((t) => t.id === templateParam);
    if (match) {
      els.prompt.value = match.prompt;
    }
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  // Build → plan first; Approve & build starts the sandbox
  requestPlan({ prompt: els.prompt.value });
});
els.iterateForm.addEventListener("submit", startIterate);
els.planApprove?.addEventListener("click", () => {
  if (!state.plan) return;
  startBuild({
    prompt: els.prompt.value,
    plan: {
      summary: state.plan.summary,
      todos: state.plan.todos.map(({ id, title }) => ({ id, title })),
    },
  });
});
els.planDiscard?.addEventListener("click", () => {
  state.plan = null;
  hidePlanPanel();
  clearError();
});
els.planReviseBtn?.addEventListener("click", () => {
  if (!els.planReviseBox) return;
  els.planReviseBox.hidden = false;
  if (els.planUpdateBtn) els.planUpdateBtn.hidden = false;
  els.planReviseBtn.hidden = true;
  els.planFeedback?.focus();
});
els.planUpdateBtn?.addEventListener("click", () => {
  const feedback = (els.planFeedback?.value || "").trim();
  if (!feedback) {
    els.planFeedback?.focus();
    showError("Describe what to change in the plan.");
    return;
  }
  requestPlan({ prompt: els.prompt.value, feedback });
});
els.copyUrl.addEventListener("click", async () => {
  if (!state.previewUrl) return;
  try {
    await navigator.clipboard.writeText(state.previewUrl);
    track("preview_url_copied");
  } catch {
    /* ignore */
  }
});

boot().catch((err) => {
  showError(err?.message || "Failed to load Preview.");
});
