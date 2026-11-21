// Configure the DB binding and RATE_LIMIT_IP_KEY Worker secret.
// This entrypoint does not serve the hosted demo's presentation page.
import { handleCaptcha } from './captcha.mjs';
export default {
  async fetch(request, env) {
    const match = new URL(request.url).pathname.match(/^\/captcha\/(init|challenge|verify|submit)$/);
    if (!match) return new Response('Not found', { status: 404 });
    return handleCaptcha(request, env, match[1]);
  },
};
