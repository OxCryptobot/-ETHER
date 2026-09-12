
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function probe(){
  let s={};
  try{s=await j("/status")}catch(e){try{s=await j("/api/origin")}catch(e2){s={}}}
  const up=!!s.ollama;
  document.getElementById("ollama").textContent=up?"UP":"DOWN";
  document.getElementById("ollama").className="v "+(up?"ok":"bad");
  document.getElementById("lane").textContent=s.live_lane||"—";
  document.getElementById("gen").textContent=s.generation==null?"—":String(s.generation);
  document.getElementById("prog").textContent=(s.progress||0)+"%";
  document.getElementById("tn").textContent=String((s.tasks||[]).length);
  document.getElementById("qn").textContent=String((s.queue||[]).length);
  document.getElementById("left").textContent=
    "HOST 4B\nmoving="+s.moving+"\n"+(s.idea||"")+"\n"+(s.updated||"");
  document.getElementById("board").innerHTML=(s.tasks||[]).slice(-12).map(t=>
    "<div class=item>"+(t.status||"")+" "+(t.title||t.id)+"</div>").join("")||"<div class=item>no tasks</div>";
  document.getElementById("queue").innerHTML=(s.queue||[]).map(n=>"<div class=item>"+n+"</div>").join("")||"<div class=item>queue empty</div>";
}
async function post(p){try{await j(p,{method:"POST"})}catch(e){} probe()}
async function ask(){
  const el=document.getElementById("q"); const t=el.value.trim(); if(!t)return; el.value="";
  const r=await fetch("/ask_stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});
  document.getElementById("left").textContent=await r.text();
  probe();
}
probe(); setInterval(probe,3000);
