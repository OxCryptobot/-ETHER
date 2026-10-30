
async function j(u){const r=await fetch(u);return r.json()}
async function probe(){
  let s={};
  try{s=await j("/status")}catch(e){try{s=await j("/api/unison")}catch(e2){s={}}}
  const up=!!s.ollama;
  document.getElementById("ollama").textContent=up?"UP":"DOWN";
  document.getElementById("ollama").className="v "+(up?"ok":"bad");
  document.getElementById("task").textContent=s.task||"—";
  document.getElementById("honest").textContent=s.honest?"TRUE":"FALSE";
  document.getElementById("honest").className="v "+(s.honest?"ok":"bad");
  document.getElementById("file").textContent=s.file||"—";
  document.getElementById("alive").textContent=s.stale?"STALE":"LIVE";
  document.getElementById("alive").className="v "+(s.stale?"bad":"ok");
  const q=s.growth_queue||[];
  document.getElementById("qn").textContent=String(q.length);
  document.getElementById("left").textContent=
    "writer="+ (s.writer||"exe") +"\n"+
    "alive="+ (s.app_alive_ts||"") +"\n"+
    "task="+ (s.task||"") +"\n"+
    "file="+ (s.file||"");
  const done=new Set(s.growth_done||[]);
  document.getElementById("queue").innerHTML=q.map(n=>
    "<div class=item>"+(done.has(n)?"done ":"open ")+n+"</div>").join("")||"<div class=item>queue empty</div>";
  document.getElementById("assert").textContent=s.assertion||"";
}
probe(); setInterval(probe,3000);
