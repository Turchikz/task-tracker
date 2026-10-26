(()=>{'use strict';
const body=document.body, uid=body.dataset.soundUser;if(!uid)return;
const key='ratracker:sound:'+uid, cheeseKey='ratracker:cheese:'+uid,
  earnedKey='ratracker:cheese-earned:'+uid, catchesKey='ratracker:catches:'+uid,
  wardrobeKey='ratracker:wardrobe:'+uid,
  defaults={notifications:false,effects:false,footsteps:false,mouseEnabled:true,pawTrail:true,mouseEffects:true,volume:25};
let prefs;try{prefs={...defaults,...JSON.parse(localStorage.getItem(key)||'{}')}}catch(_){prefs={...defaults}}
function storedCount(key,fallback=0){try{const value=localStorage.getItem(key),number=Number(value);return value!==null&&Number.isSafeInteger(number)&&number>=0?number:fallback}catch(_){return fallback}}
let cheese=storedCount(cheeseKey),earned=storedCount(earnedKey,cheese),catches=storedCount(catchesKey);
let wardrobe={hat:false,scarf:false};
try{const saved=JSON.parse(localStorage.getItem(wardrobeKey)||'{}');wardrobe={hat:saved.hat===true,scarf:saved.scarf===true}}catch(_){}
const prices={hat:5,scarf:8};
const outfitColors=['#e11d48','#2563eb','#16a34a','#f59e0b','#8b5cf6','#0891b2'];
function saveGame(){try{localStorage.setItem(cheeseKey,String(cheese));localStorage.setItem(earnedKey,String(earned));localStorage.setItem(catchesKey,String(catches));localStorage.setItem(wardrobeKey,JSON.stringify(wardrobe))}catch(_){}}
let ctx=null,master=null,activated=false,latest=null;
const save=()=>{try{localStorage.setItem(key,JSON.stringify(prefs))}catch(_){}};
['pointerdown','keydown'].forEach(type=>document.addEventListener(type,()=>{activated=true},{once:true,capture:true}));
function tone(freq,delay=0,duration=.12,wave='sine',pan=0){if(!activated||!prefs.volume)return;try{ctx??=new(window.AudioContext||window.webkitAudioContext)();if(!master){master=ctx.createDynamicsCompressor();master.threshold.value=-8;master.knee.value=8;master.ratio.value=10;master.attack.value=.003;master.release.value=.18;master.connect(ctx.destination)}if(ctx.state==='suspended')ctx.resume();const at=ctx.currentTime+delay,o=ctx.createOscillator(),g=ctx.createGain();o.type=wave;o.frequency.value=freq;g.gain.setValueAtTime(.0001,at);g.gain.exponentialRampToValueAtTime(Math.min(.99,.99*prefs.volume/100),at+.015);g.gain.exponentialRampToValueAtTime(.0001,at+duration);o.connect(g);if(ctx.createStereoPanner){const p=ctx.createStereoPanner();p.pan.value=pan;g.connect(p);p.connect(master)}else g.connect(master);o.start(at);o.stop(at+duration+.02)}catch(_){}}
function play(event,extra={}){if(event==='footsteps'?!prefs.footsteps:['notice','assigned','revision','due'].includes(event)?!prefs.notifications:!prefs.effects)return;
const patterns={notice:[[740,0],[980,.15]],assigned:[[550,0],[700,.12]],revision:[[500,0],[360,.16]],due:[[520,0]],done:[[520,0],[660,.13],[880,.26]],accepted:[[660,0],[880,.14],[1100,.28]],switch:[[360,0]],save:[[860,0]],error:[[300,0],[240,.12]],legendary:[[520,0],[660,.11],[780,.22],[1040,.33],[1320,.44]],cheese:[[640,0],[880,.11]],escape:[[850,0],[680,.12]],catch:[[1100,0],[1400,.13]],'all-done':[[523,0],[659,.15],[784,.3],[1047,.45]]};
if(event==='footsteps'){for(let i=0;i<4;i++)tone(140+i*15,i*.07,.045,'triangle',extra.pan||0);return}
if(event==='bulb-on'||event==='bulb-off'){
  // A short mechanical click, followed by the filament's rising/falling hum.
  tone(event==='bulb-on'?880:690,0,.035,'square');
  tone(event==='bulb-on'?490:280,.045,.105,'sine');
  return;
}
if(event==='catch'){const v=Math.floor(Math.random()*4);patterns.catch=[[[1200,0],[1500,.12]],[[460,0],[900,.09]],[[760,0],[1000,.11]],[[660,0],[880,.1],[1100,.2]]][v]}
(patterns[event]||patterns.notice).forEach(([f,t])=>tone(f,t,event==='legendary'?.2:.13,event==='switch'?'square':'sine'))}
window.RaTrackerSound={play,settings:()=>({...prefs})};
const settings=document.querySelector('#sound-settings'),opener=document.querySelector('[data-sound-open]');
function mouseTitle(){return earned>=50?'Сырный магнат':earned>=10?'Опытный мышелов':'Начинающий мышелов'}
function speedBonus(){return Math.round(Math.min(catches,30)*3.5)}
const mouseUnlocks=[
 {catches:5,name:'Рыжий окрас',type:'окрас'},
 {catches:10,name:'Очки',type:'аксессуар'},
 {catches:15,name:'Лавандовый окрас',type:'окрас'},
 {catches:25,name:'Жилет',type:'аксессуар'},
 {catches:30,name:'Ночной окрас',type:'окрас'},
 {catches:50,name:'Бабочка',type:'аксессуар'},
];
function renderMouseUnlocks(){
 const panel=settings?.querySelector('[data-mouse-unlocks]');if(!panel)return;
 const lines=mouseUnlocks.map(item=>`${catches>=item.catches?'✓':'🔒'} ${item.catches} поимок — ${item.name}`);
 const next=mouseUnlocks.find(item=>catches<item.catches);
 if(next){const left=next.catches-catches,word=left===1?'поимка':left<5?'поимки':'поимок';lines.unshift(`До следующего открытия: ${left} ${word}`)}
 else lines.unshift('Все открытия получены!');
 panel.textContent=lines.join('\n');
}
function showCheese(){
 const count=settings?.querySelector('[data-cheese-count]');if(count)count.textContent=String(cheese);
 const title=settings?.querySelector('[data-cheese-title]');if(title)title.textContent=mouseTitle();
 const caught=settings?.querySelector('[data-mouse-catches]');if(caught)caught.textContent=String(catches);
 const bonus=settings?.querySelector('[data-mouse-speed]');if(bonus)bonus.textContent=String(speedBonus());
 for(const item of ['hat','scarf']){
  const button=settings?.querySelector(`[data-buy-${item}]`);if(!button)continue;
  button.disabled=wardrobe[item]||cheese<prices[item];
  button.textContent=wardrobe[item]?(item==='hat'?'Шапка куплена':'Шарфик куплен'):
    `${item==='hat'?'Купить шапку':'Купить шарфик'} — ${prices[item]} 🧀`;
 }
 renderMouseUnlocks();
}
showCheese();
const walletUrl=body.dataset.mouseWallet,queueKey='ratracker:mouse-queue:'+uid,
  importedKey='ratracker:mouse-imported:'+uid,legacyKey='ratracker:mouse-legacy:'+uid;
let queue=[],ready=false,syncing=null,flushing=null,eventSequence=0;
try{const saved=JSON.parse(localStorage.getItem(queueKey)||'[]');if(Array.isArray(saved))queue=saved.filter(op=>op&&['catch','buy'].includes(op.action)&&typeof op.event_id==='string')}catch(_){}
const legacyProgress={cheese,earned,catches,wardrobe:{...wardrobe}};
let legacy=legacyProgress;
try{
 const saved=JSON.parse(localStorage.getItem(legacyKey)||'null');
 if(saved&&typeof saved==='object')legacy=saved;
 else localStorage.setItem(legacyKey,JSON.stringify(legacyProgress));
}catch(_){}
function eventId(){
 if(window.crypto?.randomUUID)return window.crypto.randomUUID();
 // Fallback for older browsers; idempotency needs a stable stored identifier.
 return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{
  const n=(Math.floor(Math.random()*16)+eventSequence++)%16;
  return(c==='x'?n:(n&3|8)).toString(16);
 });
}
function syncHint(message){const hint=settings?.querySelector('[data-mouse-sync]');if(hint)hint.textContent=message}
function saveQueue(){try{localStorage.setItem(queueKey,JSON.stringify(queue))}catch(_){}}
function replayPending(){
 for(const op of queue){
  if(op.action==='catch'){cheese+=op.reward;earned+=op.reward;catches++}
  else if(op.action==='buy'&&!wardrobe[op.item]&&cheese>=prices[op.item]){cheese-=prices[op.item];wardrobe[op.item]=true}
 }
 saveGame();showCheese();
}
function applyServer(data){
 if(!Number.isSafeInteger(data.cheese)||!Number.isSafeInteger(data.earned)||!Number.isSafeInteger(data.catches)||!data.wardrobe)return;
 cheese=data.cheese;earned=data.earned;catches=data.catches;
 wardrobe={hat:data.wardrobe.hat===true,scarf:data.wardrobe.scarf===true};
 replayPending();
}
function csrf(){return decodeURIComponent((document.cookie||'').split('; ').find(x=>x.startsWith('csrftoken='))?.slice(10)||'')}
async function postWallet(operation){
 const response=await fetch(walletUrl,{method:'POST',credentials:'same-origin',cache:'no-store',
  headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(operation)});
 if(![200,409].includes(response.status))throw Error('Не удалось сохранить прогресс');
 const data=await response.json();return{ok:response.ok,data};
}
async function flushWallet(){
 if(!ready||!walletUrl||flushing)return flushing;
 flushing=(async()=>{
  while(queue.length){
   const op=queue[0];
   try{
    const result=await postWallet(op);
    queue.shift();saveQueue();applyServer(result.data);
    if(!result.ok){const message=settings?.querySelector('[data-cheese-feedback]');if(message)message.textContent='Покупка не прошла: сыр уже потрачен на другом устройстве.'}
   }catch(_){syncHint('Нет связи · изменения ждут синхронизации');return}
  }
  syncHint('Синхронизировано с вашей учётной записью');
 })();
 try{await flushing}finally{flushing=null}
}
async function syncWallet(){
 if(!walletUrl||syncing)return syncing;
 syncing=(async()=>{
  try{
   if(flushing)await flushing;
   const response=await fetch(walletUrl,{credentials:'same-origin',cache:'no-store'});
   if(!response.ok)throw Error('Нет связи');
   let data=await response.json();
   if(localStorage.getItem(importedKey)!=='1'){
    if(legacy.cheese||legacy.earned||legacy.catches||legacy.wardrobe.hat||legacy.wardrobe.scarf){
     let importId=localStorage.getItem(importedKey+':id');
     if(!importId){importId=eventId();localStorage.setItem(importedKey+':id',importId)}
     const result=await postWallet({action:'import',event_id:importId,legacy});
     if(!result.ok)throw Error('Не удалось перенести копилку');
     data=result.data;
    }
    localStorage.setItem(importedKey,'1');
   }
   applyServer(data);ready=true;await flushWallet();
  }catch(_){syncHint('Нет связи · прогресс будет отправлен позже')}
 })();
 try{await syncing}finally{syncing=null}
}
function queueWallet(operation){if(!walletUrl)return;queue.push({event_id:eventId(),...operation});saveQueue();if(ready)void flushWallet()}
void syncWallet();
document.addEventListener('visibilitychange',()=>{if(!document.hidden)void syncWallet()});
function buyOutfit(item){
 if(wardrobe[item]||cheese<prices[item])return false;
 cheese-=prices[item];wardrobe[item]=true;saveGame();showCheese();queueWallet({action:'buy',item});
 const message=settings?.querySelector('[data-cheese-feedback]');
 if(message)message.textContent=item==='hat'?'Шапка куплена. Появится на следующей мышке!':'Шарфик куплен. Появится на следующей мышке!';
 play('cheese');return true;
}
for(const item of ['hat','scarf'])settings?.querySelector(`[data-buy-${item}]`)?.addEventListener('click',()=>buyOutfit(item));
if(settings&&opener){const names=['notifications','effects','footsteps','mouseEnabled','pawTrail','mouseEffects','volume'];function render(){names.forEach(k=>{const el=settings.querySelector('[name='+k+']');if(el){if(k==='volume')el.value=prefs[k];else el.checked=!!prefs[k]}});settings.querySelector('[data-volume-value]').textContent=prefs.volume+'%'}
opener.addEventListener('click',()=>{render();settings.hidden=!settings.hidden;opener.setAttribute('aria-expanded',String(!settings.hidden));if(!settings.hidden)void syncWallet()});settings.querySelector('[data-sound-close]').addEventListener('click',()=>{settings.hidden=true;opener.setAttribute('aria-expanded','false')});
names.forEach(k=>settings.querySelector('[name='+k+']')?.addEventListener('input',e=>{prefs[k]=k==='volume'?Number(e.target.value):e.target.checked;save();if(k==='mouseEnabled'&&!prefs.mouseEnabled)window.RaTrackerMouse?.remove();render()}));settings.querySelector('[data-sound-preview]').addEventListener('click',()=>{activated=true;play('catch')})}
document.addEventListener('ratracker:theme-changed',e=>play(e.detail.theme==='light'?'bulb-on':'bulb-off'));
document.addEventListener('click',e=>{if(e.target.closest('[data-theme-menu-toggle]'))play('switch')});
const feed=body.dataset.soundFeed;async function poll(){if(!feed||!prefs.notifications)return;try{const response=await fetch(feed,{credentials:'same-origin',cache:'no-store'});if(!response.ok)return;const data=await response.json();const sharedKey=key+':latest',shared=Number(localStorage.getItem(sharedKey)||0);if(latest===null){latest=Math.max(data.latest,shared);localStorage.setItem(sharedKey,String(latest));return}if(data.latest>Math.max(latest,shared)){latest=data.latest;localStorage.setItem(sharedKey,String(latest));play(data.kind==='revision_requested'?'revision':['overdue','due_soon'].includes(data.kind)?'due':data.kind==='assigned'?'assigned':data.kind==='accepted'?'accepted':'notice')}}catch(_){}}
poll();setInterval(poll,30000);document.addEventListener('visibilitychange',()=>{poll()});
// Mouse scheduling uses active page time, not wall time in a background tab.
// Browser timer throttling must not cause a mouse to appear on tab activation.
if(window.matchMedia&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches&&window.matchMedia('(min-width:800px)').matches){
let streak=0, activeMs=0, lastTick=performance.now(), nextRun=(10+Math.random()*10)*60000, runner=null, trailTimer=null;
function stopTrail(){if(trailTimer){window.clearInterval(trailTimer);trailTimer=null}}
function leaveFootprint(mouse,right){
 if(!mouse.isConnected||document.hidden)return;
 const rect=mouse.getBoundingClientRect();
 if(rect.right<0||rect.left>window.innerWidth)return;
 const paw=document.createElement('span');paw.className='ratracker-paw';paw.textContent='🐾';
 paw.style.left=`${Math.max(4,Math.min(window.innerWidth-24,right?rect.left+10:rect.right-25))}px`;
 paw.style.top=`${Math.max(4,Math.min(window.innerHeight-26,rect.bottom-27))}px`;
 paw.style.transform=`rotate(${right?-22:22}deg)`;
 paw.setAttribute('aria-hidden','true');document.body.append(paw);
 window.setTimeout(()=>paw.remove(),2200);
}
function cheeseBurst(rect,gold){
 const x=Math.max(24,Math.min(window.innerWidth-24,rect.left+rect.width/2));
 const y=Math.max(24,Math.min(window.innerHeight-24,rect.top+rect.height/2));
 for(let i=0;i<(gold?7:4);i++){
  const bit=document.createElement('span');bit.className='ratracker-cheese-bit';bit.textContent='🧀';
  bit.style.left=`${x}px`;bit.style.top=`${y}px`;
  bit.style.setProperty('--cheese-x',`${(i-2)*23+Math.random()*16}px`);
  bit.style.setProperty('--cheese-y',`${-25-Math.random()*48}px`);
  bit.setAttribute('aria-hidden','true');document.body.append(bit);
  window.setTimeout(()=>bit.remove(),1100);
 }
}
function dressMouse(mouse){
 const unlockedGlasses=catches>=10,unlockedVest=catches>=25,unlockedBowtie=catches>=50;
 if(!wardrobe.hat&&!wardrobe.scarf&&!unlockedGlasses&&!unlockedVest&&!unlockedBowtie)return;
 const outfit=document.createElement('span');outfit.className='ratracker-outfit';outfit.setAttribute('aria-hidden','true');
 const hatIndex=Math.floor(Math.random()*outfitColors.length);
 if(wardrobe.hat){
  const hat=document.createElement('span');hat.className='ratracker-hat';
  hat.style.setProperty('--hat-color',outfitColors[hatIndex]);
  outfit.append(hat);
 }
 if(wardrobe.scarf){
  const scarf=document.createElement('span');scarf.className='ratracker-scarf';
  scarf.style.setProperty('--scarf-color',outfitColors[(hatIndex+1+Math.floor(Math.random()*(outfitColors.length-1)))%outfitColors.length]);
  outfit.append(scarf);
 }
 if(unlockedGlasses){const glasses=document.createElement('span');glasses.className='ratracker-glasses';outfit.append(glasses)}
 if(unlockedVest){const vest=document.createElement('span');vest.className='ratracker-vest';outfit.append(vest)}
 if(unlockedBowtie){const bowtie=document.createElement('span');bowtie.className='ratracker-bowtie';outfit.append(bowtie)}
 mouse.append(outfit);
}
function mouseVariant(){
 const variants=[];
 if(catches>=5)variants.push('cinnamon');
 if(catches>=15)variants.push('lavender');
 if(catches>=30)variants.push('midnight');
 return variants.length?variants[Math.floor(Math.random()*variants.length)]:'classic';
}
function leaveCrumb(mouse){
 if(!mouse.isConnected||document.hidden)return;
 const rect=mouse.getBoundingClientRect(),crumb=document.createElement('span');
 crumb.className='ratracker-crumb';crumb.textContent='🧀';crumb.setAttribute('aria-hidden','true');
 crumb.style.left=`${Math.max(4,Math.min(window.innerWidth-22,rect.left+34))}px`;
 crumb.style.top=`${Math.max(4,Math.min(window.innerHeight-22,rect.bottom-26))}px`;
 document.body.append(crumb);setTimeout(()=>crumb.remove(),1500);
}
function mouseToast(message){
 if(!prefs.mouseEffects)return;
 const toast=document.createElement('div');toast.className='mouse-toast';toast.setAttribute('role','status');toast.textContent=message;
 document.body.append(toast);setTimeout(()=>toast.remove(),2400);
}
function spawn(options={}){
 // Manual test may run immediately; automatic runs require the visible focused tab.
 if(!prefs.mouseEnabled||(!options.force&&(document.hidden||!document.hasFocus())))return false;
 if(runner){runner.remove();runner=null;stopTrail()}
 const b=document.createElement('button'),gold=options.legendary===true||(options.legendary!==false&&Math.random()<.01),right=Math.random()<.5;
 const reactionRoll=Math.random();
 const reaction=options.reaction||(!gold?(reactionRoll<.025?'peek':reactionRoll<.055?'crumbs':reactionRoll<.07?'escape':'none'):'none');
 b.type='button';b.className='ratracker-runner'+(gold?' legendary':'');
 b.classList.add('variant-'+mouseVariant());
 if(reaction!=='none')b.classList.add('reaction-'+reaction);
 b.title='Поймать мышку';b.setAttribute('aria-label','Поймать мышку');
 b.style.setProperty('--from',right?'calc(100vw + 80px)':'-80px');
 b.style.setProperty('--to',right?'-80px':'calc(100vw + 80px)');
 // Each capture raises speed 3.5%, capped at +105% and a two-second run.
 b.style.animationDuration=(reaction==='escape'?1.55:Math.max(2,(3.9+Math.random()*1.9)/(1+Math.min(catches,30)*.035))).toFixed(2)+'s';
 b.classList.toggle('running-left',right);
 const sprite=document.createElement('span');sprite.className='ratracker-mouse-sprite';sprite.setAttribute('aria-hidden','true');b.append(sprite);dressMouse(b);
 if(reaction==='peek'){const hint=document.createElement('span');hint.className='ratracker-mouse-reaction';hint.textContent='👀';hint.setAttribute('aria-hidden','true');b.append(hint)}
 document.body.append(b);runner=b;
 trailTimer=window.setInterval(()=>{if(prefs.pawTrail)leaveFootprint(b,!right);if(reaction==='crumbs')leaveCrumb(b)},430);
 let caught=false;
 b.addEventListener('click',()=>{
  caught=true;streak++;catches++;stopTrail();play(gold?'legendary':'catch');
  const rect=b.getBoundingClientRect(),previousEarned=earned,reward=gold?5:1;
  cheese+=reward;earned+=reward;saveGame();queueWallet({action:'catch',reward});
  showCheese();
  const quotes=['Попалась! Мышка оставила сыр.', 'Быстрая реакция! Сыр ваш.', 'Мышка поймана — добыча в копилке.'];
  const milestone=previousEarned<50&&earned>=50?' · Новое звание: Сырный магнат!':previousEarned<10&&earned>=10?' · Новое звание: Опытный мышелов!':'';
  if(prefs.mouseEffects){cheeseBurst(rect,gold);mouseToast((gold?'Золотая мышка! +5 🧀':`${quotes[Math.floor(Math.random()*quotes.length)]} +1 🧀`)+` · В копилке: ${cheese} · Поймано: ${catches}`+milestone)}
  b.remove();if(runner===b)runner=null;
 },{once:true});
 b.addEventListener('animationend',event=>{if(event?.target&&event.target!==b)return;if(!caught){b.remove();if(reaction==='escape'){play('escape');mouseToast('Мышка ускользнула — попробуем поймать следующую!')}}if(runner===b){stopTrail();runner=null}});
 play('footsteps',{pan:right?1:-1});
 setTimeout(()=>{b.remove();if(runner===b){stopTrail();runner=null}},9500);
 return true;
}
// Stable browser-console test API, independent of internal timer implementation.
// RaTrackerMouse.spawn() or RaTrackerMouse.spawn({legendary:true}).
window.RaTrackerMouse={
 spawn:(options={})=>spawn({...options,force:true}),
 remove:()=>{if(runner){runner.remove();runner=null;stopTrail()}},
 status:()=>({active:!!runner,streak,catches,cheese,earned,speedBonus:speedBonus(),wardrobe:{...wardrobe},unlocks:mouseUnlocks.filter(item=>catches>=item.catches).map(item=>item.name),title:mouseTitle(),version:'0.19.9',enabled:prefs.mouseEnabled})
};
function resetClock(){lastTick=performance.now();if(runner){runner.remove();runner=null;stopTrail()}}
document.addEventListener('visibilitychange',resetClock);
window.addEventListener('blur',resetClock);
window.addEventListener('focus',resetClock);
setInterval(()=>{
 const now=performance.now(),elapsed=now-lastTick;lastTick=now;
 if(document.hidden||!document.hasFocus())return;
 // Ignore long gaps caused by browser suspension / machine sleep.
 if(elapsed<0||elapsed>2500)return;
 activeMs+=elapsed;
 if(activeMs>=nextRun){activeMs=0;nextRun=(10+Math.random()*10)*60000;spawn();}
},1000);
}else{window.RaTrackerMouse={spawn:()=>false,remove:()=>{},status:()=>({active:false,catches,cheese,earned,speedBonus:speedBonus(),wardrobe:{...wardrobe},unlocks:mouseUnlocks.filter(item=>catches>=item.catches).map(item=>item.name),title:mouseTitle(),version:'0.19.9',enabled:false,reason:'desktop-or-reduced-motion'})};}
})();
