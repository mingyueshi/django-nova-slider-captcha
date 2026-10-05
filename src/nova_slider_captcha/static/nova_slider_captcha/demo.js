(() => {
 const form = document.getElementById('captcha-demo');
 if (!form) return;
 const slider = form.querySelector('nova-slider');
 const button = document.getElementById('demo-submit');
 const result = document.getElementById('demo-result');
 let token = '', expiry, generation = 0;
 function clear() { token = ''; button.disabled = true; clearTimeout(expiry); }
 function invalidate() { generation++; clear(); }
 slider.addEventListener('verified', ({detail}) => {
  clearTimeout(expiry);
  const proofGeneration = ++generation;
  token = detail.token;
  button.disabled = false;
  expiry = setTimeout(() => { if (generation === proofGeneration) invalidate(); }, detail.expiresIn * 1000);
 });
 slider.addEventListener('captcha-reset', invalidate);
 slider.addEventListener('captcha-state', ({detail}) => { if (detail.state !== 'success') invalidate(); });
 form.addEventListener('submit', async event => {
  event.preventDefault();
  if (!token || button.disabled) return;
  const requestGeneration = generation;
  const submittedToken = token;
  button.disabled = true;
  try {
   const response = await fetch(slider.getAttribute('endpoint') + 'submit', {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({token:submittedToken,purpose:'demo'})});
   const data = await response.json();
   if (requestGeneration !== generation) return;
   result.textContent = data.ok ? data.message : 'Request rejected. Please complete a new challenge.';
  } catch (_) {
   if (requestGeneration !== generation) return;
   result.textContent = 'Network error. Please try a new challenge.';
  } finally {
   if (requestGeneration === generation) invalidate();
  }
 });
})();
