(()=>{'use strict';
const page=document.querySelector('[data-roulette-page]');if(!page)return;
const form=page.querySelector('[data-roulette-form]'),wheel=page.querySelector('[data-wheel]'),
 message=page.querySelector('[data-stage-message]'),live=page.querySelector('[data-live-winners]');
const palette=['#e5d8fb','#ffe7b3','#c8e9f3','#f7cdd7','#d6efdc','#e4dbfc','#ffe0b9','#cddff7'];
const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let spinning=false;
page.querySelectorAll('[data-confirm-delete]').forEach(form=>form.addEventListener('submit',event=>{
 if(!window.confirm('Удалить этот результат из общей истории? Его можно будет восстановить.'))event.preventDefault();
}));
function paint(people){
 wheel.querySelectorAll('.roulette-wheel-label').forEach(node=>node.remove());
 if(!people.length){wheel.style.background='conic-gradient(#eadfff,#fff0cd,#cde9f4,#eadfff)';return}
 const step=360/people.length;
 wheel.style.background=`conic-gradient(${people.map((_,index)=>`${palette[index%palette.length]} ${index*step}deg ${(index+1)*step}deg`).join(',')})`;
 people.forEach((person,index)=>{
  const label=document.createElement('span');label.className='roulette-wheel-label';
  label.style.setProperty('--angle',`${(index+.5)*step}deg`);
  label.textContent=people.length>12?String(index+1):person.name;
  label.title=person.name;wheel.append(label);
 });
}
function currentPool(){return [...form.querySelectorAll('[name=exclude]')].filter(input=>!input.checked).map(input=>({id:Number(input.value),name:input.dataset.name}))}
function updatePool(){
 if(!form||spinning)return;
 const people=currentPool(),count=form.querySelectorAll('[name=exclude]').length;
 form.querySelector('[data-pool-count]').textContent=`Участвуют: ${people.length} из ${count}`;
 const needed=Number(form.querySelector('[data-spin-button]').textContent.match(/\d+/)?.[0]||1);
 form.querySelector('[data-spin-button]').disabled=people.length<needed;
 paint(people);
}
if(form){form.addEventListener('change',updatePool);updatePool()}
else{const last=document.querySelector('#roulette-last-participants');if(last){try{paint(JSON.parse(last.textContent))}catch(_){paint([])}}}
function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms))}
async function animate(people,winner){
 paint(people);
 if(reduced){await sleep(250);return}
 const index=people.findIndex(person=>person.id===winner.id);
 if(index<0)return;
 wheel.style.transition='none';wheel.style.transform='rotate(0deg)';
 // Force the reset to take effect before starting the next spin.
 void wheel.offsetWidth;
 wheel.style.transition='transform 4.3s cubic-bezier(.12,.75,.16,1)';
 const stop=360*(5+Math.floor(Math.random()*2))-((index+.5)*360/people.length);
 wheel.style.transform=`rotate(${stop}deg)`;
 await Promise.race([new Promise(resolve=>wheel.addEventListener('transitionend',resolve,{once:true})),sleep(4700)]);
}
if(form)form.addEventListener('submit',async event=>{
 if(!window.fetch)return;
 event.preventDefault();if(spinning)return;
 const error=form.querySelector('[data-roulette-error]');error.hidden=true;error.textContent='';
 const button=form.querySelector('[data-spin-button]');spinning=true;button.disabled=true;
 try{
  const response=await fetch(form.action,{method:'POST',body:new FormData(form),credentials:'same-origin',headers:{'Accept':'application/json'}});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Не удалось провести розыгрыш');
  page.dataset.latestId=String(data.draw_id);
  const old=page.querySelector('.roulette-last-result');if(old)old.hidden=true;
  live.replaceChildren();let pool=data.participants.slice();
  for(let i=0;i<data.winners.length;i++){
   const winner=data.winners[i];message.textContent=`Выбираем ${i+1} из ${data.winners.length}…`;
   await animate(pool,winner);
   const badge=document.createElement('span');badge.textContent=`${i+1}. ${winner.name}`;live.append(badge);
   message.textContent=`Выбран: ${winner.name}`;
   pool=pool.filter(person=>person.id!==winner.id);
   if(i+1<data.winners.length)await sleep(reduced?150:500);
  }
  message.textContent='Розыгрыш завершён · результат виден всем';
  form.reset();
  if(window.crypto?.randomUUID)form.querySelector('[name=request_id]').value=window.crypto.randomUUID();
  // Refresh the saved history after the animation is complete.
  await sleep(1200);window.location.reload();
 }catch(err){error.textContent=err.message;error.hidden=false;message.textContent='Розыгрыш не проведён';spinning=false;updatePool()}
});
if(page.dataset.statusUrl)window.setInterval(async()=>{
 if(spinning||document.hidden)return;
 try{
  const response=await fetch(page.dataset.statusUrl,{credentials:'same-origin',cache:'no-store'});
  if(!response.ok)return;
  const result=await response.json();
  if(String(result.latest_id||'')!==page.dataset.latestId||String(result.visible_count)!==page.dataset.visibleCount)window.location.reload();
 }catch(_){/* The page will refresh on the next successful check. */}
},10000);
})();
