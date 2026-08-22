/** ETHER Chat UX v0.8.0 — professional, stable, role-clear conversation panel.
 *
 * Design goals:
 *  - No twitch: only re-render when turn fingerprint changes
 *  - Clear speakers: YOU (operator) vs ETHER (agent) vs GROK path
 *  - Turn cards group request + reply
 *  - Calm poll (4s idle); no scroll-jacking
 */
(function () {
  'use strict';

  const $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  var state = {
    channel: 'auto',
    fingerprint: '',
    typing: false,
    nearBottom: true,
    lastCount: 0,
  };

  function ensureStyles() {
    if (document.getElementById('ether-chat-ux-css')) return;
    var st = document.createElement('style');
    st.id = 'ether-chat-ux-css';
    st.textContent = [
      /* shell */
      '.chat-shell{display:flex;flex-direction:column;height:100%;min-height:0;background:#0b0f14;}',
      '.chat-shell .chat-header{',
      'display:flex;align-items:center;justify-content:space-between;gap:12px;',
      'padding:10px 14px;border-bottom:1px solid #1a2330;background:#0e141c;flex-shrink:0;',
      '}',
      '.chat-shell .chat-header .title{font-size:12px;font-weight:600;letter-spacing:0.04em;',
      'text-transform:uppercase;color:#8b9bb0;}',
      '.chat-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}',

      /* channel segmented control */
      '.chan-toggle{display:inline-flex;border:1px solid #243044;border-radius:6px;overflow:hidden;background:#0a1018;}',
      '.chan-toggle button{',
      'background:transparent;border:none;color:#6b7a8d;padding:5px 10px;font-size:11px;',
      'cursor:pointer;font-weight:600;letter-spacing:0.02em;',
      '}',
      '.chan-toggle button:hover{color:#a8b8c8;background:#121a24;}',
      '.chan-toggle button.on{background:#1a2740;color:#5eb8e8;}',
      '.chan-toggle button.on[data-ch="grok"]{background:#241a30;color:#b794f6;}',
      '.chan-toggle button.on[data-ch="local"]{background:#14241c;color:#4ade80;}',

      '.chat-meta{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#5eb8e8;}',
      '.btn-clear{',
      'background:transparent;border:1px solid #3d2a2a;color:#e07070;border-radius:6px;',
      'padding:5px 10px;font-size:11px;cursor:pointer;font-weight:600;',
      '}',
      '.btn-clear:hover{background:#1a1010;border-color:#5a3030;}',

      /* shortcuts */
      '.chat-shortcuts{',
      'display:flex;flex-wrap:wrap;gap:6px;padding:8px 14px;',
      'border-bottom:1px solid #1a2330;background:#0c1219;flex-shrink:0;',
      '}',
      '.chat-shortcuts .label{',
      'font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:#4a5568;',
      'align-self:center;margin-right:4px;',
      '}',
      '.chip{',
      'background:#121a24;border:1px solid #243044;color:#8b9bb0;border-radius:6px;',
      'padding:4px 10px;font-size:11px;cursor:pointer;font-family:ui-monospace,Consolas,monospace;',
      '}',
      '.chip:hover{border-color:#3a6a8a;color:#5eb8e8;background:#152030;}',
      '.chip.grok{border-color:#3a2a50;color:#b794f6;}',
      '.chip.grok:hover{background:#1a1428;border-color:#5a3a80;}',

      /* message stream */
      '.chat-messages{',
      'flex:1;overflow-y:auto;padding:16px 14px;min-height:0;',
      'scroll-behavior:auto;',
      '}',
      '.chat-empty{',
      'color:#5a6a7c;padding:48px 20px;text-align:center;font-size:13px;line-height:1.6;',
      '}',
      '.chat-empty strong{color:#8b9bb0;}',

      /* turn card — one request + one reply */
      '.turn-card{',
      'margin:0 0 14px 0;border:1px solid #1a2330;border-radius:10px;',
      'background:#0e141c;overflow:hidden;',
      '}',
      '.turn-row{padding:12px 14px;}',
      '.turn-row + .turn-row{border-top:1px solid #151c28;}',
      '.turn-row.operator{background:#0c1018;}',
      '.turn-row.agent{background:#0a1210;}',
      '.turn-row.agent.ch-grok{background:#100e18;}',
      '.turn-row.agent.ch-status,.turn-row.agent.ch-git{background:#0c1218;}',

      '.turn-meta{',
      'display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;',
      '}',
      '.speaker{',
      'font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;',
      '}',
      '.speaker.you{color:#a78bfa;}',
      '.speaker.ether{color:#4ade80;}',
      '.badge{',
      'font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.03em;',
      'padding:2px 7px;border-radius:4px;border:1px solid transparent;',
      '}',
      '.badge.local{background:#0d2a1a;color:#4ade80;border-color:#1a4a30;}',
      '.badge.git{background:#0d1e2a;color:#5eb8e8;border-color:#1a3a5a;}',
      '.badge.status{background:#2a2410;color:#f0b429;border-color:#4a3a10;}',
      '.badge.grok{background:#1e1430;color:#b794f6;border-color:#3a2a5a;}',
      '.badge.job{background:#2a1808;color:#f0a050;border-color:#4a3010;}',
      '.badge.ok{background:#0d2a1a;color:#4ade80;}',
      '.badge.fail{background:#2a1010;color:#f07070;}',
      '.turn-time{',
      'margin-left:auto;font-family:ui-monospace,Consolas,monospace;',
      'font-size:10px;color:#4a5568;',
      '}',

      '.turn-body{',
      'font-size:13px;line-height:1.55;color:#d0d8e0;white-space:pre-wrap;word-break:break-word;',
      '}',
      '.turn-row.operator .turn-body{color:#e8e4f8;}',

      '.pending-banner{',
      'margin:0 0 12px 0;padding:10px 12px;border-radius:8px;',
      'background:#14101c;border:1px solid #2a2040;color:#b794f6;font-size:12px;',
      '}',
      '.typing-row{',
      'padding:10px 14px;color:#6b7a8d;font-size:12px;font-style:italic;',
      'border:1px dashed #243044;border-radius:8px;margin-bottom:12px;',
      '}',
      '.chat-err{',
      'color:#f07070;font-size:12px;padding:10px 12px;border:1px solid #4a2020;',
      'border-radius:8px;margin:0 0 12px 0;background:#1a1010;',
      '}',

      /* compose */
      '.chat-compose{',
      'display:flex;gap:8px;padding:12px 14px;border-top:1px solid #1a2330;',
      'background:#0e141c;flex-shrink:0;align-items:center;',
      '}',
      '.chat-compose input{',
      'flex:1;background:#0a1018;border:1px solid #243044;border-radius:8px;',
      'padding:10px 12px;color:#e0e6ec;font-size:13px;outline:none;',
      '}',
      '.chat-compose input:focus{border-color:#3a6a8a;}',
      '.chat-compose input::placeholder{color:#4a5568;}',
      '.chat-compose button#chatSend{',
      'background:#1a3a5a;border:1px solid #2a5a8a;color:#8ec8f0;border-radius:8px;',
      'padding:10px 16px;font-size:12px;font-weight:600;cursor:pointer;',
      '}',
      '.chat-compose button#chatSend:hover{background:#204868;}',
      '.chat-compose button#chatSend:disabled{opacity:0.5;cursor:not-allowed;}',
    ].join('');
    document.head.appendChild(st);
  }

  function setChannel(ch) {
    state.channel = ch || 'auto';
    document.querySelectorAll('#chanToggle button').forEach(function (b) {
      var on = b.getAttribute('data-ch') === state.channel;
      b.classList.toggle('on', on);
    });
  }

  function enhanceShell() {
    var shell = document.querySelector('.chat-shell');
    if (!shell) return;

    if (shell.dataset.ux !== '2') {
      shell.dataset.ux = '2';

      var header = shell.querySelector('.chat-header');
      if (header) {
        header.innerHTML =
          '<div class="title">Conversation</div>' +
          '<div class="chat-actions">' +
          '<div class="chan-toggle" id="chanToggle" title="Where the message is routed">' +
          '<button type="button" data-ch="auto">Auto</button>' +
          '<button type="button" data-ch="local">Local</button>' +
          '<button type="button" data-ch="grok">Grok</button>' +
          '</div>' +
          '<span class="chat-meta" id="chatCount">0 turns</span>' +
          '<button type="button" class="btn-clear" id="chatClear">Clear</button>' +
          '</div>';
      }

      var messages = shell.querySelector('.chat-messages');
      if (messages && !shell.querySelector('.chat-shortcuts')) {
        var bar = document.createElement('div');
        bar.className = 'chat-shortcuts';
        bar.id = 'chatChips';
        bar.innerHTML =
          '<span class="label">Tools</span>' +
          '<button type="button" class="chip" data-msg="status" data-ch="status">Status</button>' +
          '<button type="button" class="chip" data-msg="git status" data-ch="git">Git status</button>' +
          '<button type="button" class="chip" data-msg="rates" data-ch="status">Rates</button>' +
          '<button type="button" class="chip" data-msg="doctor" data-ch="status">Doctor</button>' +
          '<button type="button" class="chip grok" data-msg="Please acknowledge this message from the ETHER dashboard." data-ch="grok">Message Grok</button>';
        messages.parentNode.insertBefore(bar, messages);
      }

      var input = $('chatInput');
      if (input) {
        input.placeholder = 'Write a message…  Enter to send';
      }
      setChannel(state.channel);
    }

    bindOnce();
  }

  function bindOnce() {
    var clearBtn = $('chatClear');
    if (clearBtn && !clearBtn.dataset.bound) {
      clearBtn.dataset.bound = '1';
      clearBtn.addEventListener('click', clearChat);
    }

    document.querySelectorAll('#chanToggle button').forEach(function (b) {
      if (b.dataset.bound) return;
      b.dataset.bound = '1';
      b.addEventListener('click', function () {
        setChannel(b.getAttribute('data-ch'));
      });
    });

    document.querySelectorAll('#chatChips .chip').forEach(function (chip) {
      if (chip.dataset.bound) return;
      chip.dataset.bound = '1';
      chip.addEventListener('click', function () {
        var ch = chip.getAttribute('data-ch');
        if (ch === 'grok') setChannel('grok');
        var force = (ch === 'grok') ? 'grok' : (ch === 'git' || ch === 'status' ? ch : null);
        sendChat(chip.getAttribute('data-msg'), force);
      });
    });

    var btn = $('chatSend');
    if (btn && !btn.dataset.uxBound) {
      btn.dataset.uxBound = '1';
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopImmediatePropagation();
        sendChat();
      }, true);
    }

    var input = $('chatInput');
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

    var body = $('chatBody');
    if (body && !body.dataset.scrollBound) {
      body.dataset.scrollBound = '1';
      body.addEventListener('scroll', function () {
        var gap = body.scrollHeight - body.scrollTop - body.clientHeight;
        state.nearBottom = gap < 80;
      });
    }
  }

  function clockOf(ts) {
    ts = (ts || '').toString();
    if (ts.indexOf('T') >= 0) return ts.slice(11, 19);
    return ts.slice(0, 8) || '—';
  }

  function channelLabel(ch) {
    ch = String(ch || 'local').toLowerCase();
    if (ch === 'escalate_grok') return 'grok';
    if (ch === 'local_llm') return 'local';
    return ch;
  }

  function fingerprint(turns, pending) {
    var ids = (turns || []).map(function (t) {
      return (t.id || '') + ':' + (t.ok === false ? '0' : '1') + ':' + String(t.reply || '').length;
    }).join('|');
    var p = pending && pending.status ? pending.status + (pending.envelope_id || '') : '';
    return ids + '#' + p;
  }

  function renderTurns(turns, pending) {
    var html = '';

    if (pending && pending.status === 'awaiting_grok') {
      html +=
        '<div class="pending-banner">Waiting for Grok · message is on the bus' +
        (pending.text ? ' · “' + esc(String(pending.text).slice(0, 80)) + '”' : '') +
        '</div>';
    }

    if (!turns || !turns.length) {
      html +=
        '<div class="chat-empty">' +
        '<strong>No messages yet</strong><br>' +
        'Use a tool shortcut above, or type below.<br>' +
        'Channel <strong>Local</strong> = Ollama on this machine.<br>' +
        'Channel <strong>Grok</strong> = this remote chat window.' +
        '</div>';
      return html;
    }

    // API returns newest-first; show oldest at top (conversation order)
    var ordered = turns.slice().reverse();

    ordered.forEach(function (t) {
      var ch = channelLabel(t.channel || t.intent);
      var okBadge = t.ok === false
        ? '<span class="badge fail">fail</span>'
        : '<span class="badge ok">ok</span>';
      var time = clockOf(t.ts);

      html += '<article class="turn-card" data-turn-id="' + esc(t.id || '') + '">';

      // Operator
      html +=
        '<div class="turn-row operator">' +
        '<div class="turn-meta">' +
        '<span class="speaker you">You</span>' +
        '<span class="turn-time">' + esc(time) + '</span>' +
        '</div>' +
        '<div class="turn-body">' + esc(t.message || '') + '</div>' +
        '</div>';

      // Agent
      html +=
        '<div class="turn-row agent ch-' + esc(ch) + '">' +
        '<div class="turn-meta">' +
        '<span class="speaker ether">ETHER</span>' +
        '<span class="badge ' + esc(ch) + '">' + esc(ch) + '</span>' +
        okBadge +
        '<span class="turn-time">' + esc(time) + '</span>' +
        '</div>' +
        '<div class="turn-body">' + esc(t.reply || '(no reply)') + '</div>' +
        '</div>';

      html += '</article>';
    });

    return html;
  }

  function showErr(msg) {
    var body = $('chatBody');
    if (!body) return;
    var div = document.createElement('div');
    div.className = 'chat-err';
    div.textContent = msg;
    body.appendChild(div);
    if (state.nearBottom) body.scrollTop = body.scrollHeight;
  }

  async function refreshTurns(force) {
    if (state.typing && !force) return;
    try {
      var r = await fetch('/api/chat?limit=40');
      if (!r.ok) return;
      var d = await r.json();
      var turns = d.turns || [];
      var pending = d.pending_grok || (d.summary && d.summary.pending_grok) || null;
      var fp = fingerprint(turns, pending);

      // Stability: skip DOM rewrite if nothing meaningful changed
      if (!force && fp === state.fingerprint) return;
      state.fingerprint = fp;

      var n = (d.summary && d.summary.turns_n != null) ? d.summary.turns_n : turns.length;
      state.lastCount = n;
      var count = $('chatCount');
      if (count) count.textContent = n + (n === 1 ? ' turn' : ' turns');

      var body = $('chatBody');
      if (body) {
        var wasNear = state.nearBottom;
        body.innerHTML = renderTurns(turns, pending);
        if (wasNear) body.scrollTop = body.scrollHeight;
      }

      var kpi = $('kChatVal');
      if (kpi) kpi.textContent = n + 't';
    } catch (_) {}
  }

  async function sendChat(preset, forceCh) {
    var input = $('chatInput');
    var btn = $('chatSend');
    var text = (preset != null ? String(preset) : (input && input.value) || '').trim();
    if (!text) return;

    if (btn) btn.disabled = true;
    state.typing = true;

    var body = $('chatBody');
    if (body) {
      // Remove empty state if present
      var empty = body.querySelector('.chat-empty');
      if (empty) empty.remove();

      var tip = document.createElement('div');
      tip.className = 'typing-row';
      tip.id = 'chatTyping';
      tip.textContent = 'ETHER is working…';
      body.appendChild(tip);
      body.scrollTop = body.scrollHeight;
      state.nearBottom = true;
    }

    if (preset == null && input) input.value = '';

    var channel = forceCh || state.channel || 'auto';
    var payload = { message: text, orchestrate: true };
    if (channel === 'grok') payload.force_channel = 'grok';
    else if (channel === 'local') payload.force_channel = 'local';
    else if (channel === 'git') payload.force_channel = 'git';
    else if (channel === 'status') payload.force_channel = 'status';

    try {
      var r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      var d = {};
      try { d = await r.json(); } catch (_) { d = { error: 'HTTP ' + r.status }; }
      if (!r.ok || (!(d.ok || d.turn || d.envelope))) {
        showErr('Send failed: ' + (d.error || ('HTTP ' + r.status)));
      }
    } catch (e) {
      showErr('Send failed: ' + e);
    } finally {
      state.typing = false;
      var tip = document.getElementById('chatTyping');
      if (tip) tip.remove();
      if (btn) btn.disabled = false;
      state.fingerprint = ''; // force one clean re-render
      await refreshTurns(true);
      if (input) input.focus();
    }
  }

  function clearChat() {
    state.fingerprint = 'cleared';
    var body = $('chatBody');
    if (body) {
      body.innerHTML =
        '<div class="chat-empty"><strong>Conversation cleared</strong><br>Ready for the next message.</div>';
    }
    var count = $('chatCount');
    if (count) count.textContent = '0 turns';
    var kpi = $('kChatVal');
    if (kpi) kpi.textContent = '0t';
    state.lastCount = 0;

    fetch('/api/chat/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keep_archive: true }),
    }).catch(function () {});
  }

  function wire() {
    ensureStyles();
    enhanceShell();
    refreshTurns(true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Calm: rebuild shell rarely; poll slowly; skip identical fingerprints
  setInterval(enhanceShell, 8000);
  setInterval(function () {
    refreshTurns(false);
  }, 4000);
})();
