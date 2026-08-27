(() => {
  let messages = [];
  let waiting = false;
  const conversationId = (() => {
    const key = 'agrovision-chat-conversation';
    let value = localStorage.getItem(key);
    if (!value || !/^[A-Za-z0-9_-]{8,80}$/.test(value)) {
      value = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem(key, value);
    }
    return value;
  })();

  const byId = id => document.getElementById(id);
  const language = () => byId('languageSelect')?.value || 'en';
  const text = key => typeof getTranslation === 'function' ? getTranslation(key) : key;

  function renderMarkdown(content) {
    const escape = value => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const inline = value => escape(value).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>');
    return content.split(/\r?\n/).map(line => {
      if (/^\s*---+\s*$/.test(line)) return '<hr>';
      const heading = line.match(/^\s*(#{1,4})\s+(.+)$/);
      if (heading) return `<h${Math.min(heading[1].length + 2, 6)}>${inline(heading[2])}</h${Math.min(heading[1].length + 2, 6)}>`;
      const bullet = line.match(/^\s*[*-]\s+(.+)$/);
      if (bullet) return `<div class="chatbot-list-item"><span>•</span><span>${inline(bullet[1])}</span></div>`;
      const numbered = line.match(/^\s*(\d+)\.\s+(.+)$/);
      if (numbered) return `<div class="chatbot-list-item"><span>${numbered[1]}.</span><span>${inline(numbered[2])}</span></div>`;
      return line.trim() ? `<p>${inline(line)}</p>` : '<div class="chatbot-line-gap"></div>';
    }).join('');
  }

  function addMessage(role, content, isError = false) {
    messages.push({ role, content });
    const item = document.createElement('div');
    item.className = `chatbot-message ${role}${isError ? ' error' : ''}`;
    if (role === 'assistant') {
      const avatar = document.createElement('span');
      avatar.className = 'chatbot-message-avatar';
      avatar.textContent = '🤖';
      item.appendChild(avatar);
    }
    const body = document.createElement('span');
    body.className = 'chatbot-message-body';
    if (role === 'assistant') body.innerHTML = renderMarkdown(content);
    else body.textContent = content;
    item.appendChild(body);
    byId('chatbotMessages').appendChild(item);
    byId('chatbotMessages').scrollTop = byId('chatbotMessages').scrollHeight;
  }

  function showWelcome() {
    if (!messages.length) {
      addMessage('assistant', text('chatbotWelcome'));
      const suggestions = document.createElement('div');
      suggestions.className = 'chatbot-suggestions';
      ['chatbotSuggestion1', 'chatbotSuggestion2', 'chatbotSuggestion3', 'chatbotSuggestion4', 'chatbotSuggestion5'].forEach(key => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chatbot-suggestion';
        button.textContent = text(key);
        button.addEventListener('click', () => {
          byId('chatbotInput').value = text(key).replace(/^[^\w\u0080-\uFFFF]+\s*/, '');
          send();
        });
        suggestions.appendChild(button);
      });
      byId('chatbotMessages').appendChild(suggestions);
      byId('chatbotMessages').scrollTop = byId('chatbotMessages').scrollHeight;
    }
  }

  function setOpen(open) {
    const panel = byId('chatbotPanel');
    panel.classList.toggle('open', open);
    panel.setAttribute('aria-hidden', String(!open));
    byId('chatbotLauncher').setAttribute('aria-expanded', String(open));
    if (open) { showWelcome(); byId('chatbotInput').focus(); }
  }

  function context() {
    const value = id => byId(id)?.textContent?.trim() || null;
    return {
      soil_moisture: value('mv'),
      temperature: value('tv'),
      humidity: value('hv'),
      pump_status: value('plb'),
      latest_disease: value('dn2'),
      disease_confidence: value('dc2')
    };
  }

  async function send() {
    const input = byId('chatbotInput');
    const message = input.value.trim();
    if (!message || waiting) return;
    input.value = '';
    addMessage('user', message);
    waiting = true;
    byId('chatbotSend').disabled = true;
    const indicator = document.createElement('div');
    indicator.className = 'chatbot-thinking';
    indicator.innerHTML = `<span>🤖 ${text('chatbotThinking')}</span><span class="chatbot-dots"><i></i><i></i><i></i></span>`;
    byId('chatbotMessages').appendChild(indicator);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, language: language(), conversation_id: conversationId, context: context() })
      });
      const data = await response.json().catch(() => ({}));
      indicator.remove();
      if (!response.ok || data.error) throw new Error(data.message || text('chatbotError'));
      addMessage('assistant', data.response);
    } catch (error) {
      indicator.remove();
      addMessage('assistant', error.message || text('chatbotError'), true);
    } finally {
      waiting = false;
      byId('chatbotSend').disabled = false;
      input.focus();
    }
  }

  function refreshLanguage() {
    document.querySelectorAll('#chatbotPanel [data-i18n]').forEach(element => {
      element.textContent = text(element.dataset.i18n);
    });
    const input = byId('chatbotInput');
    input.placeholder = text('chatbotPlaceholder');
    if (messages.length === 1 && messages[0].role === 'assistant') {
      const welcomeBody = byId('chatbotMessages').querySelector('.chatbot-message-body');
      if (welcomeBody) welcomeBody.textContent = text('chatbotWelcome');
      messages[0].content = text('chatbotWelcome');
      byId('chatbotMessages').querySelectorAll('.chatbot-suggestion').forEach((button, index) => {
        button.textContent = text(`chatbotSuggestion${index + 1}`);
      });
    }
  }

  async function loadHistory() {
    try {
      const response = await fetch(`/api/chat/history?conversation_id=${encodeURIComponent(conversationId)}`);
      const data = await response.json();
      (data.messages || []).forEach(item => addMessage(item.role, item.content));
    } catch (error) {
      console.warn('Chat history could not be loaded');
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    byId('chatbotLauncher').addEventListener('click', () => setOpen(!byId('chatbotPanel').classList.contains('open')));
    byId('chatbotClose').addEventListener('click', () => setOpen(false));
    byId('chatbotClear').addEventListener('click', async () => {
      try { await fetch(`/api/chat/history?conversation_id=${encodeURIComponent(conversationId)}`, { method: 'DELETE' }); }
      catch (error) { console.warn('Chat history could not be cleared'); }
      messages = [];
      byId('chatbotMessages').replaceChildren();
      showWelcome();
    });
    byId('chatbotSend').addEventListener('click', send);
    byId('chatbotInput').addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); }
    });
    refreshLanguage();
    loadHistory().then(() => { if (!messages.length) showWelcome(); });
  });

  window.refreshChatbotLanguage = refreshLanguage;
})();
