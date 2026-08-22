/** ETHER Chat UX v0.7.3 — instant Clear, optimistic send, fast poll.
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

  window.__etherChannel = window.__etherChannel || 'auto';
  window.__chatPending = false;

  function ensureStyles() {
    if (document.getElementById('ether-chat-ux-css')) return;
    const st = document.createElement('style');
    st.id = 'ether-chat-ux-css';
    st.textContent = [
      '.chat-header .chat-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}',
      '.btn-clear{background:#2a1515;border:1px solid #5a3030;color:#ff5c5c;border-radius:5px;padding:4px 10px;font-size:10px;cursor:pointer;font-weight:600;text-transform:uppercase}',
      '.btn-clear:hover{background:#3a1a1a}',
      '.chan-toggle{display:inline-flex;border:1px solid #1c2836;border-radius:5px;overflow:hidden}',
      '.chan-toggle button{background:#0b1017;border:none;color:#7a8796;padding:4px 8px;font-size:10px;cursor:pointer;text-transform:uppercase;font-weight:600}',
      '.chan-toggle button.on{background:#16324a;color:#4cc9f0}',
      '.chan-toggle button.on.grok{background:#2a1a2a;color:#9b8cff}',
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
      '.chat-err{color:#ff5c5c;font-size:12px;padding:8px;border:1px solid #5a3030;border-radius:6px;margin:6px 0;background:#1a0f0f}',
      '.pending-banner{background:#1a1520;border:1px solid #3a2a5a;color:#9b8cff;padding:6px 10px;font-size:11px;margin-bottom:6px;border-radius:6px}'
    ].join('');
    document.head.appendChild(st);
  }

  function setChannel(ch) {
    window.__etherChannel = ch;
    document.querySelectorAll('.chan-toggle button').forEach(function (b) {
      b.classList.toggle('on', b.dataset.ch === ch);
      b.classList.toggle('grok', b.dataset.ch === 'grok' && ch === 'grok');
    });
  }

  function enhanceShell() {
    const shell = document.querySelector('.chat-shell');
    if (!shell) return;
    if (shell.dataset.ux !== '1') {
      shell.dataset.ux = '1';
      const header = shell.querySelector('.chat-header');
      if (header) {
        header.innerHTML =
          '<span>ETHER agent · low-latency</span>' +
          '<div class="chat-actions">' +
          '<div class="chan-toggle" id="chanToggle">' +
          '<button type="button" data-ch="auto">Auto</button>' +
          '<button type="button" data-ch="local">Local</button>' +
          '<button type="button" data-ch="grok">Grok</button>' +
          '</div>' +
          '<span id="chatCount" style="font-family:Consolas,monospace;color:#4cc9f0">0 turns</span>' +
          '<button type="button" class="btn-clear" id="chatClear" title="Clear now">Clear</button>' +
          '</div>';
      }
      const messages = shell.querySelector('.chat-messages');
      if (messages && !shell.querySelector('.chat-chips')) {
        const chips = document.createElement('div');
        chips.className = 'chat-chips';
        chips.id = 'chatChips';
        chips.innerHTML =
          '<button type="button" class="chip" data-msg="status" data-ch="status">status</button>' +
          '<button type="button" class="chip" data-msg="git status" data-ch="git">git status</button>' +
          '<button type="button" class="chip" data-msg="rates" data-ch="status">rates</button>' +
          '<button type="button" class="chip" data-msg="doctor" data-ch="status">doctor</button>' +
          '<button type="button" class="chip" data-msg="hello from ETHER — ack please" data-ch="grok">→ Grok</button>';
        messages.parentNode.insertBefore(chips, messages);
      }
      const input = $('chatInput');
      if (input) input.placeholder = 'Message ETHER — Grok channel for this window';
      setChannel(window.__etherChannel || 'auto');
    }
    const clearBtn = $('chatClear');
    if (clearBtn && !clearBtn.dataset.bound) {
      clearBtn.dataset.bound = '1';
      clearBtn.addEventListener('click', clearChat);
    }
    document.querySelectorAll('#chanToggle button').forEach(function (b) {
      if (b.dataset.bound) return;
      b.dataset.bound = '1';
      b.addEventListener('click', function () { setChannel(b.dataset.ch); });
    });
    document.querySelectorAll('#chatChips .chip').forEach(function (chip) {
      if (chip.dataset.bound) return;
      chip.dataset.bound = '1';
      chip.addEventListener('click', function () {
        const ch = chip.getAttribute('data-ch');
        if (ch === 'grok') setChannel('grok');
        sendChat(chip.getAttribute('data-msg'), ch === 'grok' ? 'grok' : (ch === 'git' || ch === 'status' ? ch : null));
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

  function renderTurns(turns, pending) {
    let html = '';
    window.__chatPending = !!(pending && pending.status === 'awaiting_grok');
    if (window.__chatPending) {
      html += '<div class="pending-banner">⏳ Awaiting Grok · bus push is async (~1–3s)</div>';
    }
    if (!turns || !turns.length) {
      return html + '<div class="chat-empty">Empty — Clear is instant. Channel <b>Grok</b> reaches this window.</div>';
    }
    html += turns.slice().reverse().map(function (t) {
      const ts = (t.ts || '').toString();
      const clock = ts.indexOf('T') >= 0 ? ts.slice(11, 19) : ts.slice(0, 8);
      const ch = String(t.channel || t.intent || 'local').toLowerCase();
      return (
        '<div class="chat-msg user"><span class="from">you</span><div class="text">' + esc(t.message || '') +
        '</div><div class="ts">' + esc(clock) + '</div></div>' +
        '<div class="chat-msg agent"><span class="from">ETHER</span><span class="channel ' + esc(ch) + '">' + esc(ch) +
        '</span><div class="text">' + esc(t.reply || '(no reply)') + '</div><div class="ts">' +
        esc(clock) + ' · ' + (t.ok === false ? 'FAIL' : 'ok') + '</div></div>'
      );
    }).join('');
    return html;
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
      if (!r.ok) return;
      const d = await r.json();
      const turns = d.turns || [];
      const pending = d.pending_grok || (d.summary && d.summary.pending_grok) || null;
      const n = (d.summary && d.summary.turns_n != null) ? d.summary.turns_n : turns.length;
      const count = $('chatCount');
      if (count) count.textContent = n + ' turns';
      const body = $('chatBody');
      if (body) {
        body.innerHTML = renderTurns(turns, pending);
        body.scrollTop = body.scrollHeight;
      }
      const kpi = $('kChatVal');
      if (kpi) kpi.textContent = n + 't';
    } catch (_) {}
  }

  async function sendChat(preset, forceCh) {
    const input = $('chatInput');
    const btn = $('chatSend');
    const text = (preset != null ? String(preset) : (input && input.value) || '').trim();
    if (!text) return;
    if (btn) btn.disabled = true;
    window.__chatTyping = true;
    // Optimistic user bubble immediately
    const body = $('chatBody');
    if (body) {
      body.innerHTML += '<div class="chat-msg user"><span class="from">you</span><div class="text">' +
        esc(text) + '</div></div><div class="typing" id="chatTyping">ETHER…</div>';
      body.scrollTop = body.scrollHeight;
    }
    if (preset == null && input) input.value = '';
    const channel = forceCh || window.__etherChannel || 'auto';
    const payload = { message: text, orchestrate: true };
    if (channel === 'grok') payload.force_channel = 'grok';
    else if (channel === 'local') payload.force_channel = 'local';
    else if (channel === 'git') payload.force_channel = 'git';
    else if (channel === 'status') payload.force_channel = 'status';
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      let d = {};
      try { d = await r.json(); } catch (_) { d = { error: 'HTTP ' + r.status }; }
      if (!r.ok || (!(d.ok || d.turn || d.envelope))) {
        showErr('chat failed: ' + (d.error || r.status));
      } else if (d.turn && d.turn.reply && body) {
        const tip = document.getElementById('chatTyping');
        if (tip) tip.remove();
        const t = d.turn;
        const ch = String(t.channel || 'local').toLowerCase();
        body.innerHTML += '<div class="chat-msg agent"><span class="from">ETHER</span><span class="channel ' +
          esc(ch) + '">' + esc(ch) + '</span><div class="text">' + esc(t.reply) + '</div></div>';
        body.scrollTop = body.scrollHeight;
      }
    } catch (e) {
      showErr('chat error: ' + e);
    } finally {
      window.__chatTyping = false;
      const tip = document.getElementById('chatTyping');
      if (tip) tip.remove();
      if (btn) btn.disabled = false;
      refreshTurns();
      if (input) input.focus();
    }
  }

  async function clearChat() {
    // Instant UI wipe — no confirm
    const body = $('chatBody');
    if (body) body.innerHTML = '<div class="chat-empty">Cleared.</div>';
    const count = $('chatCount');
    if (count) count.textContent = '0 turns';
    const kpi = $('kChatVal');
    if (kpi) kpi.textContent = '0t';
    // Fire-and-forget server clear
    fetch('/api/chat/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keep_archive: true }),
    }).catch(function () {});
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
  setInterval(enhanceShell, 3000);
  // 1s poll when awaiting Grok, else 2s
  setInterval(function () {
    refreshTurns();
  }, 1000);
})();
