"""The built-in web chat served by the gateway (single self-contained page, no external resources)."""

HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0d0f15">
<title>Notus</title>
<style>
:root{--bg:#f3f4f8;--s1:#fff;--s2:#eceff6;--bd:#d9deea;--tx:#1b2030;--mu:#667089;--ub:#e4e8f6;--ac:#7c5cff;--cb:#eef0f7;--dg:#e5484d}
@media (prefers-color-scheme:dark){:root{--bg:#0d0f15;--s1:#141720;--s2:#1b1f2b;--bd:#2a3040;--tx:#e7eaf3;--mu:#8b94aa;--ub:#252a3d;--cb:#0a0c11}}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--tx);font:16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%}
button,select,textarea,input{font:inherit;color:inherit}
button{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:8px 12px;cursor:pointer}
button.pri{background:var(--ac);border-color:var(--ac);color:#fff;font-weight:600}
button:disabled{opacity:.5}
select,textarea,input[type=text],input[type=password],input[type=number]{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:8px 10px;width:100%}
#app{display:flex;height:100%}
#drawer{width:270px;background:var(--s1);border-right:1px solid var(--bd);display:flex;flex-direction:column;padding:12px;gap:8px;flex:none}
#brand{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:1px;font-size:18px;padding:4px 2px}
#chats{flex:1;overflow:auto;display:flex;flex-direction:column;gap:2px}
.ci{display:flex;align-items:center;border-radius:10px;padding:8px 10px;cursor:pointer;gap:6px}
.ci:hover,.ci.on{background:var(--s2)}.ci.on{color:var(--ac)}
.ci span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ci b{font-weight:400;color:var(--mu);padding:0 6px}
main{flex:1;display:flex;flex-direction:column;min-width:0;height:100%}
header{display:flex;align-items:center;gap:8px;padding:calc(8px + env(safe-area-inset-top)) 12px 8px;background:var(--s1);border-bottom:1px solid var(--bd)}
header select{flex:1;min-width:0}
#menu{display:none}
#log{flex:1;overflow-y:auto;padding:16px 12px;display:flex;flex-direction:column;gap:12px;-webkit-overflow-scrolling:touch}
.m{max-width:min(760px,92%);padding:10px 14px;border-radius:16px;overflow-wrap:anywhere}
.m.user{align-self:flex-end;background:var(--ub)}
.m.bot{align-self:flex-start;background:var(--s1);border:1px solid var(--bd)}
.m p{margin:4px 0}.m pre{background:var(--cb);padding:10px;border-radius:10px;overflow-x:auto;white-space:pre-wrap;margin:6px 0}
.m code{background:var(--cb);padding:1px 5px;border-radius:5px;font-family:ui-monospace,Consolas,monospace;font-size:.92em}.m pre code{background:none;padding:0}
.m ul{margin:4px 0;padding-left:22px}.m h4{margin:8px 0 2px}
.m img{max-width:200px;max-height:160px;border-radius:10px;display:block;margin:4px 0}
.m details{color:var(--mu);font-size:.9em;margin-bottom:6px}.m small{color:var(--mu);display:block;margin-top:6px}
.err{color:var(--dg)}.hint{margin:auto;color:var(--mu);text-align:center;max-width:420px}
#bar{padding:8px 12px calc(10px + env(safe-area-inset-bottom));background:var(--s1);border-top:1px solid var(--bd)}
#att{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.chip{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:3px 8px;font-size:.85em;display:flex;align-items:center;gap:6px}
.chip img{height:34px;border-radius:6px}.chip i{cursor:pointer;font-style:normal;color:var(--mu)}
#row{display:flex;gap:8px;align-items:flex-end}#in{resize:none;max-height:160px}
#sheet{position:fixed;right:0;top:0;bottom:0;width:min(360px,100%);background:var(--s1);border-left:1px solid var(--bd);transform:translateX(100%);transition:transform .2s;z-index:6;padding:calc(14px + env(safe-area-inset-top)) 14px 14px;overflow:auto;display:flex;flex-direction:column;gap:10px}
#sheet.open{transform:none}#sheet label{color:var(--mu);font-size:.85em;display:block;margin-bottom:3px}
#scrim{display:none;position:fixed;inset:0;background:#0007;z-index:5}
@media (max-width:820px){
 #drawer{position:fixed;left:0;top:0;bottom:0;z-index:6;transform:translateX(-100%);transition:transform .2s;padding-top:calc(12px + env(safe-area-inset-top))}
 #drawer.open{transform:none}#menu{display:block}#scrim.on{display:block}
}
</style></head>
<body>
<div id="app">
 <aside id="drawer">
  <div id="brand"><svg width="30" height="30" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#18143f"/><stop offset="1" stop-color="#7a52ff"/></linearGradient></defs><rect width="64" height="64" rx="15" fill="url(#g)"/><path d="M19 46V19l26 27V19" fill="none" stroke="#9fe9ff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>NOTUS</div>
  <button class="pri" id="new"></button>
  <div id="chats"></div>
  <button id="export"></button>
  <small style="color:var(--mu)">Notus __VERSION__</small>
 </aside>
 <div id="scrim"></div>
 <main>
  <header>
   <button id="menu">☰</button>
   <select id="model"></select>
   <button id="gear">⚙</button>
  </header>
  <div id="log"></div>
  <div id="bar">
   <div id="att"></div>
   <div id="row">
    <button id="pick">📎</button>
    <textarea id="in" rows="1"></textarea>
    <button class="pri" id="send"></button>
   </div>
   <input type="file" id="file" multiple hidden accept="image/*,.txt,.md,.csv,.json,.xml,.yaml,.yml,.log,.py,.js,.ts,.java,.c,.cpp,.h,.cs,.go,.rs,.php,.sh,.sql,.html,.css">
  </div>
 </main>
 <section id="sheet">
  <div style="display:flex;justify-content:space-between;align-items:center"><b id="st"></b><button id="close">✕</button></div>
  <div><label id="l_as"></label><select id="as"></select></div>
  <div><label id="l_th"></label><select id="th"></select></div>
  <div><label id="l_te"></label><input type="number" id="te" step="0.05" min="0" max="2"></div>
  <div><label id="l_tp"></label><input type="number" id="tp" step="0.05" min="0" max="1"></div>
  <div><label id="l_mx"></label><input type="number" id="mx" step="64" min="16" max="32768"></div>
  <div><label id="l_sy"></label><textarea id="sy" rows="5"></textarea></div>
  <button id="unload"></button>
  <button id="logout"></button>
  <small id="ver" style="color:var(--mu)"></small>
 </section>
</div>
<script>
"use strict";
const T={en:{new:"+ New chat",export:"Export chat",send:"Send",stop:"Stop",ph:"Message…",settings:"Settings",assistant:"Assistant",none:"No assistant",
 thinking:"Thinking",auto:"Auto",on:"On",off:"Off",temp:"Temperature",topp:"Top-P",max:"Max new tokens",sys:"System prompt",unload:"Unload model from memory",
 logout:"Change access key",key:"Access key:",hint:"Pick a model above and start chatting.\nEverything runs on your own computer.",
 loading:"Loading the model… this can take a while on older hardware.",waiting:"Waiting for the model…",think:"Thinking",tok:"tok",
 novision:"This model cannot read images (no vision projector).",big:"File is too large (max 300 KB of text).",nomodels:"No models in the Notus library",
 err401:"Wrong or missing access key.",conn:"Cannot reach Notus. Is the computer on and sharing enabled?",loaded:"loaded",newchat:"New chat",del:"Delete this chat?"},
 ru:{new:"+ Новый чат",export:"Экспорт чата",send:"Отправить",stop:"Стоп",ph:"Сообщение…",settings:"Настройки",assistant:"Ассистент",none:"Без ассистента",
 thinking:"Размышления",auto:"Авто",on:"Вкл",off:"Выкл",temp:"Температура",topp:"Top-P",max:"Макс. новых токенов",sys:"Системный промпт",unload:"Выгрузить модель из памяти",
 logout:"Сменить ключ доступа",key:"Ключ доступа:",hint:"Выберите модель сверху и общайтесь.\nВсё работает на вашем компьютере.",
 loading:"Загрузка модели… на старом железе это может занять время.",waiting:"Ждём модель…",think:"Размышление",tok:"ток",
 novision:"Эта модель не умеет читать картинки (нет vision-проектора).",big:"Файл слишком большой (макс. 300 КБ текста).",nomodels:"В библиотеке Notus нет моделей",
 err401:"Неверный или отсутствует ключ доступа.",conn:"Нет связи с Notus. Компьютер включён и раздача включена?",loaded:"загружена",newchat:"Новый чат",del:"Удалить этот чат?"}};
const lang=(navigator.language||"en").toLowerCase().startsWith("ru")?"ru":"en";
const t=k=>(T[lang][k]??T.en[k]??k);
const $=id=>document.getElementById(id);
const LS=window.localStorage;
const jget=(k,d)=>{try{const v=JSON.parse(LS.getItem(k));return v??d}catch(e){return d}};

let key=(location.hash.match(/key=([^&]+)/)||[])[1]||LS.getItem("notus.key")||"";
if(key)key=decodeURIComponent(key);
if(location.hash)history.replaceState(null,"",location.pathname);
if(key)LS.setItem("notus.key",key);

let info={models:[],assistants:[],state:"unloaded",loaded:null,allow_switch:true};
let chats=jget("notus.chats",[]);let cur=LS.getItem("notus.cur")||"";
let prefs=Object.assign({temp:0.7,top_p:0.9,max:1024,think:"auto",assistant:"",system:"",model:""},jget("notus.prefs",{}));
let busy=false,ctrl=null,pending=[];

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
function inl(s){
 return esc(s).replace(/`([^`\n]+)`/g,"<code>$1</code>").replace(/\*\*(.+?)\*\*/g,"<b>$1</b>")
  .replace(/(^|[\s(])\*(?!\s)([^*\n]+?)\*(?=[\s).,!?:;]|$)/g,"$1<i>$2</i>")
  .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md(src){
 return String(src).split("```").map((p,i)=>{
  if(i%2===1)return "<pre><code>"+esc(p.replace(/^[^\n]*\n/,"").replace(/\n$/,""))+"</code></pre>";
  const out=[];let list=false;
  for(const line of p.split("\n")){
   let m;
   if((m=line.match(/^\s*[-*+]\s+(.*)$/))){if(!list){out.push("<ul>");list=true}out.push("<li>"+inl(m[1])+"</li>");continue}
   if(list){out.push("</ul>");list=false}
   if((m=line.match(/^#{1,4}\s+(.*)$/)))out.push("<h4>"+inl(m[1])+"</h4>");
   else if(line.trim())out.push("<p>"+inl(line)+"</p>");
  }
  if(list)out.push("</ul>");
  return out.join("");
 }).join("");
}

function save(){LS.setItem("notus.chats",JSON.stringify(chats));LS.setItem("notus.cur",cur);LS.setItem("notus.prefs",JSON.stringify(prefs))}
function chat(){let c=chats.find(x=>x.id===cur);if(!c){c={id:String(Date.now()),title:t("newchat"),messages:[]};chats.unshift(c);cur=c.id;save()}return c}

async function api(path,opt={},retry=true){
 const h=Object.assign({"Content-Type":"application/json"},opt.headers||{});
 if(key)h["Authorization"]="Bearer "+key;
 let r;
 try{r=await fetch(path,Object.assign({},opt,{headers:h}))}catch(e){if(e.name==="AbortError")throw e;throw new Error(t("conn"))}
 if(r.status===401&&retry){
  const k=prompt(t("key"),"");
  if(k===null)throw new Error(t("err401"));
  key=k.trim();LS.setItem("notus.key",key);return api(path,opt,false);
 }
 return r;
}

function renderChats(){
 const box=$("chats");box.innerHTML="";
 for(const c of chats){
  const d=document.createElement("div");d.className="ci"+(c.id===cur?" on":"");
  d.innerHTML="<span>"+esc(c.title)+"</span><b>✕</b>";
  d.onclick=()=>{cur=c.id;save();renderChats();renderLog();closeDrawer()};
  d.querySelector("b").onclick=e=>{e.stopPropagation();if(!confirm(t("del")))return;chats=chats.filter(x=>x.id!==c.id);if(cur===c.id)cur="";save();renderChats();renderLog()};
  box.appendChild(d);
 }
}
function bubble(m){
 const d=document.createElement("div");d.className="m "+(m.role==="user"?"user":"bot");
 fillBubble(d,m);return d;
}
function fillBubble(d,m){
 let h="";
 for(const f of m.files||[])h+='<div class="chip">📎 '+esc(f.name)+"</div>";
 for(const u of m.images||[])h+='<img src="'+u+'">';
 if(m.reasoning)h+="<details><summary>"+t("think")+"</summary>"+esc(m.reasoning).replace(/\n/g,"<br>")+"</details>";
 if(m.error)h+='<p class="err">'+esc(m.error)+"</p>";
 h+=m.role==="user"?"<p>"+esc(m.content||"").replace(/\n/g,"<br>")+"</p>":md(m.content||"");
 if(m.stats)h+="<small>"+esc(m.stats)+"</small>";
 d.innerHTML=h;
}
function renderLog(){
 const log=$("log");log.innerHTML="";const c=chats.find(x=>x.id===cur);
 if(!c||!c.messages.length){const h=document.createElement("div");h.className="hint";h.style.whiteSpace="pre-line";h.textContent=t("hint");log.appendChild(h);return}
 for(const m of c.messages)log.appendChild(bubble(m));
 log.scrollTop=log.scrollHeight;
}

function fillSelects(){
 const sel=$("model");sel.innerHTML="";
 if(!info.models.length){const o=document.createElement("option");o.textContent=t("nomodels");sel.appendChild(o)}
 for(const m of info.models){const o=document.createElement("option");o.value=m.name;o.textContent=(m.loaded?"● ":"")+m.name;sel.appendChild(o)}
 const names=info.models.map(m=>m.name);
 if(!names.includes(prefs.model))prefs.model=info.loaded||names[0]||"";
 sel.value=prefs.model;sel.disabled=!info.allow_switch&&!!info.loaded;
 const as=$("as");as.innerHTML="";
 const o0=document.createElement("option");o0.value="";o0.textContent=t("none");as.appendChild(o0);
 for(const a of info.assistants){const o=document.createElement("option");o.value=a.id;o.textContent=a.name;as.appendChild(o)}
 as.value=info.assistants.some(a=>a.id===prefs.assistant)?prefs.assistant:"";
}
async function refresh(){
 try{const r=await api("/api/info");if(r.ok){info=await r.json();fillSelects();$("ver").textContent="Notus "+(info.version||"")}}catch(e){toast(e.message)}
}
function toast(msg){const log=$("log");const d=document.createElement("div");d.className="hint err";d.textContent=msg;log.appendChild(d);log.scrollTop=log.scrollHeight;setTimeout(()=>d.remove(),6000)}

function curModel(){return info.models.find(m=>m.name===prefs.model)}
function resizeImage(file){
 return new Promise((res,rej)=>{
  const img=new Image(),url=URL.createObjectURL(file);
  img.onload=()=>{const s=Math.min(1,1024/Math.max(img.width,img.height));const c=document.createElement("canvas");
   c.width=Math.round(img.width*s);c.height=Math.round(img.height*s);c.getContext("2d").drawImage(img,0,0,c.width,c.height);
   URL.revokeObjectURL(url);res(c.toDataURL("image/jpeg",0.85))};
  img.onerror=()=>{URL.revokeObjectURL(url);rej(new Error("image"))};img.src=url;
 });
}
function renderAtt(){
 const box=$("att");box.innerHTML="";
 pending.forEach((p,i)=>{const d=document.createElement("div");d.className="chip";
  d.innerHTML=(p.image?'<img src="'+p.image+'">':"📎 "+esc(p.name))+"<i>✕</i>";
  d.querySelector("i").onclick=()=>{pending.splice(i,1);renderAtt()};box.appendChild(d)});
}
async function onFiles(files){
 for(const f of files){
  if(f.type.startsWith("image/")){
   const m=curModel();if(m&&!m.vision){toast(t("novision"));continue}
   try{pending.push({image:await resizeImage(f),name:f.name})}catch(e){}
  }else{
   if(f.size>300*1024){toast(t("big"));continue}
   pending.push({name:f.name,text:await f.text()});
  }
 }
 renderAtt();
}

function buildMessages(c,system){
 const out=[];if(system.trim())out.push({role:"system",content:system});
 let lastUser=-1;c.messages.forEach((m,i)=>{if(m.role==="user")lastUser=i});
 c.messages.forEach((m,i)=>{
  if(m.error)return;
  let text=(m.files||[]).map(f=>"[Attached file: "+f.name+"]\n```\n"+f.text+"\n```").concat([m.content||""]).filter(Boolean).join("\n\n");
  if(m.role==="user"&&(m.images||[]).length){
   if(i===lastUser){out.push({role:"user",content:[{type:"text",text:text||"Describe the image."}].concat(m.images.map(u=>({type:"image_url",image_url:{url:u}})))});return}
   text+="\n[image attached here]";
  }
  out.push({role:m.role,content:text});
 });
 return out;
}

async function send(){
 if(busy){if(ctrl)ctrl.abort();return}
 const text=$("in").value.trim();if(!text&&!pending.length)return;
 const c=chat();
 const um={role:"user",content:text,images:pending.filter(p=>p.image).map(p=>p.image),files:pending.filter(p=>!p.image).map(p=>({name:p.name,text:p.text}))};
 c.messages.push(um);if(c.messages.length===1)c.title=(text||um.files[0]?.name||t("newchat")).slice(0,40);
 pending=[];renderAtt();$("in").value="";autosize();save();renderChats();renderLog();
 const a=info.assistants.find(x=>x.id===prefs.assistant);
 const system=(a&&a.system_prompt)||prefs.system||"";
 const temp=a&&a.temperature>=0?a.temperature:prefs.temp;
 const think=a&&a.think&&a.think!=="inherit"?a.think:prefs.think;
 const body={model:prefs.model,messages:buildMessages(c,system),stream:true,temperature:temp,top_p:prefs.top_p,max_tokens:prefs.max};
 if(think==="on"||think==="off")body.chat_template_kwargs={enable_thinking:think==="on"};
 const bm={role:"assistant",content:"",reasoning:""};
 const log=$("log");const bd=bubble(bm);bd.innerHTML="<p>"+t(info.loaded===prefs.model?"waiting":"loading")+"</p>";log.appendChild(bd);log.scrollTop=log.scrollHeight;
 busy=true;$("send").textContent=t("stop");ctrl=new AbortController();
 const t0=Date.now();let n=0,frame=0;
 const paint=()=>{frame=0;fillBubble(bd,bm);log.scrollTop=log.scrollHeight};
 try{
  const r=await api("/v1/chat/completions",{method:"POST",body:JSON.stringify(body),signal:ctrl.signal});
  if(!r.ok){let msg="HTTP "+r.status;try{const j=await r.json();msg=(j.error&&j.error.message)||msg}catch(e){}throw new Error(msg)}
  const rd=r.body.getReader(),dec=new TextDecoder();let buf="";
  for(;;){
   const {done,value}=await rd.read();if(done)break;
   buf+=dec.decode(value,{stream:true});
   let i;
   while((i=buf.indexOf("\n"))>=0){
    const line=buf.slice(0,i).trim();buf=buf.slice(i+1);
    if(!line.startsWith("data:"))continue;
    const d=line.slice(5).trim();if(d==="[DONE]")continue;
    let o;try{o=JSON.parse(d)}catch(e){continue}
    if(o.error)throw new Error(o.error.message||"error");
    const dl=o.choices&&o.choices[0]&&o.choices[0].delta;if(!dl)continue;
    if(dl.reasoning_content)bm.reasoning+=dl.reasoning_content;
    if(dl.content){bm.content+=dl.content;n++}
    if(!frame)frame=requestAnimationFrame(paint);
   }
  }
 }catch(e){if(e.name!=="AbortError")bm.error=e.message}
 finally{
  if(frame)cancelAnimationFrame(frame);
  const th=bm.content.match(/<think>([\s\S]*?)(<\/think>|$)/);
  if(th){bm.reasoning=(bm.reasoning?bm.reasoning+"\n":"")+th[1].trim();bm.content=bm.content.replace(/<think>[\s\S]*?(<\/think>|$)/,"").trim()}
  const secs=(Date.now()-t0)/1000;if(n)bm.stats=(n/Math.max(secs,0.1)).toFixed(1)+" "+t("tok")+"/s · "+n+" "+t("tok");
  if(!bm.reasoning)delete bm.reasoning;
  fillBubble(bd,bm);
  if(bm.content||bm.reasoning||bm.error){c.messages.push(bm);save()}
  busy=false;ctrl=null;$("send").textContent=t("send");refresh();
 }
}

async function switchModel(name){
 prefs.model=name;save();
 const m=info.models.find(x=>x.name===name);if(!m||m.loaded||!info.allow_switch)return;
 const log=$("log");const d=document.createElement("div");d.className="hint";d.textContent=t("loading");log.appendChild(d);log.scrollTop=log.scrollHeight;
 try{const r=await api("/api/load",{method:"POST",body:JSON.stringify({model:name})});
  if(!r.ok){const j=await r.json().catch(()=>({}));toast((j.error&&j.error.message)||"HTTP "+r.status)}}
 catch(e){toast(e.message)}
 d.remove();refresh();
}

function autosize(){const e=$("in");e.style.height="auto";e.style.height=Math.min(e.scrollHeight,160)+"px"}
function openDrawer(){$("drawer").classList.add("open");$("scrim").classList.add("on")}
function closeDrawer(){$("drawer").classList.remove("open");$("scrim").classList.remove("on")}
function exportChat(){
 const c=chats.find(x=>x.id===cur);if(!c)return;
 const md=c.messages.map(m=>"**"+(m.role==="user"?"You":"Notus")+":**\n\n"+(m.content||"")).join("\n\n---\n\n");
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([md],{type:"text/markdown"}));a.download=(c.title||"chat")+".md";a.click();
}

function initUI(){
 $("new").textContent=t("new");$("export").textContent=t("export");$("send").textContent=t("send");$("in").placeholder=t("ph");
 $("st").textContent=t("settings");$("l_as").textContent=t("assistant");$("l_th").textContent=t("thinking");$("l_te").textContent=t("temp");
 $("l_tp").textContent=t("topp");$("l_mx").textContent=t("max");$("l_sy").textContent=t("sys");$("unload").textContent=t("unload");$("logout").textContent=t("logout");
 const th=$("th");for(const v of ["auto","on","off"]){const o=document.createElement("option");o.value=v;o.textContent=t(v);th.appendChild(o)}
 $("th").value=prefs.think;$("te").value=prefs.temp;$("tp").value=prefs.top_p;$("mx").value=prefs.max;$("sy").value=prefs.system;
 $("new").onclick=()=>{cur="";chat();save();renderChats();renderLog();closeDrawer()};
 $("export").onclick=exportChat;$("send").onclick=send;
 $("in").addEventListener("input",autosize);
 $("in").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey&&!/Mobi|Android/i.test(navigator.userAgent)){e.preventDefault();send()}});
 $("pick").onclick=()=>$("file").click();
 $("file").onchange=e=>{onFiles([...e.target.files]);e.target.value=""};
 $("menu").onclick=openDrawer;$("scrim").onclick=()=>{closeDrawer();$("sheet").classList.remove("open")};
 $("gear").onclick=()=>{$("sheet").classList.add("open");$("scrim").classList.add("on")};
 $("close").onclick=()=>{$("sheet").classList.remove("open");$("scrim").classList.remove("on")};
 $("model").onchange=e=>switchModel(e.target.value);
 $("as").onchange=e=>{prefs.assistant=e.target.value;save()};
 $("th").onchange=e=>{prefs.think=e.target.value;save()};
 $("te").onchange=e=>{prefs.temp=parseFloat(e.target.value)||0.7;save()};
 $("tp").onchange=e=>{prefs.top_p=parseFloat(e.target.value)||0.9;save()};
 $("mx").onchange=e=>{prefs.max=parseInt(e.target.value)||1024;save()};
 $("sy").onchange=e=>{prefs.system=e.target.value;save()};
 $("unload").onclick=async()=>{try{await api("/api/unload",{method:"POST",body:"{}"})}catch(e){toast(e.message)}refresh()};
 $("logout").onclick=()=>{LS.removeItem("notus.key");key="";refresh()};
 document.addEventListener("paste",e=>{const fs=[...(e.clipboardData&&e.clipboardData.files||[])];if(fs.length)onFiles(fs)});
 chat();renderChats();renderLog();refresh();setInterval(()=>{if(!busy)refresh()},15000);
}
initUI();
</script></body></html>
"""
