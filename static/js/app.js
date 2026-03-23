// AI Agent - Frontend Application

const API_BASE = '';
let currentSessionId = null;
let chatHistory = [];

const chatContainer = document.getElementById('chatContainer');
const welcomeMessage = document.getElementById('welcomeMessage');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const modelSelect = document.getElementById('modelSelect');
const newChatBtn = document.getElementById('newChatBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const errorMessage = document.getElementById('errorMessage');
const historyList = document.getElementById('historyList');
const noHistory = document.getElementById('noHistory');

async function loadModels() {
  try {
    const res = await fetch(`${API_BASE}/api/models`);
    const data = await res.json();
    modelSelect.innerHTML = '';
    const defaultModel = data.default || 'gpt-4o';
    for (const m of data.models) {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = `${m.name}${m.available ? '' : ' (no key)'}`;
      opt.disabled = !m.available;
      if (m.id === defaultModel && m.available) opt.selected = true;
      modelSelect.appendChild(opt);
    }
    if (!modelSelect.value && data.models.length) {
      const firstAvailable = data.models.find(m => m.available);
      if (firstAvailable) modelSelect.value = firstAvailable.id;
    }
  } catch (err) {
    modelSelect.innerHTML = '<option value="">Failed to load models</option>';
    showError('Failed to load models: ' + err.message);
  }
}

async function loadHistoryList() {
  try {
    const res = await fetch(`${API_BASE}/api/history`);
    const data = await res.json();
    const sessions = data.sessions || [];
    noHistory.style.display = sessions.length ? 'none' : 'block';
    historyList.querySelectorAll('.history-item').forEach(el => el.remove());
    for (const s of sessions) {
      const sid = s.id || s;
      const title = typeof s === 'object' ? (s.title || 'New chat') : `${sid.slice(0, 8)}...`;
      const item = document.createElement('div');
      item.className = 'history-item group flex items-center gap-1 rounded-lg text-sm text-slate-700 hover:bg-slate-100';
      if (sid === currentSessionId) item.classList.add('active');
      item.dataset.sessionId = sid;
      item.innerHTML = `
        <button class="flex-1 min-w-0 text-left px-3 py-2 truncate" title="${escapeHtml(title)}">${escapeHtml(title)}</button>
        <div class="flex opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button class="rename-btn p-1.5 rounded hover:bg-slate-200 text-slate-500 hover:text-teal-600" title="Preimenuj">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
          </button>
          <button class="delete-btn p-1.5 rounded hover:bg-red-100 text-slate-500 hover:text-red-600" title="Obriši">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </div>
      `;
      item.querySelector('button:first-child').addEventListener('click', (e) => { e.stopPropagation(); loadSession(sid); });
      item.querySelector('.rename-btn').addEventListener('click', (e) => { e.stopPropagation(); renameChat(sid, title); });
      item.querySelector('.delete-btn').addEventListener('click', (e) => { e.stopPropagation(); deleteChat(sid); });
      historyList.appendChild(item);
    }
  } catch (err) {
    console.error('Failed to load history:', err);
  }
}

async function renameChat(sessionId, currentTitle) {
  const newTitle = prompt('Preimenuj chat:', currentTitle);
  if (newTitle === null || newTitle.trim() === '') return;
  try {
    const res = await fetch(`${API_BASE}/api/chat/rename?session_id=${encodeURIComponent(sessionId)}&title=${encodeURIComponent(newTitle.trim())}`, { method: 'PATCH' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to rename');
    loadHistoryList();
  } catch (err) {
    showError('Failed to rename: ' + err.message);
  }
}

async function deleteChat(sessionId) {
  if (!confirm('Obriši ovaj chat? Ova akcija se ne može poništiti.')) return;
  try {
    const res = await fetch(`${API_BASE}/api/chat/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to delete');
    if (currentSessionId === sessionId) {
      currentSessionId = null;
      chatHistory = [];
      renderChat();
      welcomeMessage.style.display = 'block';
    }
    loadHistoryList();
  } catch (err) {
    showError('Failed to delete: ' + err.message);
  }
}

async function loadSession(sessionId) {
  try {
    const res = await fetch(`${API_BASE}/api/history?session_id=${sessionId}`);
    const data = await res.json();
    currentSessionId = sessionId;
    chatHistory = data.messages || [];
    renderChat();
    loadHistoryList();
  } catch (err) {
    showError('Failed to load session: ' + err.message);
  }
}

function getLastUserMessageIndex() {
  for (let i = chatHistory.length - 1; i >= 0; i--) {
    if (chatHistory[i].role === 'user') return i;
  }
  return -1;
}

function renderChat(scrollToLastQuestion = false) {
  welcomeMessage.style.display = chatHistory.length ? 'none' : 'block';
  const existing = chatContainer.querySelectorAll('.chat-message');
  existing.forEach(el => el.remove());
  const lastUserIdx = getLastUserMessageIndex();

  chatHistory.forEach((msg, i) => {
    const div = document.createElement('div');
    div.className = 'chat-message flex gap-3';
    const isUser = msg.role === 'user';
    const isLastUser = isUser && i === lastUserIdx;
    div.innerHTML = `
      <div class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isUser ? 'bg-teal-500 text-white' : 'bg-slate-200 text-slate-600'}">
        ${isUser ? '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"/></svg>' : '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z"/></svg>'}
      </div>
      <div class="flex-1 min-w-0">
        <div class="${isUser ? 'user-bubble' : 'assistant-bubble'} inline-block max-w-[85%] px-4 py-3">
          <div class="whitespace-pre-wrap break-words">${escapeHtml(msg.content)}</div>
        </div>
      </div>
    `;
    if (isLastUser) div.id = 'lastUserMessage';
    chatContainer.appendChild(div);
  });

  if (scrollToLastQuestion) {
    const el = document.getElementById('lastUserMessage');
    if (el) el.scrollIntoView({ block: 'start', behavior: 'smooth' });
  } else {
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function setLoading(show) {
  loadingOverlay.classList.toggle('hidden', !show);
}

function showError(msg) {
  errorMessage.textContent = msg;
  errorMessage.classList.remove('hidden');
}

function hideError() {
  errorMessage.classList.add('hidden');
}

function shortenStatus(msg) {
  if (msg.length <= 70) return msg;
  return msg.slice(0, 67) + '...';
}

function updateStatusSteps(steps) {
  const container = document.getElementById('statusSteps');
  const placeholder = document.getElementById('statusPlaceholder');
  if (steps.length === 0) {
    placeholder.style.display = 'block';
    container.innerHTML = '';
    return;
  }
  placeholder.style.display = 'none';
  container.innerHTML = steps.map((s, i) =>
    `<div class="status-step flex items-center gap-2 text-sm text-slate-600">
      <span class="text-teal-500 shrink-0">${i + 1}.</span>
      <span class="truncate" title="${escapeHtml(s)}">${escapeHtml(shortenStatus(s))}</span>
    </div>`
  ).join('');
  const scrollParent = container.parentElement;
  if (scrollParent && scrollParent.scrollHeight > scrollParent.clientHeight) {
    scrollParent.scrollTop = scrollParent.scrollHeight;
  }
}

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text) return;
  const modelId = modelSelect.value;
  if (!modelId) {
    showError('Izaberi model');
    return;
  }

  setLoading(true);
  updateStatusSteps([]);
  hideError();

  chatHistory.push({ role: 'user', content: text });
  messageInput.value = '';
  renderChat();

  const messages = chatHistory.map(m => ({ role: m.role, content: m.content }));

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        model_id: modelId,
        session_id: currentSessionId,
        history: messages.slice(0, -1),
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      let errMsg = 'Request failed';
      try {
        const errData = JSON.parse(errText);
        errMsg = errData.detail || errData.error || errMsg;
        if (Array.isArray(errMsg)) errMsg = errMsg.map(e => e.msg || e).join('; ');
      } catch (_) {
        if (errText.length < 200) errMsg = errText;
      }
      throw new Error(errMsg);
    }

    const contentType = res.headers.get('content-type') || '';
    const isNDJSON = contentType.includes('ndjson') || contentType.includes('x-ndjson');

    if (isNDJSON && res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const statusSteps = [];
      let finalData = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          try {
            const data = JSON.parse(trimmed);
            if (data.type === 'status') {
              statusSteps.push(data.message);
              updateStatusSteps(statusSteps);
            } else if (data.type === 'done') {
              finalData = data;
            } else if (data.type === 'error') {
              throw new Error(data.detail || 'Unknown error');
            }
          } catch (e) {
            if (e instanceof Error && !(e instanceof SyntaxError)) throw e;
          }
        }
      }
      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer.trim());
          if (data.type === 'done') finalData = data;
          else if (data.type === 'error') throw new Error(data.detail || 'Unknown error');
        } catch (e) {
          if (e instanceof Error && !(e instanceof SyntaxError)) throw e;
        }
      }
      if (finalData) {
        currentSessionId = finalData.session_id;
        chatHistory.push({ role: 'assistant', content: finalData.content });
        renderChat(true);
        loadHistoryList();
      } else {
        showError('No response received from agent');
        chatHistory.pop();
        renderChat();
      }
    } else {
      const data = await res.json();
      currentSessionId = data.session_id;
      chatHistory.push({ role: 'assistant', content: data.content });
      renderChat(true);
      loadHistoryList();
    }
  } catch (err) {
    chatHistory.pop();
    renderChat();
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

newChatBtn.addEventListener('click', async () => {
  try {
    const res = await fetch(`${API_BASE}/api/chat/new`, { method: 'POST' });
    const data = await res.json();
    currentSessionId = data.session_id;
    chatHistory = [];
    renderChat();
    loadHistoryList();
  } catch (err) {
    showError('Failed to create new chat: ' + err.message);
  }
});

clearChatBtn.addEventListener('click', async () => {
  if (!currentSessionId) return;
  try {
    await fetch(`${API_BASE}/api/chat/clear?session_id=${currentSessionId}`, { method: 'POST' });
    chatHistory = [];
    renderChat();
    loadHistoryList();
    currentSessionId = null;
  } catch (err) {
    showError('Failed to clear chat: ' + err.message);
  }
});

messageInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', sendMessage);

loadModels();
loadHistoryList();
