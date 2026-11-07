
async function j(u){const r=await fetch(u);return r.json()}
async function probe(){
  let s={};
  try{s=await j("/status")}catch(e){try{s=await j("/api/unison")}catch(e2){s={}}}
  const up=!!s.ollama;
  document.getElementById("ollama").textContent=up?"UP":"DOWN";
  document.getElementById("ollama").className="v "+(up?"ok":"bad");
  const kept=s.env_kept|| (s.sota_goals||[]).length ||0;
  document.getElementById("kept").textContent=String(kept);
  document.getElementById("keptbar").style.width=Math.min(100, kept*4)+"%";
  document.getElementById("disk").textContent=s.env_disk!=null?s.env_disk+" GB":"—";
  document.getElementById("last").textContent=s.sota_goal||s.task||"—";
  document.getElementById("honest").textContent=s.sota_kept||s.honest?"TRUE":"FALSE";
  document.getElementById("honest").className="v "+(s.sota_kept||s.honest?"ok":"bad");
  document.getElementById("alive").textContent=s.stale?"STALE":"LIVE";
  document.getElementById("alive").className="v "+(s.stale?"bad":"ok");
  document.getElementById("stamp").textContent=s.app_alive_ts?s.app_alive_ts.slice(11,19)+"Z":"watching";
  document.getElementById("left").textContent=
    "kept="+ kept +"\n"+
    "disk="+ (s.env_disk!=null?s.env_disk+" GB":"—") +"\n"+
    "ollama="+ (up?"up":"down") +"\n"+
    "alive="+ (s.app_alive_ts||"") +"\n"+
    "last="+ (s.sota_goal||"");
  const goals=s.sota_goals||s.growth_queue||[];
  document.getElementById("queue").innerHTML=goals.slice(-12).map(n=>
    "<div class=item>kept "+n+"</div>").join("")||"<div class=item>none yet</div>";
}
probe(); setInterval(probe,3000);
