/** ETHER Chat UX v0.7.2 — Clear, turn-first, chips, typing. Hardened.
 * Injected by dashboard/app.py on every /. Works even if host was stale.
 */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')
    .replace(/"/g, '"')
    .replace(/'/g, '&#39;');

  function ensureStyles() {
    if (document.getElementById('ether-chat-ux-css')) return;
    const st = document.createElement('style');
    st.id = 'ether-chat-ux-css';
    st.textContent = [
      '.chat-header .chat-actions{display:flex;gap:6px;align-items:center}',
      '.btn-clear{background:#2a1515;border:1px solid #5a3030;color:#ff5c5c;border-radius:5px;padding:4px 10px;font-size:10px;cursor:pointer;font-weight:600;text-transform:uppercase}',
      '.btn-clear:hover{background:#3a1a1a}',
      '.chat-chips{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px;border-bottom:1px solid #1c2836;background:#0a1016;flex-shrink:0}',
      '.chip{background:#0b1017;border:1px solid #1c2836;color:#7a8796;border-radius:999px;padding:4px 10px;font-size:11px;cursor:pointer;font-family:Consolas,monospace}',
      '.chip:hover{border-color:#2a5a7a;color:#4cc9f0}',
      '.chat-msg.user{border-left:3px solid #9b8cff}',
      '.chat-msg.agent{border-left:3px solid #3ddc97}',
      '.chat-msg .channel{display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;margin-left:6px;text-transform:uppercase;background:#1a1a2a;color:#9b8cff}',
      '.chat-msg .channel.local{background:#0d2a1a;color:#3ddc97}',
      '.chat-msg .channel.git{background:#1a2a3a;color:#4cc9f0}',
      '.chat-msg .channel.status{background:#2a2a1a;color:#f0b429}',
      '.chat-msg .channel.grok{background:#2a1a2a;color:#9b8cff}',
      '.chat-msg .channel.job{background:#2a1a0d;color:#f0b429}',
      '.typing{color:#7a8796;font-size:12px;padding:8px;font-style:italic}',
      '.chat-empty{color:#7a8796;padding:28px 12px;text-align:center;font-size:13px;line-height:1.5}',
      '.chat-err{color:#ff5c5c;font-size:12px;padding:8px;border:1px solid #5a3030;border-radius:6px;margin:6px 0;background:#1a0f0f}'
    ].join('');
    document.head.appendChild(st);
  }

  function enhanceShell() {
    const shell = document.querySelector('.chat-shell');
    if (!shell) return;
    if (shell.dataset.ux !== '1') {
      shell.dataset.ux = '1';
      const header = shell.querySelector('.chat-header');
      if (header) {
        header.innerHTML =
          '<span>ETHER agent · turn protocol</span>' +
          '<div class="chat-actions">' +
          '<span id="chatCount" style="font-family:Consolas,monospace;color:#4cc9f0">0 turns</span>' +
          '<button type="button" class="btn-clear" id="chatClear" title="Archive bus + clear turns">Clear</button>' +
          '</div>';
      }
      const messages = shell.querySelector('.chat-messages');
      if (messages && !shell.querySelector('.chat-chips')) {
        const chips = document.createElement('div');
        chips.className = 'chat-chips';
        chips.id = 'chatChips';
        chips.innerHTML =
          '<button type="button" class="chip" data-msg="status">status</button>' +
          '<button type="button" class="chip" data-msg="git status">git status</button>' +
          '<button type="button" class="chip" data-msg="rates">rates</button>' +
          '<button type="button" class="chip" data-msg="doctor">doctor</button>' +
          '<button type="button" class="chip" data-msg="ask grok: summarize host state">ask grok</button>';
        messages.parentNode.insertBefore(chips, messages);
      }
      const input = $('chatInput');
      if (input) {
        input.placeholder = 'Message ETHER (status · git · local LLM · ask grok) — Enter to send';
      }
    }
    // Bind controls every pass (DOM may be replaced)
    const clearBtn = $('chatClear');
    if (clearBtn && !clearBtn.dataset.bound) {
      clearBtn.dataset.bound = '1';
      clearBtn.addEventListener('click', clearChat);
    }
    document.querySelectorAll('#chatChips .chip').forEach(function (chip) {
      if (chip.dataset.bound) return;
      chip.dataset.bound = '1';
      chip.addEventListener('click', function () {
        sendChat(chip.getAttribute('data-msg'));
      });
    });
    const btn = $('chatSend');
    if (btn && !btn.dataset.uxBound) {
      btn.dataset.uxBound = '1';
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopImmediatePropagation();
        sendChat();
      }, true);
    }
    const input = $('chatInput');
    if (input && !input.dataset.uxBound) {
      input.dataset.uxBound = '1';
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          e.stopImmediatePropagation();
          sendChat();
        }
      }, true);
    }
  }

  function renderTurns(turns) {
    if (!turns || !turns.length) {
      return '<div class="chat-empty">No turns yet — try a chip or type a hypothesis below</div>';
    }
    return turns.slice().reverse().map(function (t) {
      const ts = (t.ts || '').toString();
      const clock = ts.indexOf('T') >= 0 ? ts.slice(11, 19) : ts.slice(0, 8);
      const ch = String(t.channel || t.intent || 'local').toLowerCase();
      return (
        '<div class="chat-msg user">' +
          '<span class="from">you</span>' +
          '<div class="text">' + esc(t.message || '') + '</div>' +
          '<div class="ts">' + esc(clock) + '</div>' +
        '</div>' +
        '<div class="chat-msg agent">' +
          '<span class="from">ETHER</span>' +
          '<span class="channel ' + esc(ch) + '">' + esc(ch) + '</span>' +
          '<div class="text">' + esc(t.reply || '(no reply)') + '</div>' +
          '<div class="ts">' + esc(clock) + ' · ' + (t.ok === false ? 'FAIL' : 'ok') + ' · ' + esc(t.id || '') + '</div>' +
        '</div>'
      );
    }).join('');
  }

  function showErr(msg) {
    const body = $('chatBody');
    if (!body) return;
    const div = document.createElement('div');
    div.className = 'chat-err';
    div.textContent = msg;
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
  }

  async function refreshTurns() {
    if (window.__chatTyping) return;
    try {
      const r = await fetch('/api/chat?limit=40');
      if (!r.ok) {
        showErr('GET /api/chat HTTP ' + r.status + ' — dashboard may be on old code. Restart host.');
        return;
      }
      const d = await r.json();
      if (d.error && !d.turns) {
        showErr('chat API: ' + d.error);
      }
      const turns = d.turns || [];
      const n = (d.summary && d.summary.turns_n != null) ? d.summary.turns_n : turns.length;
      const count = $('chatCount');
      if (count) count.textContent = n + ' turns';
      const body = $('chatBody');
      if (body) {
        body.innerHTML = renderTurns(turns);
        body.scrollTop = body.scrollHeight;
      }
      const kpi = $('kChatVal');
      if (kpi) kpi.textContent = n + 't';
    } catch (e) {
      showErr('chat fetch failed: ' + e + ' — is the host dashboard up?');
    }
  }

  async function sendChat(preset) {
    const input = $('chatInput');
    const btn = $('chatSend');
    const text = (preset != null ? String(preset) : (input && input.value) || '').trim();
    if (!text) return;
    if (btn) btn.disabled = true;
    window.__chatTyping = true;
    const body = $('chatBody');
    if (body) {
      const tip = document.createElement('div');
      tip.className = 'typing';
      tip.id = 'chatTyping';
      tip.textContent = 'ETHER is thinking…';
      body.appendChild(tip);
      body.scrollTop = body.scrollHeight;
    }
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, orchestrate: true }),
      });
      let d = {};
      try { d = await r.json(); } catch (_) { d = { error: 'non-JSON response HTTP ' + r.status }; }
      if (!r.ok || (!(d.ok || d.turn || d.envelope))) {
        showErr('chat failed: ' + (d.error || ('HTTP ' + r.status)));
      } else if (preset == null && input) {
        input.value = '';
      }
      // optimistic: if turn returned, show immediately
      if (d.turn && d.turn.reply && body) {
        const t = d.turn;
        const ch = String(t.channel || 'local').toLowerCase();
        body.innerHTML +=
          '<div class="chat-msg user"><span class="from">you</span><div class="text">' + esc(text) + '</div></div>' +
          '<div class="chat-msg agent"><span class="from">ETHER</span><span class="channel ' + esc(ch) + '">' + esc(ch) + '</span>' +
          '<div class="text">' + esc(t.reply) + '</div></div>';
        body.scrollTop = body.scrollHeight;
      }
    } catch (e) {
      showErr('chat error: ' + e + ' — restart host if dashboard is down');
    } finally {
      window.__chatTyping = false;
      const tip = document.getElementById('chatTyping');
      if (tip) tip.remove();
      if (btn) btn.disabled = false;
      await refreshTurns();
      if (input) input.focus();
    }
  }

  async function clearChat() {
    if (!window.confirm('Clear chat session? Archives bus messages and removes turns from the UI.')) return;
    try {
      const r = await fetch('/api/chat/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keep_archive: true }),
      });
      let d = {};
      try { d = await r.json(); } catch (_) { d = { error: 'HTTP ' + r.status }; }
      if (!r.ok || !d.ok) {
        showErr('clear failed: ' + (d.error || ('HTTP ' + r.status)) + ' — pull latest + restart host');
      }
      await refreshTurns();
    } catch (e) {
      showErr('clear error: ' + e);
    }
  }

  function wire() {
    ensureStyles();
    enhanceShell();
    refreshTurns();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
  setInterval(enhanceShell, 2500);
  setInterval(refreshTurns, 2500);
})();
