"""Loopback Django/Chromium focus regression via the Playwright CLI skill.

Start Django with a private NOVA_TEST_DB first. Run from the repository root:
python verification/2026-10-29-review-fixes/browser_checks.py --work /path/to/new-work
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8896/captcha-demo/")
    parser.add_argument("--baseline", default="75117ebdfc032d00e140d050fcc2e7fe9b571e52")
    args = parser.parse_args()
    work = args.work.resolve()
    images = work / "output/playwright"
    images.mkdir(parents=True, exist_ok=True)
    baseline = work / "baseline-slider.js"
    baseline.write_bytes(subprocess.check_output(["git", "show", args.baseline + ":src/nova_slider_captcha/static/nova_slider_captcha/slider.js"], cwd=ROOT))
    cli = Path.home() / ".codex/skills/playwright/scripts/playwright_cli.sh"

    def run(*command):
        result = subprocess.run([str(cli), "-s=nova-review-20261029", *command], cwd=work, text=True, capture_output=True, check=True)
        if "### Error" in result.stdout:
            raise RuntimeError(result.stdout)
        return result.stdout

    run("open", args.url, "--headed")
    run("snapshot")
    code = r"""async (page) => {
      const results = [];
      const require = (condition, message) => { if (!condition) throw new Error(message); };
      const state = () => page.evaluate(() => {
        const w = document.querySelector('nova-slider');
        return {state:w.state, active:document.activeElement === w.range ? 'range' : document.activeElement === w.querySelector('.nsc-refresh') ? 'refresh' : document.activeElement.tagName,
          disabled:w.range.disabled, ariaDisabled:w.range.getAttribute('aria-disabled'), x:w.x, calls:window.verifyCalls};
      });
      const prepare = async () => {
        await page.reload();
        await page.waitForFunction(() => document.querySelector('nova-slider')?.state === 'ready');
        await page.evaluate(() => {
          const original = window.fetch;
          window.verifyCalls = 0;
          window.fetch = async (...args) => {
            const verify = String(args[0]).endsWith('/verify');
            if (verify) { window.verifyCalls++; window.releaseVerify = null; }
            const response = await original(...args);
            if (verify) await new Promise(resolve => { window.releaseVerify = resolve; });
            return response;
          };
        });
      };
      const submit = async () => {
        await page.getByRole('slider').focus();
        await page.keyboard.press('ArrowRight');
        await page.keyboard.press('Enter');
        await page.waitForFunction(() => typeof window.releaseVerify === 'function');
      };
      const release = async () => {
        await page.evaluate(() => window.releaseVerify());
        await page.waitForFunction(() => document.querySelector('nova-slider').state === 'ready');
      };
      await page.unroute('**/slider.js');
      await page.route('**/slider.js', route => route.fulfill({path:BASELINE, contentType:'application/javascript'}));
      await prepare(); await submit();
      const before = await state(); await release(); const after = await state();
      require(before.active === 'BODY' && after.active === 'BODY' && before.disabled, 'Baseline did not reproduce focus loss');
      results.push({case:'baseline keyboard error', checking:before, ready:after});
      await page.unroute('**/slider.js');
      for (const spec of [
        {locale:'zh-CN', width:1280, scheme:'light', action:'retry'},
        {locale:'en', width:360, scheme:'dark', action:'retry'},
        {locale:'zh-CN', width:360, scheme:'light', action:'tab'},
        {locale:'en', width:360, scheme:'dark', action:'refresh'},
      ]) {
        await page.setViewportSize({width:spec.width, height:850});
        await page.emulateMedia({colorScheme:spec.scheme});
        await prepare();
        await page.evaluate(locale => { const w=document.querySelector('nova-slider'); w.setLocale(locale); w.style.maxWidth='240px'; }, spec.locale);
        await submit();
        const checking = await state();
        require(checking.active === 'range' && !checking.disabled && checking.ariaDisabled === 'true', 'Checking lost focus or its disabled semantics');
        await page.keyboard.press('ArrowRight'); await page.keyboard.press('End'); await page.keyboard.press('Enter');
        const guarded = await state();
        require(guarded.x === checking.x && guarded.calls === 1, 'Checking allowed edits or duplicate requests');
        if (spec.action === 'tab') await page.keyboard.press('Tab');
        if (spec.action === 'refresh') {
          await page.keyboard.press('Tab'); await page.keyboard.press('Enter');
          await page.waitForFunction(() => document.querySelector('nova-slider').state === 'ready');
        }
        await release();
        const ready = await state();
        const expected = spec.action === 'retry' ? 'range' : 'refresh';
        require(ready.active === expected && ready.ariaDisabled === 'false', 'Response stole focus or did not re-enable retry');
        const aria = await page.evaluate(() => {
          const w=document.querySelector('nova-slider');
          return {overlay:w.overlay.getAttribute('aria-hidden'), live:w.status.getAttribute('role'), overflow:document.documentElement.scrollWidth > innerWidth};
        });
        require(aria.overlay === 'true' && aria.live === 'status' && !aria.overflow, 'ARIA or narrow viewport check failed');
        await page.screenshot({path:IMAGES + '/' + spec.locale + '-' + spec.scheme + '-' + spec.action + '.png'});
        results.push({case:spec, checking, ready, aria});
      }
      return {browser:page.context().browser().version(), backend:'loopback Django test settings, private SQLite', baseline:REVISION, results};
    }""".replace("BASELINE", json.dumps(str(baseline))).replace("IMAGES", json.dumps(str(images))).replace("REVISION", json.dumps(args.baseline))
    output = run("run-code", code)
    payload = output.split("### Result\n", 1)[1].split("\n### ", 1)[0]
    data = json.loads(payload)
    (EVIDENCE / "browser.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    for image in images.glob("*.png"):
        shutil.copyfile(image, EVIDENCE / image.name)
    run("close")
    print(json.dumps({"browser":data["browser"], "cases":len(data["results"]), "status":"passed"}))


if __name__ == "__main__":
    main()
