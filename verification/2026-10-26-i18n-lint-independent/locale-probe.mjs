// Independent public-component contract checks. No real CAPTCHA is solved.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
const require = createRequire(join(process.env.NOVA_JSDOM_ROOT, 'package.json'));
const { JSDOM } = require('jsdom');
const script = readFileSync(join(process.env.NOVA_REVIEW_ROOT, 'src/nova_slider_captcha/static/nova_slider_captcha/slider.js'), 'utf8');
const flush = async () => { await new Promise(setImmediate); await new Promise(setImmediate); };
async function page(locale, method = 'attribute') {
  const dom = new JSDOM('<!doctype html><html lang="fr"><body><form></form></body></html>', {url:'https://local.test/', runScripts:'outside-only'});
  const w = dom.window, calls = [], timers = new Map(); let timerId = 0;
  w.HTMLImageElement.prototype.decode = async () => {};
  w.setTimeout = (fn, ms) => { const id = ++timerId; timers.set(id, {fn,ms}); return id; };
  w.clearTimeout = id => timers.delete(id);
  w.fetch = async (url, options) => {
    calls.push({url,options});
    const body = url.endsWith('init') ? {csrfToken:'test-csrf'} : url.endsWith('challenge') ? {
      challengeId:'isolated-test-challenge', background:'data:image/png;base64,AA', piece:'data:image/png;base64,AA',
      width:320,height:160,pieceWidth:44,pieceY:56,expiresIn:120,maxAttempts:5
    } : {ok:true,token:'test-proof',expiresIn:60};
    return {ok:true,status:200,headers:{get:()=>'application/json'},json:async()=>body};
  };
  const el = w.document.createElement('nova-slider');
  if (method === 'preupgrade') el.locale = locale;
  else if (locale !== undefined) el.setAttribute('locale', locale);
  w.eval(script); w.document.querySelector('form').append(el); await flush();
  return {dom,w,el,calls,timers};
}
function ready(c, lang) {
  const english = lang === 'en';
  assert.equal(c.el.locale, lang);
  assert.equal(c.el.lang, lang);
  assert.equal(c.el.querySelector('.nsc').lang, lang);
  assert.equal(c.el.getAttribute('aria-label'), english?'Security verification':'安全验证');
  assert.equal(c.el.querySelector('.nsc-status').textContent, english?'Slide the piece to fit the gap':'拖动拼图，对齐图中的缺口');
  assert.equal(c.el.querySelector('input[type=range]').getAttribute('aria-label'), english?'Move the puzzle piece':'移动拼图块');
  assert.equal(c.el.querySelector('.nsc-background').alt, english?'Landscape with a missing puzzle piece':'带有一处拼图缺口的山水图案');
}
test('missing and empty locale retain Chinese despite document language', async () => {
  for (const locale of [undefined,'','   ']) { const c=await page(locale); try {ready(c,'zh-CN');} finally {c.dom.window.close();} }
});
test('explicit unsupported language tags use English including accessible labels', async () => {
  for (const locale of ['fr','fr-FR','ja-JP','de','ar','sr_Latn_RS','pt-BR']) {const c=await page(locale); try {ready(c,'en');} finally {c.dom.window.close();}}
});
test('Chinese and English aliases retain their supported dictionaries', async () => {
  for (const [locale,expected] of [['zh','zh_Hans','zh-TW','ZH_hant_HK'].map(x=>[x,'zh-CN']),['en','EN_gb','en-US'].map(x=>[x,'en'])].flat()) {
    const c=await page(locale); try {ready(c,expected);} finally {c.dom.window.close();}
  }
});
test('malformed and non-string property values fail safely to the default', async () => {
  const c=await page(); try {
    for (const invalid of [null,{},123,'__proto__','en-<script>','../fr','fr FR']) {c.el.setLocale(invalid);ready(c,'zh-CN');}
  } finally {c.dom.window.close();}
});
test('pre-upgrade locale property and dynamic fallback preserve proof and expiry', async () => {
  const c=await page('fr-FR','preupgrade'); try {
    ready(c,'en'); await c.el.verify();
    const proof=c.el.getToken(), count=c.calls.length, before=[...c.timers.entries()];
    assert.equal(proof,'test-proof'); assert.equal(before.length,1);
    for (const change of [()=>c.el.setLocale('zh-Hans'),()=>{c.el.locale='ja';},()=>c.el.setAttribute('locale','de-DE')]) {
      change(); assert.equal(c.el.getToken(),proof);assert.equal(c.calls.length,count);
      assert.deepEqual([...c.timers.entries()],before);
      assert.equal(new c.w.FormData(c.w.document.querySelector('form')).get('nova_slider_token'),proof);
    }
    assert.equal(c.el.lang,'en');assert.match(c.el.querySelector('.nsc-status').textContent,/^Verified\./);
    before[0][1].fn();assert.equal(c.el.getToken(),'');
    assert.equal(c.el.querySelector('.nsc-status').textContent,'Your verification expired. Please verify again.');
  } finally {c.dom.window.close();}
});
