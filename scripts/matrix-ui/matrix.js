
async function j(u,o){const r=await fetch(u,o); return r.json();}
async function probe(){
  const s = await j('/api/origin');
  document.getElementById('ollama').textContent = s.ollama ? 'UP' : 'DOWN';
  document.getElementById('ollama').className = 'v ' + (s.ollama ? 'ok' : 'bad');
  document.getElementById('lane').textContent = s.live_lane || '—';
  document.getElementById('src').textContent = s.source || 'local';
  document.getElementById('tn').textContent = String((s.tasks||[]).length);
  document.getElementById('left').textContent = JSON.stringify(s,null,2);
  document.getElementById('right').textContent = (s.tasks||[]).map(t => (t.status||'') + ' ' + (t.title||t.id)).join('\n') || 'no tasks';
}
async function post(p){ document.getElementById('left').textContent = JSON.stringify(await j(p,{method:'POST'}),null,2); probe(); }
async function ask(){
  const el=document.getElementById('q'); const t=el.value.trim(); if(!t)return; el.value='';
  document.getElementById('left').textContent = '';
  const r = await fetch('/ask_stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  const txt = await r.text();
  document.getElementById('left').textContent = txt;
  probe();
}
probe(); setInterval(probe, 4000);
