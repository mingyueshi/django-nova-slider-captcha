async (page) => {
  const results = [];
  for (const help of [false, true]) for (const error of [false, true]) {
    await page.goto(`http://127.0.0.1:8769/?help=${+help}&error=${+error}`);
    await page.waitForFunction(() => [...document.querySelectorAll('nova-slider')].every(w => w.state === 'ready'));
    await page.keyboard.press('Tab');
    if (!await page.getByRole('slider').first().evaluate(el => el === document.activeElement)) throw Error('Tab did not focus range');
    await page.keyboard.press('ArrowRight');
    const widgets = await page.locator('nova-slider').evaluateAll(nodes => nodes.map(w => ({
      id: w.id, invalid: w.range.getAttribute('aria-invalid'), value: w.range.value,
      describedby: w.range.getAttribute('aria-describedby').split(' '), keyboard: w.querySelector('.nsc-keyboard').id,
      texts: w.range.getAttribute('aria-describedby').split(' ').map(id => document.getElementById(id)?.textContent.trim())
    })));
    for (const w of widgets) {
      const expected = [...(help ? [w.id+'_helptext'] : []), ...(error ? [w.id+'_error'] : []), w.keyboard];
      if (JSON.stringify(w.describedby) !== JSON.stringify(expected) || w.invalid !== (error?'true':null) || w.texts.some(t=>!t)) throw Error('ARIA mapping failed');
    }
    if (+widgets[0].value !== 1) throw Error('ArrowRight did not move focused slider');
    const cdp = await page.context().newCDPSession(page);
    const ax = (await cdp.send('Accessibility.getFullAXTree')).nodes.filter(n=>n.role?.value==='slider').map(n=>({name:n.name?.value,description:n.description?.value,invalid:n.properties?.find(p=>p.name==='invalid')?.value.value}));
    await cdp.detach();
    if (ax.length!==2 || ax.some(a=>!a.description.includes('Use the arrow keys') || (help&&!a.description.includes('Use the secure alternative')) || (error&&!a.description.includes('This field is required')))) throw Error('Chrome accessibility description missing');
    results.push({help,error,tabFocus:true,arrowRight:true,widgets,ax});
  }
  const lifecycle = await page.locator('nova-slider').first().evaluate(async w => {
    const id=w.querySelector('.nsc-keyboard').id, original=w.range;
    w.setAttribute('aria-describedby', `id_account-proof_helptext ${id} id_account-proof_helptext`);
    w.setAttribute('aria-invalid','false');
    if(w.range.getAttribute('aria-describedby')!==`id_account-proof_helptext ${id}` || w.range.getAttribute('aria-invalid')!=='false')throw Error('dynamic update failed');
    w.setLocale('zh-CN');
    if(w.range.getAttribute('aria-describedby')!==`id_account-proof_helptext ${id}`)throw Error('locale lost ARIA');
    w.removeAttribute('aria-describedby');w.removeAttribute('aria-invalid');
    if(w.range.getAttribute('aria-describedby')!==id||w.range.hasAttribute('aria-invalid'))throw Error('removal failed');
    w.connectedCallback();if(w.range!==original)throw Error('double connect rebuilt input');
    const parent=w.parentNode;w.remove();parent.append(w);
    const fresh=w.querySelector('.nsc-keyboard').id;
    if(fresh===id||w.range.getAttribute('aria-describedby')!==fresh||w.range.hasAttribute('aria-invalid'))throw Error('reconnect failed');
    return {updates:true,removals:true,locale:true,repeatedConnection:true,reconnect:true};
  });
  return {status:'passed',browser:await page.evaluate(()=>navigator.userAgent),results,lifecycle,limitations:['No screen reader or human assistive technology acceptance']};
}
