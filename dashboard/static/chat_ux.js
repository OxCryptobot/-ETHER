/** ETHER Chat UX v0.9.0 — Dual-pane Input / Output.
 *
 * Left  = INPUT  (operator → Local / Grok / Git / Auto)
 * Right = OUTPUT (status, ops, jobs, Ollama/Grok replies — realtime)
 *
 * Goals: no twitch, clear roles, channel control, live system feed.
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  var state = {
    channel: 'auto',
    fingerprint: '',
    opsFingerprint: '',
    typing: false,
    nearBottomIn: true,
    nearBottomOut: true,
  };

  function ensureStyles() {
    if (document.getElementById('ether-chat-ux-css')) return;
    var st = document.createElement('style');
    st.id = 'ether-chat-ux-css';
    st.textContent = [
      '.chat-shell{display:flex;flex-direction:column;height:100%;min-height:0;background:#0b0f14;}',
      '.chat-shell .chat-header{',
      'display:flex;align-items:center;justify-content:space-between;gap:12px;',
      'padding:10px 14px;border-bottom:1px solid #1a2330;background:#0e141c;flex-shrink:0;',
      '}',
      '.chat-shell .chat-header .title{font-size:12px;font-weight:600;letter-spacing:0.04em;',
      'text-transform:uppercase;color:#8b9bb0;}',
      '.chat-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}',
      '.chan-toggle{display:inline-flex;border:1px solid #243044;border-radius:6px;overflow:hidden;background:#0a1018;}',
      '.chan-toggle button{background:transparent;border:none;color:#6b7a8d;padding:5px 10px;font-size:11px;',
      'cursor:pointer;font-weight:600;letter-spacing:0.02em;}',
      '.chan-toggle button:hover{color:#a8b8c8;background:#121a24;}',
      '.chan-toggle button.on{background:#1a2740;color:#5eb8e8;}',
      '.chan-toggle button.on[data-ch="grok"]{background:#241a30;color:#b794f6;}',
      '.chan-toggle button.on[data-ch="local"]{background:#14241c;color:#4ade80;}',
      '.chan-toggle button.on[data-ch="git"]{background:#0d1e2a;color:#5eb8e8;}',
      '.chat-meta{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#5eb8e8;}',
      '.btn-clear{background:transparent;border:1px solid #3d2a2a;color:#e07070;border-radius:6px;',
      'padding:5px 10px;font-size:11px;cursor:pointer;font-weight:600;}',
      '.btn-clear:hover{background:#1a1010;border-color:#5a3030;}',

      /* dual panes */
      '.chat-dual{display:grid;grid-template-columns:1fr 1fr;gap:0;flex:1;min-height:0;overflow:hidden;}',
      '@media (max-width:900px){.chat-dual{grid-template-columns:1fr;grid-template-rows:1fr 1fr;}}',
      '.chat-pane{display:flex;flex-direction:column;min-height:0;overflow:hidden;border-right:1px solid #1a2330;}',
      '.chat-pane:last-child{border-right:none;border-left:1px solid #1a2330;}',
      '.pane-label{',
      'padding:6px 12px;font-size:10px;text-transform:uppercase;letter-spacing:0.07em;',
      'color:#6b7a8d;background:#0c1219;border-bottom:1px solid #1a2330;flex-shrink:0;',
      'display:flex;justify-content:space-between;align-items:center;',
      '}',
      '.pane-label .tag{font-family:ui-monospace,Consolas,monospace;color:#5eb8e8;font-size:10px;}',
      '.pane-label.out .tag{color:#4ade80;}',
      '.pane-body{flex:1;overflow-y:auto;padding:12px;min-height:0;}',

      '.chat-shortcuts{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px;',
      'border-bottom:1px solid #1a2330;background:#0c1219;flex-shrink:0;}',
      '.chat-shortcuts .label{font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:#4a5568;',
      'align-self:center;margin-right:4px;}',
      '.chip{background:#121a24;border:1px solid #243044;color:#8b9bb0;border-radius:6px;',
      'padding:4px 10px;font-size:11px;cursor:pointer;font-family:ui-monospace,Consolas,monospace;}',
      '.chip:hover{border-color:#3a6a8a;color:#5eb8e8;background:#152030;}',
      '.chip.grok{border-color:#3a2a50;color:#b794f6;}',
      '.chip.grok:hover{background:#1a1428;border-color:#5a3a80;}',

      '.chat-empty{color:#5a6a7c;padding:32px 16px;text-align:center;font-size:13px;line-height:1.6;}',
      '.chat-empty strong{color:#8b9bb0;}',

      /* input messages */
      '.in-msg{margin:0 0 10px 0;padding:10px 12px;border-radius:8px;',
      'background:#0e141c;border:1px solid #1a2330;border-left:3px solid #a78bfa;}',
      '.in-msg .meta{display:flex;gap:8px;align-items:center;margin-bottom:4px;font-size:10px;}',
      '.in-msg .who{color:#a78bfa;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;}',
      '.in-msg .when{margin-left:auto;color:#4a5568;font-family:ui-monospace,Consolas,monospace;}',
      '.in-msg .body{font-size:13px;line-height:1.5;color:#e8e4f8;white-space:pre-wrap;word-break:break-word;}',

      /* output stream */
      '.out-msg{margin:0 0 8px 0;padding:8px 10px;border-radius:6px;',
      'background:#0a1210;border:1px solid #1a2830;font-size:12px;}',
      '.out-msg.status{border-left:3px solid #f0b429;}',
      '.out-msg.job{border-left:3px solid #f0a050;}',
      '.out-msg.local{border-left:3px solid #4ade80;}',
      '.out-msg.grok{border-left:3px solid #b794f6;background:#100e18;}',
      '.out-msg.git{border-left:3px solid #5eb8e8;}',
      '.out-msg.ops{border-left:3px solid #5eb8e8;background:#0c1218;}',
      '.out-msg .meta{display:flex;gap:6px;align-items:center;margin-bottom:3px;flex-wrap:wrap;}',
      '.out-msg .kind{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:#8b9bb0;}',
      '.out-msg .badge{font-size:9px;padding:1px 6px;border-radius:3px;border:1px solid transparent;}',
      '.out-msg .badge.local{background:#0d2a1a;color:#4ade80;border-color:#1a4a30;}',
      '.out-msg .badge.grok{background:#1e1430;color:#b794f6;border-color:#3a2a5a;}',
      '.out-msg .badge.status{background:#2a2410;color:#f0b429;border-color:#4a3a10;}',
      '.out-msg .badge.job{background:#2a1808;color:#f0a050;border-color:#4a3010;}',
      '.out-msg .badge.git{background:#0d1e2a;color:#5eb8e8;border-color:#1a3a5a;}',
      '.out-msg .badge.ops{background:#0d1e2a;color:#5eb8e8;border-color:#1a3a5a;}',
      '.out-msg .when{margin-left:auto;color:#4a5568;font-family:ui-monospace,Consolas,monospace;font-size:10px;}',
      '.out-msg .body{color:#d0d8e0;white-space:pre-wrap;word-break:break-word;line-height:1.45;}',

      '.pending-banner{margin:0 0 10px 0;padding:8px 10px;border-radius:6px;',
      'background:#14101c;border:1px solid #2a2040;color:#b794f6;font-size:12px;}',
      '.typing-row{padding:8px 10px;color:#6b7a8d;font-size:12px;font-style:italic;',
      'border:1px dashed #243044;border-radius:6px;margin-bottom:10px;}',
      '.chat-err{color:#f07070;font-size:12px;padding:8px 10px;border:1px solid #4a2020;',
      'border-radius:6px;margin:0 0 10px 0;background:#1a1010;}',

      '.chat-compose{display:flex;gap:8px;padding:12px 14px;border-top:1px solid #1a2330;',
      'background:#0e141c;flex-shrink:0;align-items:center;}',
      '.chat-compose input{flex:1;background:#0a1018;border:1px solid #243044;border-radius:8px;',
      'padding:10px 12px;color:#e0e6ec;font-size:13px;outline:none;}',
      '.chat-compose input:focus{border-color:#3a6a8a;}',
      '.chat-compose input::placeholder{color:#4a5568;}',
      '.chat-compose button#chatSend{background:#1a3a5a;border:1px solid #2a5a8a;color:#8ec8f0;border-radius:8px;',
      'padding:10px 16px;font-size:12px;font-weight:600;cursor:pointer;}',
      '.chat-compose button#chatSend:hover{background:#204868;}',
      '.chat-compose button#chatSend:disabled{opacity:0.5;cursor:not-allowed;}',
    ].join('');
    document.head.appendChild(st);
  }

  function setChannel(ch) {
    state.channel = ch || 'auto';
    document.querySelectorAll('#chanToggle button').forEach(function (b) {
      b.classList.toggle('on', b.getAttribute('data-ch') === state.channel);
    });
  }

  function enhanceShell() {
    var shell = document.querySelector('.chat-shell');
    if (!shell) return;

    if (shell.dataset.ux !== 'dual9') {
      shell.dataset.ux = 'dual9';

      var header = shell.querySelector('.chat-header');
      if (header) {
        header.innerHTML =
          '<div class="title">Dual Chat · Input ↔ Output</div>' +
          '<div class="chat-actions">' +
          '<div class="chan-toggle" id="chanToggle" title="Route for new messages">' +
          '<button type="button" data-ch="auto">Auto</button>' +
          '<button type="button" data-ch="local">Local</button>' +
          '<button type="button" data-ch="grok">Grok</button>' +
          '<button type="button" data-ch="git">Git</button>' +
          '</div>' +
          '<span class="chat-meta" id="chatCount">0 turns</span>' +
          '<button type="button" class="btn-clear" id="chatClear">Clear</button>' +
          '</div>';
      }

      // Replace single messages area with dual panes
      var oldBody = shell.querySelector('.chat-messages');
      var compose = shell.querySelector('.chat-compose');

      // Remove old shortcuts if present
      var oldChips = shell.querySelector('.chat-shortcuts');
      if (oldChips) oldChips.remove();

      var dual = document.createElement('div');
      dual.className = 'chat-dual';
      dual.id = 'chatDual';
      dual.innerHTML =
        '<div class="chat-pane" id="paneInput">' +
        '<div class="pane-label">Input · you → system <span class="tag" id="inCount">0</span></div>' +
        '<div class="chat-shortcuts" id="chatChips">' +
        '<span class="label">Quick</span>' +
        '<button type="button" class="chip" data-msg="status" data-ch="status">Status</button>' +
        '<button type="button" class="chip" data-msg="rates" data-ch="status">Rates</button>' +
        '<button type="button" class="chip" data-msg="doctor" data-ch="status">Doctor</button>' +
        '<button type="button" class="chip" data-msg="git status" data-ch="git">Git</button>' +
        '<button type="button" class="chip grok" data-msg="Please acknowledge from the ETHER dashboard." data-ch="grok">Grok</button>' +
        '</div>' +
        '<div class="pane-body" id="chatInputBody"></div>' +
        '</div>' +
        '<div class="chat-pane" id="paneOutput">' +
        '<div class="pane-label out">Output · status · ops · jobs · replies <span class="tag" id="outCount">0</span></div>' +
        '<div class="pane-body" id="chatOutputBody"></div>' +
        '</div>';

      if (oldBody) {
        oldBody.replaceWith(dual);
      } else if (compose) {
        shell.insertBefore(dual, compose);
      } else {
        shell.appendChild(dual);
      }

      // Ensure compose exists
      if (!compose) {
        compose = document.createElement('div');
        compose.className = 'chat-compose';
        compose.innerHTML =
          '<input id="chatInput" type="text" placeholder="Message (one hypothesis) — Enter to send" maxlength="2000" autocomplete="off" />' +
          '<button id="chatSend" type="button">Send</button>';
        shell.appendChild(compose);
      } else {
        var input = $('chatInput');
        if (input) input.placeholder = 'Message (one hypothesis) — Enter to send';
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
      b.addEventListener('click', function () { setChannel(b.getAttribute('data-ch')); });
    });

    document.querySelectorAll('#chatChips .chip').forEach(function (chip) {
      if (chip.dataset.bound) return;
      chip.dataset.bound = '1';
      chip.addEventListener('click', function () {
        var ch = chip.getAttribute('data-ch');
        if (ch === 'grok') setChannel('grok');
        else if (ch === 'git') setChannel('git');
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

    ['chatInputBody', 'chatOutputBody'].forEach(function (id) {
      var el = $(id);
      if (el && !el.dataset.scrollBound) {
        el.dataset.scrollBound = '1';
        el.addEventListener('scroll', function () {
          var gap = el.scrollHeight - el.scrollTop - el.clientHeight;
          if (id === 'chatInputBody') state.nearBottomIn = gap < 80;
          else state.nearBottomOut = gap < 80;
        });
      }
    });
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

  function fingerprint(turns, pending, host) {
    var ids = (turns || []).map(function (t) {
      return (t.id || '') + ':' + (t.ok === false ? '0' : '1') + ':' + String(t.reply || '').length;
    }).join('|');
    var p = pending && pending.status ? pending.status + (pending.envelope_id || '') : '';
    var h = host ? (host.phase || '') + (host.current_job || '') + (host.last_job || '') : '';
    return ids + '#' + p + '#' + h;
  }

  function renderInput(turns) {
    if (!turns || !turns.length) {
      return '<div class="chat-empty"><strong>Input empty</strong><br>Type below or use a quick action.<br>Channel selects Local / Grok / Git / Auto.</div>';
    }
    var ordered = turns.slice().reverse();
    var html = '';
    ordered.forEach(function (t) {
      html +=
        '<div class="in-msg" data-turn-id="' + esc(t.id || '') + '">' +
        '<div class="meta"><span class="who">You</span>' +
        '<span class="when">' + esc(clockOf(t.ts)) + '</span></div>' +
        '<div class="body">' + esc(t.message || '') + '</div></div>';
    });
    return html;
  }

  function renderOutput(turns, pending, hostSnap) {
    var html = '';

    if (pending && pending.status === 'awaiting_grok') {
      html +=
        '<div class="pending-banner">Waiting for Grok · on the bus' +
        (pending.text ? ' · “' + esc(String(pending.text).slice(0, 72)) + '”' : '') +
        '</div>';
    }

    // Live host ops line
    if (hostSnap) {
      var phase = hostSnap.phase || '—';
      var cur = hostSnap.current_job || hostSnap.last_job || '—';
      var ok = hostSnap.last_ok;
      var okS = ok === true ? 'PASS' : ok === false ? 'FAIL' : '—';
      html +=
        '<div class="out-msg ops">' +
        '<div class="meta"><span class="kind">OPS</span>' +
        '<span class="badge ops">live</span>' +
        '<span class="when">now</span></div>' +
        '<div class="body">phase=' + esc(phase) +
        ' · job=' + esc(String(cur)) +
        ' · last=' + esc(okS) + '</div></div>';
    }

    if (!turns || !turns.length) {
      if (!html) {
        html =
          '<div class="chat-empty"><strong>Output idle</strong><br>' +
          'Status, jobs, Local (Ollama) and Grok replies appear here in realtime.</div>';
      }
      return html;
    }

    var ordered = turns.slice().reverse();
    ordered.forEach(function (t) {
      var ch = channelLabel(t.channel || t.intent);
      var kind = ch === 'status' || ch === 'git' || ch === 'job' ? ch : (ch === 'grok' ? 'grok' : 'local');
      var badge = kind;
      html +=
        '<div class="out-msg ' + esc(kind) + '">' +
        '<div class="meta">' +
        '<span class="kind">ETHER</span>' +
        '<span class="badge ' + esc(badge) + '">' + esc(badge) + '</span>' +
        (t.ok === false ? '<span class="badge" style="background:#2a1010;color:#f07070">fail</span>' : '') +
        '<span class="when">' + esc(clockOf(t.ts)) + '</span></div>' +
        '<div class="body">' + esc(t.reply || '(no reply)') + '</div></div>';
    });
    return html;
  }

  function showErr(msg) {
    var body = $('chatOutputBody');
    if (!body) return;
    var div = document.createElement('div');
    div.className = 'chat-err';
    div.textContent = msg;
    body.appendChild(div);
    if (state.nearBottomOut) body.scrollTop = body.scrollHeight;
  }

  async function refresh(force) {
    if (state.typing && !force) return;
    try {
      var rChat = await fetch('/api/chat?limit=40');
      if (!rChat.ok) return;
      var d = await rChat.json();
      var turns = d.turns || [];
      var pending = d.pending_grok || (d.summary && d.summary.pending_grok) || null;

      var hostSnap = null;
      try {
        var rH = await fetch('/api/host-agent');
        if (rH.ok) {
          var hd = await rH.json();
          hostSnap = hd.status || {};
          if (hd.last_job) {
            hostSnap.last_job = hd.last_job.job_id || hostSnap.last_job;
            hostSnap.last_ok = hd.last_job.ok;
          }
        }
      } catch (_) {}

      var fp = fingerprint(turns, pending, hostSnap);
      if (!force && fp === state.fingerprint) return;
      state.fingerprint = fp;

      var n = (d.summary && d.summary.turns_n != null) ? d.summary.turns_n : turns.length;
      var count = $('chatCount');
      if (count) count.textContent = n + (n === 1 ? ' turn' : ' turns');
      var inC = $('inCount');
      if (inC) inC.textContent = String(turns.length);
      var outC = $('outCount');
      if (outC) outC.textContent = String(turns.length + (hostSnap ? 1 : 0));

      var inBody = $('chatInputBody');
      if (inBody) {
        var wasNear = state.nearBottomIn;
        inBody.innerHTML = renderInput(turns);
        if (wasNear) inBody.scrollTop = inBody.scrollHeight;
      }

      var outBody = $('chatOutputBody');
      if (outBody) {
        var wasNearO = state.nearBottomOut;
        outBody.innerHTML = renderOutput(turns, pending, hostSnap);
        if (wasNearO) outBody.scrollTop = outBody.scrollHeight;
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

    var outBody = $('chatOutputBody');
    if (outBody) {
      var tip = document.createElement('div');
      tip.className = 'typing-row';
      tip.id = 'chatTyping';
      tip.textContent = 'ETHER is working…';
      outBody.appendChild(tip);
      outBody.scrollTop = outBody.scrollHeight;
      state.nearBottomOut = true;
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
      state.fingerprint = '';
      await refresh(true);
      if (input) input.focus();
    }
  }

  function clearChat() {
    state.fingerprint = 'cleared';
    var inBody = $('chatInputBody');
    if (inBody) {
      inBody.innerHTML = '<div class="chat-empty"><strong>Input cleared</strong></div>';
    }
    var outBody = $('chatOutputBody');
    if (outBody) {
      outBody.innerHTML = '<div class="chat-empty"><strong>Output cleared</strong></div>';
    }
    var count = $('chatCount');
    if (count) count.textContent = '0 turns';
    var kpi = $('kChatVal');
    if (kpi) kpi.textContent = '0t';

    fetch('/api/chat/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keep_archive: true }),
    }).catch(function () {});
  }

  function wire() {
    ensureStyles();
    enhanceShell();
    refresh(true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  setInterval(enhanceShell, 8000);
  setInterval(function () { refresh(false); }, 2500);
})();
