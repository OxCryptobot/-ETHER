
async function j(u,o){const r=await fetch(u,o);return r.json()}
function list(el, items, fn){
  el.innerHTML = items.length ? items.map(fn).join("") : "<div class=item>Nothing yet</div>";
}
async function probe(){
  let s={};
  try { s = await j("/status"); } catch(e) { try { s = await j("/api/origin"); } catch(e2) { s={}; } }
  const up=!!s.ollama;
  document.getElementById("dot").className="dot"+(up?" on":"");
  document.getElementById("stat").textContent =
    (up?"Model up":"Model down")+" · "+(s.live_lane||"")+" · gen "+(s.generation||0)+" · "+(s.progress||0)+"%";
  document.getElementById("meta").textContent = (s.role||"idle")+" · "+(s.idea||"no last idea");
  list(document.getElementById("board"), (s.tasks||[]).slice(-20), t =>
    "<div class=item>"+(t.status||"")+" — "+(t.title||t.id)+"</div>");
  list(document.getElementById("queue"), s.queue||[], n => "<div class=item>"+n+"</div>");
}
async function post(p){ try{await j(p,{method:"POST"});}catch(e){} probe(); }
async function ask(){
  const el=document.getElementById("q"); const t=el.value.trim(); if(!t)return; el.value="";
  const chat=document.getElementById("chat");
  chat.insertAdjacentHTML("beforeend","<div class=msg><div class=who>You</div><div class=bubble>"+t.replace(/</g,"")+"</div></div>");
  const r=await fetch("/ask_stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});
  const txt=await r.text();
  chat.insertAdjacentHTML("beforeend","<div class=msg><div class=who>ETHER</div><div class=bubble>"+(txt||"").replace(/</g,"")+"</div></div>");
  chat.scrollTop=chat.scrollHeight;
  probe();
}
probe(); setInterval(probe, 3000);
