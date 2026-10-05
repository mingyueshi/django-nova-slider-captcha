/* End-to-end DOM/API contract checks. Real Django test client, jsdom rendering.
   Set JSDOM_MODULE to an installed jsdom module and NOVA_PYTHON to a test venv.
   This suite does not claim browser pixel, touch, or layout verification. */
const {JSDOM}=require(process.env.JSDOM_MODULE || 'jsdom');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const readline=require('node:readline');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const python=process.env.NOVA_PYTHON||'python';
const bridge=spawn(python,[path.join(__dirname,'dom_bridge.py')],{cwd:root,env:process.env});
bridge.stderr.on('data',d=>process.stderr.write(d));
let id=0;const pending=new Map();
readline.createInterface({input:bridge.stdout}).on('line',line=>{let d=JSON.parse(line);const p=pending.get(d.id);pending.delete(d.id);d.error?p.reject(new Error(d.error)):p.resolve(d.result)});
function call(body){return new Promise((resolve,reject)=>{const requestId=++id;pending.set(requestId,{resolve,reject});bridge.stdin.write(JSON.stringify({...body,requestId})+'\n')})}
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn){for(let i=0;i<300;i++){if(fn())return;await delay(10)}throw Error('Wait timed out')}
async function page(url, demo=false){
 const response=await call({path:url});assert.equal(response.status,200);
 const dom=new JSDOM(response.text,{url:'http://testserver'+url,runScripts:'outside-only'});const w=dom.window;
 w.HTMLImageElement.prototype.decode=async()=>{};
 w.fetch=async(url,opts={})=>{const r=await call({path:new URL(url,w.location.href).pathname,method:opts.method||'GET',headers:opts.headers||{},body:opts.body});return{ok:r.status>=200&&r.status<300,status:r.status,headers:{get:()=>r.text.startsWith('{')?'application/json':'text/html'},json:async()=>JSON.parse(r.text)}};
 const timers=new Map();let timerId=0;
 w.setTimeout=(fn,ms)=>{if(ms>=50000){const tid=++timerId;timers.set(tid,{fn,ms});return tid}return setTimeout(fn,ms)};
 w.clearTimeout=t=>{if(timers.has(t))timers.delete(t);else clearTimeout(t)};
 if(demo)w.eval(fs.readFileSync(path.join(root,'src/nova_slider_captcha/static/nova_slider_captcha/demo.js'),'utf8'));
 w.eval(fs.readFileSync(path.join(root,'src/nova_slider_captcha/static/nova_slider_captcha/slider.js'),'utf8'));
 const slider=w.document.querySelector('nova-slider');await wait(()=>slider.state==='ready');
 return {dom,w,slider,timers};
}
(async()=>{
 const results=[];
 let p=await page('/captcha/',true);let {w,slider}=p;
 assert.equal(w.document.querySelectorAll('[name=nova_slider_token]').length,1);
 assert.equal(slider.locale, 'zh-CN');assert.equal(slider.status.textContent,'拖动拼图，对齐图中的缺口');assert.equal(w.document.documentElement.lang,'zh-hans');assert.equal(w.document.querySelector('#demo-submit').textContent,'提交受保护的请求');results.push('Django Chinese locale renders translated demo and initializes Chinese widget');
 slider.move(0);await slider.verify();assert.equal(slider.state,'ready');assert.match(slider.status.textContent,/4/);results.push('wrong guess keeps widget usable with four attempts');
 const solution=await call({op:'solution',id:slider.challenge.challengeId});
 slider.range.value=solution.x;slider.range.dispatchEvent(new w.Event('input'));slider.range.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 await wait(()=>slider.state==='success');assert.equal(slider.getToken().length,43);assert.equal(w.document.querySelector('#demo-submit').disabled,false);results.push('keyboard Enter verifies through real Django API');
 const token=slider.getToken();w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));await wait(()=>w.document.querySelector('#demo-result').textContent===slider.getText('demo_accepted'));
 assert.equal(w.document.querySelector('#demo-submit').disabled,true);results.push('protected demo consumes token and displays local Chinese result');
 slider.setLocale('en');assert.equal(slider.status.textContent.includes('Verified.'),true);assert.equal(w.document.querySelector('#demo-result').textContent,'Request accepted. The verification token has been used.');assert.equal(slider.getToken(),token);results.push('dynamic English locale translates success and demo result without losing proof');
 const csrf=(await call({path:'/captcha/init'}));const csrfToken=JSON.parse(csrf.text).csrfToken;
 const replay=await call({path:'/captcha/submit',method:'POST',headers:{'X-CSRFToken':csrfToken},body:JSON.stringify({token,purpose:'demo'})});assert.equal(replay.status,403);results.push('real Django rejects protected replay');
 await slider.refresh();assert.equal(slider.getToken(),'');assert.equal(w.document.querySelector('#demo-submit').disabled,true);
 await Promise.all([slider.refresh(),slider.refresh()]);assert.equal(slider.state,'ready');results.push('repeated refresh keeps newest challenge and clears proof');
 let currentSolution=(await call({op:'solution',id:slider.challenge.challengeId})).x;slider.move(currentSolution);await slider.verify();
 const originalFetch=w.fetch;let releaseSubmit,submitted=false;
 w.fetch=async(url,options)=>{const response=await originalFetch(url,options);if(url.endsWith('submit')){submitted=true;await new Promise(resolve=>releaseSubmit=resolve)}return response};
 w.document.querySelector('#demo-result').textContent='waiting on A';
 w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));await wait(()=>submitted);
 await slider.refresh();currentSolution=(await call({op:'solution',id:slider.challenge.challengeId})).x;slider.move(currentSolution);await slider.verify();
 const newerToken=slider.getToken();assert.equal(w.document.querySelector('#demo-submit').disabled,false);
 releaseSubmit();await delay(25);
 assert.equal(slider.getToken(),newerToken);assert.equal(w.document.querySelector('#demo-submit').disabled,false);assert.equal(w.document.querySelector('#demo-result').textContent,'waiting on A');
 w.fetch=originalFetch;
 w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));await wait(()=>w.document.querySelector('#demo-result').textContent===slider.getText('demo_accepted'));
 results.push('late submit A cannot clear or overwrite refreshed proof B, which remains usable');
 p.dom.window.close();
 p=await page('/admin/login/');({w,slider}=p);
 assert.equal(w.document.querySelectorAll('[name=nova_slider_token]').length,1);assert.equal(slider.purpose,'login');assert.equal(slider.locale,'zh-CN');assert.equal(slider.getAttribute('aria-label'),'安全验证');assert.ok(w.document.querySelector('noscript').textContent.includes('此图形验证需要 JavaScript'));results.push('Django Admin widget label and nonvisual fallback are translated');
 let x=(await call({op:'solution',id:slider.challenge.challengeId})).x;slider.move(x);await slider.verify();assert.equal(slider.state,'success');
 const fields=new w.FormData(w.document.querySelector('form'));assert.equal(fields.getAll('nova_slider_token').length,1);assert.equal(fields.get('nova_slider_token').length,43);results.push('Admin has exactly one populated login proof field');
 const expiry=[...p.timers.values()].find(t=>t.ms>=50000 && t.ms<=60000);assert.ok(expiry);expiry.fn();assert.equal(slider.getToken(),'');assert.equal(slider.state,'expired');results.push('proof expiration clears Admin hidden field');
 await slider.refresh();for(let i=0;i<5;i++){slider.move(0);await slider.verify()}assert.equal(slider.state,'error');assert.equal(slider.getToken(),'');results.push('fifth mismatch locks widget and leaves no proof');
 p.dom.window.close();
 fs.writeFileSync(path.join(root,'verification/dom-results.json'),JSON.stringify({status:'passed',engine:'jsdom 26.1.0 + real Django test client',checks:results,limitations:['No browser layout, pixels, pointer/touch rendering, or assistive-technology testing']},null,2)+'\n');
 console.log(JSON.stringify(results));bridge.stdin.end();
})().catch(error=>{console.error(error);bridge.kill();process.exitCode=1});
