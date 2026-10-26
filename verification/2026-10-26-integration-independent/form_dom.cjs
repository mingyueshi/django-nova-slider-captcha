const {createRequire}=require('node:module');
const req=createRequire(process.cwd()+'/package.json');
const {JSDOM}=req('jsdom');
const {spawn}=require('node:child_process');
const {readFileSync}=require('node:fs');
const readline=require('node:readline');
const assert=require('node:assert/strict');
const bridge=spawn(process.env.NOVA_PYTHON||'python',[require('node:path').join(__dirname,'form_bridge.py')],{cwd:process.cwd(),env:{...process.env,PYTHONPATH:'src:.',DJANGO_SETTINGS_MODULE:'tests.settings'}});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
let id=0;const pending=new Map();
readline.createInterface({input:bridge.stdout}).on('line',line=>{const data=JSON.parse(line),p=pending.get(data.id);pending.delete(data.id);data.error?p.reject(Error(data.error)):p.resolve(data.result)});
function call(data){return new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});bridge.stdin.write(JSON.stringify({...data,id:key})+'\n')})}
async function wait(fn){for(let n=0;n<500;n++){if(fn())return;await new Promise(r=>setTimeout(r,10))}throw Error('state timeout')}
(async()=>{
 const {html}=await call({op:'form'});
 const dom=new JSDOM(html,{url:'http://testserver/register',runScripts:'outside-only'}),w=dom.window;
 w.HTMLImageElement.prototype.decode=async()=>{};
 w.fetch=async(url,options={})=>{const r=await call({path:new URL(url,w.location.href).pathname,method:options.method||'GET',headers:options.headers||{},body:options.body});return{ok:r.status<400,status:r.status,headers:{get:()=>r.text.startsWith('{')?'application/json':'text/html'},json:async()=>JSON.parse(r.text)}};
 w.eval(readFileSync('src/nova_slider_captcha/static/nova_slider_captcha/slider.js','utf8'));
 const widget=w.document.querySelector('nova-slider');
 await wait(()=>widget.state==='ready');
 assert.equal(widget.purpose,'signup');
 assert.equal(widget.field.name,'registration-safety');
 assert.equal(w.document.querySelectorAll('[name="registration-safety"]').length,1);
 const answer=await call({op:'answer',challengeId:widget.challenge.challengeId});
 widget.move(answer.x);await widget.verify();assert.equal(widget.state,'success');
 let data=Object.fromEntries(new w.FormData(w.document.querySelector('form')));
 data['registration-email']='invalid';
 const invalid=await call({op:'submit',data});assert.equal(invalid.valid,false);
 data['registration-email']='person@example.com';
 const valid=await call({op:'submit',data});assert.equal(valid.valid,true,JSON.stringify(valid));
 const replay=await call({op:'submit',data});assert.equal(replay.valid,false);
 console.log(JSON.stringify({status:'passed',checks:['real Django rendered configurable-purpose widget','prefixed hidden field submits under exact Django field name','CSRF-backed custom-purpose issuance and solve','other field error retains proof','corrected form consumes once','replay denied'],limitations:['jsdom replaces image decode; no browser layout claim']}));
 dom.window.close();bridge.stdin.end();
})().catch(error=>{console.error(error);bridge.kill();process.exitCode=1});
