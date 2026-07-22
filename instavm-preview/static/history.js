/** Conversation history persistence for InstaVM Preview (guest localStorage). */

const STORE_KEY = "ivm_preview_conversations_v1";
const ACTIVE_KEY = "ivm_preview_active_conversation";
const COLLAPSED_KEY = "ivm_preview_sidebar_collapsed";
const MAX_CONVERSATIONS = 40;
const MAX_STEPS = 80;
const MAX_MESSAGES = 40;

function uid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function titleFromPrompt(prompt) {
  const t = String(prompt || "").trim().replace(/\s+/g, " ");
  if (!t) return "Untitled build";
  return t.length > 48 ? `${t.slice(0, 48)}…` : t;
}

export function loadStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return { conversations: [] };
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.conversations)) return { conversations: [] };
    return parsed;
  } catch {
    return { conversations: [] };
  }
}

function saveStore(store) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    /* quota — drop oldest */
    try {
      store.conversations = store.conversations.slice(0, Math.floor(MAX_CONVERSATIONS / 2));
      localStorage.setItem(STORE_KEY, JSON.stringify(store));
    } catch {
      /* ignore */
    }
  }
}

export function listConversations() {
  return loadStore().conversations.slice().sort((a, b) => b.updatedAt - a.updatedAt);
}

/** Mark abandoned in-flight builds (page reload) so UI stays on a clean prompt. */
export function abandonInterruptedBuilds() {
  const store = loadStore();
  let changed = false;
  for (const c of store.conversations) {
    const hasFeed = (c.steps && c.steps.length) || c.previewUrl;
    if (c.status === "building" && !hasFeed) {
      c.status = "error";
      c.error = c.error || "Build interrupted — submit again";
      c.updatedAt = Date.now();
      changed = true;
    } else if (c.status === "building" && !c.previewUrl) {
      c.status = "error";
      c.error = c.error || "Build interrupted";
      c.updatedAt = Date.now();
      changed = true;
    }
  }
  if (changed) saveStore(store);
  return changed;
}

export function getConversation(id) {
  return loadStore().conversations.find((c) => c.id === id) || null;
}

export function getActiveId() {
  return localStorage.getItem(ACTIVE_KEY) || "";
}

export function setActiveId(id) {
  if (id) localStorage.setItem(ACTIVE_KEY, id);
  else localStorage.removeItem(ACTIVE_KEY);
}

export function isSidebarCollapsed() {
  return localStorage.getItem(COLLAPSED_KEY) === "1";
}

export function setSidebarCollapsed(collapsed) {
  localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
}

export function createConversation({ prompt = "", templateId = null, attachmentNames = [] } = {}) {
  const now = Date.now();
  const convo = {
    id: uid(),
    title: titleFromPrompt(prompt),
    createdAt: now,
    updatedAt: now,
    prompt,
    templateId,
    attachmentNames: attachmentNames.slice(0, 8),
    sessionId: null,
    vmId: null,
    ptyId: null,
    mode: null,
    previewUrl: null,
    expiresAt: null,
    remixPath: null,
    status: "building",
    error: null,
    plan: null,
    usage: null,
    phases: [],
    steps: [],
    messages: prompt
      ? [{ role: "user", text: prompt, at: now, kind: "build" }]
      : [],
  };
  const store = loadStore();
  store.conversations.unshift(convo);
  if (store.conversations.length > MAX_CONVERSATIONS) {
    store.conversations = store.conversations.slice(0, MAX_CONVERSATIONS);
  }
  saveStore(store);
  setActiveId(convo.id);
  return convo;
}

export function updateConversation(id, patch) {
  const store = loadStore();
  const idx = store.conversations.findIndex((c) => c.id === id);
  if (idx < 0) return null;
  const prev = store.conversations[idx];
  const next = {
    ...prev,
    ...patch,
    updatedAt: Date.now(),
  };
  if (patch.prompt && !patch.title) {
    next.title = titleFromPrompt(patch.prompt);
  }
  if (Array.isArray(next.steps) && next.steps.length > MAX_STEPS) {
    next.steps = next.steps.slice(-MAX_STEPS);
  }
  if (Array.isArray(next.messages) && next.messages.length > MAX_MESSAGES) {
    next.messages = next.messages.slice(-MAX_MESSAGES);
  }
  store.conversations[idx] = next;
  // bump to top
  store.conversations.splice(idx, 1);
  store.conversations.unshift(next);
  saveStore(store);
  return next;
}

export function appendStep(id, tag, body) {
  const convo = getConversation(id);
  if (!convo) return null;
  const steps = [...(convo.steps || []), { tag, body: String(body || "").slice(0, 1500), at: Date.now() }];
  return updateConversation(id, { steps });
}

export function appendMessage(id, role, text, kind = "note") {
  const convo = getConversation(id);
  if (!convo) return null;
  const messages = [
    ...(convo.messages || []),
    { role, text: String(text || "").slice(0, 4000), at: Date.now(), kind },
  ];
  return updateConversation(id, { messages });
}

export function setPhases(id, phases) {
  return updateConversation(id, {
    phases: (phases || []).map((p) => ({
      id: p.id,
      label: p.label,
      status: p.status || "pending",
    })),
  });
}

export function patchPhase(id, phaseId, label, status) {
  const convo = getConversation(id);
  if (!convo) return null;
  const phases = (convo.phases || []).map((p) =>
    p.id === phaseId
      ? { ...p, label: label || p.label, status: status || p.status }
      : p
  );
  return updateConversation(id, { phases });
}

export function deleteConversation(id) {
  const store = loadStore();
  store.conversations = store.conversations.filter((c) => c.id !== id);
  saveStore(store);
  if (getActiveId() === id) setActiveId("");
}

export function upsertFromRemix(session) {
  const existing = listConversations().find(
    (c) => c.sessionId === session.session_id || c.previewUrl === session.preview_url
  );
  const live = session.live !== false && Boolean(session.preview_url);
  const patch = {
    prompt: session.prompt || "Remixed preview",
    sessionId: live ? session.session_id : null,
    previewUrl: live ? session.preview_url : null,
    expiresAt: session.expires_at ? session.expires_at * 1000 : null,
    status: live ? "ready" : "draft",
    remixPath: `/?remix=${session.session_id}`,
    usage: session.usage || null,
    error: null,
  };
  if (existing) {
    return updateConversation(existing.id, patch);
  }
  const convo = createConversation({
    prompt: session.prompt || "Remixed preview",
    templateId: session.template_id || null,
  });
  return updateConversation(convo.id, patch);
}
