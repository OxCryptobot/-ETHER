
async function j(u,o){const r=await fetch(u,o);return r.json()}
function rows(el, items, fmt){
  el.innerHTML = items.length ? items.map(fmt).join("") : "<div class=k>empty</div>";
}
async function probe(){
  let s;
  try { s = await j("/status"); } catch(e) { s = await j("/api/origin"); }
  const up = !!s.ollama;
  document.getElementById("ollama").textContent = up ? "UP" : "DOWN";
  document.getElementById("ollama").className = "v " + (up ? "ok" : "bad");
  document.getElementById("lane").textContent = s.live_lane || "—";
  document.getElementById("role").textContent = s.role || "—";
  document.getElementById("gen").textContent = s.generation == null ? "—" : String(s.generation);
  const tasks = s.tasks || [];
  const queue = s.queue || [];
  document.getElementById("tn").textContent = String(tasks.length);
  document.getElementById("qn").textContent = String(queue.length);
  document.getElementById("left").textContent = "progress "+(s.progress||0)+"% moving="+s.moving+"\n" + 
    "ollama " + up + "\nlane " + (s.live_lane||"") + "\nupdated " + (s.updated||"") +
    "\nrole " + (s.role||"") + "\ngen " + (s.generation||0) + "\n" + (s.idea||"");
  rows(document.getElementById("board"), tasks.slice(-16), t =>
    "<div class=row><div class=k>"+(t.status||"")+"</div><div>"+(t.title||t.id)+"</div></div>");
  rows(document.getElementById("queue"), queue, n => "<div class=row>"+n+"</div>");
}
async function post(p){ await j(p,{method:"POST"}); probe(); }
async function ask(){
  const el=document.getElementById("q"); const t=el.value.trim(); if(!t)return; el.value="";
  const r=await fetch("/ask_stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});
  document.getElementById("left").textContent = "progress "+(s.progress||0)+"% moving="+s.moving+"\n" +  await r.text();
  probe();
}
probe(); setInterval(probe, 3000);
