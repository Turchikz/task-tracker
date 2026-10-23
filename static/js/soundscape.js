(()=>{'use strict';
const body=document.body, uid=body.dataset.soundUser;if(!uid)return;
const key='ratracker:sound:'+uid, defaults={notifications:false,effects:false,footsteps:false,volume:25};
let prefs;try{prefs={...defaults,...JSON.parse(localStorage.getItem(key)||'{}')}}catch(_){prefs={...defaults}}
let ctx=null,master=null,activated=false,latest=null;
const save=()=>{try{localStorage.setItem(key,JSON.stringify(prefs))}catch(_){}};
['pointerdown','keydown'].forEach(type=>document.addEventListener(type,()=>{activated=true},{once:true,capture:true}));
function tone(freq,delay=0,duration=.12,wave='sine',pan=0){if(!activated||!prefs.volume)return;try{ctx??=new(window.AudioContext||window.webkitAudioContext)();if(!master){master=ctx.createDynamicsCompressor();master.threshold.value=-8;master.knee.value=8;master.ratio.value=10;master.attack.value=.003;master.release.value=.18;master.connect(ctx.destination)}if(ctx.state==='suspended')ctx.resume();const at=ctx.currentTime+delay,o=ctx.createOscillator(),g=ctx.createGain();o.type=wave;o.frequency.value=freq;g.gain.setValueAtTime(.0001,at);g.gain.exponentialRampToValueAtTime(Math.min(.99,.99*prefs.volume/100),at+.015);g.gain.exponentialRampToValueAtTime(.0001,at+duration);o.connect(g);if(ctx.createStereoPanner){const p=ctx.createStereoPanner();p.pan.value=pan;g.connect(p);p.connect(master)}else g.connect(master);o.start(at);o.stop(at+duration+.02)}catch(_){}}
function play(event,extra={}){if(event==='footsteps'?!prefs.footsteps:['notice','assigned','revision','due'].includes(event)?!prefs.notifications:!prefs.effects)return;
const patterns={notice:[[740,0],[980,.15]],assigned:[[550,0],[700,.12]],revision:[[500,0],[360,.16]],due:[[520,0]],done:[[520,0],[660,.13],[880,.26]],accepted:[[660,0],[880,.14],[1100,.28]],switch:[[360,0]],save:[[860,0]],error:[[300,0],[240,.12]],legendary:[[520,0],[660,.11],[780,.22],[1040,.33],[1320,.44]],cheese:[[640,0],[880,.11]],escape:[[850,0],[680,.12]],catch:[[1100,0],[1400,.13]],'all-done':[[523,0],[659,.15],[784,.3],[1047,.45]]};
if(event==='footsteps'){for(let i=0;i<4;i++)tone(140+i*15,i*.07,.045,'triangle',extra.pan||0);return}
if(event==='catch'){const v=Math.floor(Math.random()*4);patterns.catch=[[[1200,0],[1500,.12]],[[460,0],[900,.09]],[[760,0],[1000,.11]],[[660,0],[880,.1],[1100,.2]]][v]}
(patterns[event]||patterns.notice).forEach(([f,t])=>tone(f,t,event==='legendary'?.2:.13,event==='switch'?'square':'sine'))}
window.RaTrackerSound={play,settings:()=>({...prefs})};
const settings=document.querySelector('#sound-settings'),opener=document.querySelector('[data-sound-open]');
if(settings&&opener){const names=['notifications','effects','footsteps','volume'];function render(){names.forEach(k=>{const el=settings.querySelector('[name='+k+']');if(el){if(k==='volume')el.value=prefs[k];else el.checked=!!prefs[k]}});settings.querySelector('[data-volume-value]').textContent=prefs.volume+'%'}
opener.addEventListener('click',()=>{render();settings.hidden=!settings.hidden;opener.setAttribute('aria-expanded',String(!settings.hidden))});settings.querySelector('[data-sound-close]').addEventListener('click',()=>{settings.hidden=true;opener.setAttribute('aria-expanded','false')});
names.forEach(k=>settings.querySelector('[name='+k+']')?.addEventListener('input',e=>{prefs[k]=k==='volume'?Number(e.target.value):e.target.checked;save();render()}));settings.querySelector('[data-sound-preview]').addEventListener('click',()=>{activated=true;play('catch')})}
document.addEventListener('click',e=>{if(e.target.closest('[data-theme-toggle],[data-theme-menu-toggle]'))play('switch')});
const feed=body.dataset.soundFeed;async function poll(){if(!feed||!prefs.notifications)return;try{const response=await fetch(feed,{credentials:'same-origin',cache:'no-store'});if(!response.ok)return;const data=await response.json();const sharedKey=key+':latest',shared=Number(localStorage.getItem(sharedKey)||0);if(latest===null){latest=Math.max(data.latest,shared);localStorage.setItem(sharedKey,String(latest));return}if(data.latest>Math.max(latest,shared)){latest=data.latest;localStorage.setItem(sharedKey,String(latest));play(data.kind==='revision_requested'?'revision':['overdue','due_soon'].includes(data.kind)?'due':data.kind==='assigned'?'assigned':data.kind==='accepted'?'accepted':'notice')}}catch(_){}}
poll();setInterval(poll,30000);document.addEventListener('visibilitychange',()=>{poll()});
// Mouse scheduling uses active page time, not wall time in a background tab.
// Browser timer throttling must not cause a mouse to appear on tab activation.
if(window.matchMedia&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches&&window.matchMedia('(min-width:800px)').matches){
let streak=0, activeMs=0, lastTick=performance.now(), nextRun=(10+Math.random()*10)*60000, runner=null;
function spawn(options={}){
 // Manual test may run immediately; automatic runs require the visible focused tab.
 if(!options.force&&(document.hidden||!document.hasFocus()))return false;
 if(runner){runner.remove();runner=null;}
 const b=document.createElement('button'),gold=options.legendary===true||(options.legendary!==false&&Math.random()<.01),right=Math.random()<.5;
 b.type='button';b.className='ratracker-runner'+(gold?' legendary':'');
 b.title='Поймать мышку';b.setAttribute('aria-label','Поймать мышку');
 b.style.setProperty('--from',right?'calc(100vw + 80px)':'-80px');
 b.style.setProperty('--to',right?'-80px':'calc(100vw + 80px)');
 b.style.animationDuration=(3.9+Math.random()*1.9).toFixed(2)+'s';
 b.classList.toggle('running-left',right);
 const sprite=document.createElement('span');sprite.className='ratracker-mouse-sprite';sprite.setAttribute('aria-hidden','true');b.append(sprite);
 document.body.append(b);runner=b;
 let caught=false;
 b.addEventListener('click',()=>{
  caught=true;streak++;play(gold?'legendary':'catch');
  if(streak>=3&&Math.random()<.25)play('cheese');
  const toast=document.createElement('div');toast.className='mouse-toast';toast.setAttribute('role','status');
  toast.textContent=gold?'Золотая мышка поймана!':streak>=3?'Мышка поймана! Серия: '+streak:'Мышка поймана!';
  document.body.append(toast);setTimeout(()=>toast.remove(),2400);b.remove();if(runner===b)runner=null;
 },{once:true});
 b.addEventListener('animationend',()=>{if(!caught)b.remove();if(runner===b)runner=null},{once:true});
 play('footsteps',{pan:right?1:-1});
 setTimeout(()=>{b.remove();if(runner===b)runner=null},9500);
 return true;
}
// Stable browser-console test API, independent of internal timer implementation.
// RaTrackerMouse.spawn() or RaTrackerMouse.spawn({legendary:true}).
window.RaTrackerMouse={
 spawn:(options={})=>spawn({...options,force:true}),
 remove:()=>{if(runner){runner.remove();runner=null;}},
 status:()=>({active:!!runner,streak,version:'0.9.8',enabled:true})
};
function resetClock(){lastTick=performance.now();if(runner){runner.remove();runner=null;}}
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
}else{window.RaTrackerMouse={spawn:()=>false,remove:()=>{},status:()=>({active:false,version:'0.9.8',enabled:false,reason:'desktop-or-reduced-motion'})};}
})();
