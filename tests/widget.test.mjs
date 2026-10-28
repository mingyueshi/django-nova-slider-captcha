import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
const script = readFileSync(
  new URL("../src/nova_slider_captcha/static/nova_slider_captcha/slider.js", import.meta.url),
  "utf8",
);
const flush = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
};
const puzzle = (id = "challenge1") => ({
  challengeId: id,
  background: "data:image/png;base64,AA",
  piece: "data:image/png;base64,AA",
  pieceY: 56,
  width: 320,
  height: 160,
  pieceWidth: 44,
  expiresIn: 120,
  maxAttempts: 5,
});
function response(body, status = 200, type = "application/json") {
  return {
    ok: status < 400,
    status,
    headers: { get: () => type },
    json: async () => body,
  };
}
async function setup(handler, options = {}) {
  const dom = new JSDOM(`<!doctype html><html lang="${options.documentLang || "en"}"><body>${options.demo ? '<form id="captcha-demo" action="/captcha-demo/submit"><input name="csrfmiddlewaretoken" value="csrf"><button id="demo-submit" disabled></button><p id="demo-result"></p></form>' : ""}</body></html>`, {
    url: "https://demo.test/",
    runScripts: "outside-only",
  });
  const w = dom.window,
    calls = [],
    timers = new Map();
  let tid = 0;
  w.setTimeout = (fn, ms) => {
    const id = ++tid;
    timers.set(id, { fn, ms });
    return id;
  };
  w.clearTimeout = (id) => timers.delete(id);
  w.HTMLImageElement.prototype.decode = () => Promise.resolve();
  const images = options.images?.(w);
  w.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return handler
      ? handler(url, options, calls)
      : response(
          url.endsWith("init")
            ? { csrfToken: "csrf" }
            : url.endsWith("challenge")
              ? puzzle()
              : { ok: true, token: "proof", expiresIn: 60 },
        );
  };
  const widget = w.document.createElement("nova-slider");
  for (const [key, value] of Object.entries(options.attrs || {})) widget.setAttribute(key, value);
  if (options.messages) widget.messages = options.messages;
  if (Object.hasOwn(options, "localeProperty")) widget.locale = options.localeProperty;
  w.eval(script);
  (options.demo ? w.document.querySelector("form") : w.document.body).append(widget);
  if (options.demo) w.eval(readFileSync(new URL("../src/nova_slider_captcha/static/nova_slider_captcha/demo.js", import.meta.url), "utf8"));
  await flush();
  return { w, dom, widget, calls, timers, images };
}
// Model event delivery and cache state explicitly: jsdom does not load PNGs.
function imageEvents(w, { cached = false, cachedWidth = 320, synchronous = false, decode } = {}) {
  const images = [], states = new WeakMap(), listeners = new Map();
  const prototype = w.HTMLImageElement.prototype;
  prototype.decode = decode;
  const add = prototype.addEventListener, remove = prototype.removeEventListener;
  prototype.addEventListener = function (type, fn, options) {
    if (["load", "error"].includes(type)) {
      if (!listeners.has(this)) listeners.set(this, new Set());
      listeners.get(this).add(fn);
    }
    return add.call(this, type, fn, options);
  };
  prototype.removeEventListener = function (type, fn, options) {
    listeners.get(this)?.delete(fn);
    return remove.call(this, type, fn, options);
  };
  function finish(image, type = "load") {
    states.set(image, { complete: true, width: type === "load" ? 320 : 0 });
    image.dispatchEvent(new w.Event(type));
  }
  Object.defineProperties(prototype, {
    src: { configurable: true, get() { return this.getAttribute("src") || ""; }, set(value) {
      this.setAttribute("src", value);
      states.set(this, { complete: cached, width: cached ? cachedWidth : 0 });
      images.push(this);
      if (synchronous) finish(this);
    } },
    complete: { configurable: true, get() { return states.get(this)?.complete ?? false; } },
    naturalWidth: { configurable: true, get() { return states.get(this)?.width ?? 0; } },
  });
  return { images, finish, listeners, active: () => [...listeners.values()].reduce((n, set) => n + set.size, 0) };
}
function pointer(c, type, pointerId = 1) {
  const event = new c.w.Event(type);
  Object.defineProperty(event, "pointerId", { value: pointerId });
  c.widget.range.dispatchEvent(event);
}
function cleanup(c) {
  c.widget.remove();
  c.dom.window.close();
}
test("form ARIA reaches the focusable slider and keeps keyboard instructions", async () => {
  for (const attrs of [{}, { "aria-describedby": "help" }, { "aria-describedby": "error", "aria-invalid": "true" }, { "aria-describedby": "help error help", "aria-invalid": "true" }]) {
    const c = await setup(undefined, { attrs });
    try {
      const keyboard = c.widget.querySelector(".nsc-keyboard");
      const external = [...new Set((attrs["aria-describedby"] || "").split(/\s+/).filter(Boolean))];
      assert.deepEqual(c.widget.range.getAttribute("aria-describedby").split(" "), [...external, keyboard.id]);
      assert.equal(c.widget.range.getAttribute("aria-invalid"), attrs["aria-invalid"] || null);
      c.widget.range.focus();
      assert.equal(c.w.document.activeElement, c.widget.range);
      assert.ok(keyboard.textContent.length > 0);
    } finally { cleanup(c); }
  }
});
test("form ARIA changes and removals do not reset proof or locale", async () => {
  const c = await setup();
  try {
    await c.widget.verify();
    const token = c.widget.getToken(), seq = c.widget.seq, requests = c.calls.length;
    const keyboard = c.widget.querySelector(".nsc-keyboard");
    c.widget.setAttribute("aria-describedby", ` help\t${keyboard.id}\nerror help `);
    c.widget.setAttribute("aria-invalid", "true");
    assert.equal(c.widget.range.getAttribute("aria-describedby"), `help ${keyboard.id} error`);
    assert.equal(c.widget.range.getAttribute("aria-invalid"), "true");
    c.widget.setLocale("en");
    assert.equal(c.widget.range.getAttribute("aria-label"), "Move the puzzle piece");
    assert.equal(c.widget.range.getAttribute("aria-invalid"), "true");
    c.widget.setAttribute("aria-invalid", "false");
    assert.equal(c.widget.range.getAttribute("aria-invalid"), "false");
    c.widget.removeAttribute("aria-invalid");
    c.widget.removeAttribute("aria-describedby");
    assert.equal(c.widget.range.hasAttribute("aria-invalid"), false);
    assert.equal(c.widget.range.getAttribute("aria-describedby"), keyboard.id);
    assert.equal(c.widget.getToken(), token);
    assert.equal(c.widget.seq, seq);
    assert.equal(c.calls.length, requests);
  } finally { cleanup(c); }
});
test("form ARIA stays independent across widgets and reconnects", async () => {
  const c = await setup(undefined, { attrs: { "aria-describedby": "first-help", "aria-invalid": "true" } });
  const second = c.w.document.createElement("nova-slider");
  try {
    second.setAttribute("aria-describedby", "second-help");
    c.w.document.body.append(second);
    await flush();
    const firstId = c.widget.querySelector(".nsc-keyboard").id;
    const secondId = second.querySelector(".nsc-keyboard").id;
    assert.notEqual(firstId, secondId);
    c.widget.connectedCallback();
    assert.equal(c.widget.querySelector(".nsc-keyboard").id, firstId);
    c.widget.remove();
    c.widget.setAttribute("aria-describedby", "new-help new-help");
    c.widget.removeAttribute("aria-invalid");
    c.w.document.body.append(c.widget);
    await flush();
    const newId = c.widget.querySelector(".nsc-keyboard").id;
    assert.notEqual(newId, firstId);
    assert.equal(c.widget.range.getAttribute("aria-describedby"), `new-help ${newId}`);
    assert.equal(c.widget.range.hasAttribute("aria-invalid"), false);
    assert.equal(second.range.getAttribute("aria-describedby"), `second-help ${secondId}`);
    assert.equal(c.widget.querySelectorAll(".nsc-range").length, 1);
  } finally { second.remove(); cleanup(c); }
});
test("missing decode waits for both load events and cleans listeners", async () => {
  const c = await setup(undefined, { images: imageEvents });
  const [background, piece] = c.images.images;
  assert.equal(c.widget.state, "loading");
  assert.equal(c.images.active(), 4);
  c.images.finish(background);
  await flush();
  assert.equal(c.widget.state, "loading");
  c.images.finish(piece);
  await flush();
  assert.equal(c.widget.state, "ready");
  assert.equal(c.images.active(), 0);
  assert.equal(background.alt, "带有一处拼图缺口的山水图案");
  cleanup(c);
});
test("missing decode handles cached images and listeners installed before src", async () => {
  for (const mode of [{ cached: true }, { synchronous: true }]) {
    const c = await setup(undefined, { images: w => imageEvents(w, mode) });
    assert.equal(c.widget.state, "ready");
    assert.equal(c.images.active(), 0);
    cleanup(c);
  }
});
test("a completed broken cached image fails instead of becoming ready", async () => {
  const c = await setup(undefined, { images: w => imageEvents(w, { cached: true, cachedWidth: 0 }) });
  assert.equal(c.widget.state, "error");
  assert.equal(c.widget.range.disabled, true);
  assert.equal(c.images.active(), 0);
  cleanup(c);
});
test("refresh recovers from fallback image errors while ignoring old events", async () => {
  const c = await setup(undefined, { images: imageEvents });
  const old = [...c.images.images];
  c.images.finish(old[0], "error");
  await flush();
  assert.equal(c.widget.state, "error");
  const pending = c.widget.refresh();
  await flush();
  for (const image of old) c.images.finish(image, "error");
  for (const image of c.images.images.slice(-2)) c.images.finish(image);
  await pending;
  assert.equal(c.widget.state, "ready");
  assert.equal(c.images.active(), 0);
  cleanup(c);
});
test("image errors and decode rejection fail closed and clean the sibling", async () => {
  for (const mode of ["fallback", "decode-error", "decode-reject"]) {
    const c = await setup(undefined, { images: w => imageEvents(w, {
      decode: mode === "decode-error" ? () => new Promise(() => {}) : mode === "decode-reject" ? () => Promise.reject(Error("bad decode")) : undefined,
    }) });
    if (mode !== "decode-reject") c.images.finish(c.images.images[0], "error");
    await flush();
    assert.equal(c.widget.state, "error");
    assert.equal(c.widget.getToken(), "");
    assert.equal(c.widget.range.disabled, true);
    assert.equal(c.images.active(), 0);
    for (const image of c.images.images) c.images.finish(image);
    await flush();
    assert.equal(c.widget.state, "error");
    cleanup(c);
  }
});
test("fallback refresh and disconnect isolate late events and remove listeners", async () => {
  const c = await setup(undefined, { images: imageEvents });
  const old = [...c.images.images];
  const refreshed = c.widget.refresh();
  await flush();
  assert.ok(old.every(image => c.images.listeners.get(image).size === 0));
  for (const image of old) c.images.finish(image);
  await flush();
  assert.equal(c.widget.state, "loading");
  for (const image of c.images.images.slice(2)) c.images.finish(image);
  await refreshed;
  assert.equal(c.widget.state, "ready");
  const pending = c.widget.refresh();
  await flush();
  const disconnected = c.images.images.slice(-2);
  c.widget.remove();
  await pending;
  assert.equal(c.images.active(), 0);
  c.w.document.body.append(c.widget);
  await flush();
  for (const image of disconnected) c.images.finish(image, "error");
  await flush();
  assert.equal(c.widget.state, "loading");
  for (const image of c.images.images.slice(-2)) c.images.finish(image);
  await flush();
  assert.equal(c.widget.state, "ready");
  assert.equal(c.images.active(), 0);
  cleanup(c);
});
test("late decode completion after refresh cannot ready or fail a new generation", async () => {
  const decodes = [];
  const c = await setup(undefined, { images: w => imageEvents(w, { decode: () => new Promise((resolve, reject) => decodes.push({ resolve, reject })) }) });
  const pending = c.widget.refresh();
  await flush();
  decodes[0].resolve();
  decodes[1].reject(Error("old image"));
  await flush();
  assert.equal(c.widget.state, "loading");
  decodes[2].resolve();
  decodes[3].resolve();
  await pending;
  assert.equal(c.widget.state, "ready");
  assert.equal(c.images.active(), 0);
  cleanup(c);
});
test("loads via init/challenge, no answer in DOM and single form field", async () => {
  const c = await setup();
  assert.equal(c.widget.state, "ready");
  assert.deepEqual(
    c.calls.map((x) => x.url),
    ["/captcha/init", "/captcha/challenge"],
  );
  assert.equal(c.widget.querySelectorAll("[name=nova_slider_token]").length, 1);
  assert.equal(c.widget.getToken(), "");
  assert.equal(c.widget.range.disabled, false);
  assert.equal(c.widget.textContent.includes("answer"), false);
  cleanup(c);
});
test("keyboard submission, duplicate verification gated, token/reset events", async () => {
  const c = await setup();
  let proof,
    resets = 0;
  c.widget.addEventListener("verified", (e) => (proof = e.detail));
  c.widget.addEventListener("captcha-reset", () => resets++);
  c.widget.move(122);
  c.widget.range.dispatchEvent(
    new c.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
  );
  c.widget.verify();
  await flush();
  assert.equal(c.calls.filter((x) => x.url.endsWith("verify")).length, 1);
  assert.equal(c.widget.state, "success");
  assert.equal(proof.token, "proof");
  assert.equal(c.widget.getToken(), "proof");
  await c.widget.refresh();
  assert.equal(c.widget.getToken(), "");
  assert.equal(resets, 1);
  cleanup(c);
});
test("wrong answer is retryable and exhausting attempts requires refresh", async () => {
  let attempts = 2;
  const c = await setup((url) =>
    response(
      url.endsWith("init")
        ? { csrfToken: "csrf" }
        : url.endsWith("challenge")
          ? puzzle()
          : { ok: false, code: "incorrect", attemptsRemaining: --attempts },
      url.endsWith("verify") ? 422 : 200,
    ),
  );
  c.widget.move(12);
  await c.widget.verify();
  assert.equal(c.widget.state, "ready");
  assert.equal(c.widget.x, 0);
  await c.widget.verify();
  assert.equal(c.widget.state, "error");
  assert.equal(c.widget.range.disabled, true);
  cleanup(c);
});
test("checking preserves keyboard focus and blocks edits and duplicate submissions", async () => {
  let finish;
  const c = await setup((url) => url.endsWith("verify")
    ? new Promise(resolve => { finish = resolve; })
    : response(url.endsWith("init") ? { csrfToken: "csrf" } : puzzle()));
  try {
    c.widget.range.focus();
    c.widget.move(12);
    c.widget.range.dispatchEvent(new c.w.KeyboardEvent("keydown", { key: "Enter", cancelable: true }));
    await flush();
    assert.equal(c.widget.state, "checking");
    assert.equal(c.widget.range.disabled, false);
    assert.equal(c.widget.range.getAttribute("aria-disabled"), "true");
    assert.equal(c.w.document.activeElement, c.widget.range);
    for (const key of ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", "Enter"]) {
      const event = new c.w.KeyboardEvent("keydown", { key, cancelable: true });
      c.widget.range.dispatchEvent(event);
      assert.equal(event.defaultPrevented, true, key);
    }
    const tab = new c.w.KeyboardEvent("keydown", { key: "Tab", cancelable: true });
    c.widget.range.dispatchEvent(tab);
    assert.equal(tab.defaultPrevented, false);
    const down = new c.w.Event("pointerdown", { cancelable: true });
    c.widget.range.dispatchEvent(down);
    assert.equal(down.defaultPrevented, true);
    c.widget.range.value = 99;
    c.widget.range.dispatchEvent(new c.w.Event("input"));
    assert.equal(c.widget.x, 12);
    assert.equal(c.widget.range.value, "12");
    assert.equal(c.calls.filter(call => call.url.endsWith("verify")).length, 1);
    finish(response({ ok: false, code: "incorrect", attemptsRemaining: 4 }, 422));
    await flush();
    assert.equal(c.widget.state, "ready");
    assert.equal(c.widget.x, 0);
    assert.equal(c.widget.range.getAttribute("aria-disabled"), "false");
    assert.equal(c.w.document.activeElement, c.widget.range);
    assert.equal(c.widget.overlay.getAttribute("aria-hidden"), "true");
    assert.equal(c.widget.status.getAttribute("role"), "status");
  } finally { cleanup(c); }
});
test("retry responses never steal focus moved away during checking", async () => {
  for (const initiallyFocused of [false, true]) {
    let finish;
    const c = await setup((url) => url.endsWith("verify")
      ? new Promise(resolve => { finish = resolve; })
      : response(url.endsWith("init") ? { csrfToken: "csrf" } : puzzle()));
    try {
      if (initiallyFocused) c.widget.range.focus();
      const pending = c.widget.verify();
      await flush();
      const refresh = c.widget.querySelector(".nsc-refresh");
      refresh.focus();
      finish(response({ ok: false, code: "incorrect", attemptsRemaining: 4 }, 422));
      await pending;
      assert.equal(c.widget.state, "ready");
      assert.equal(c.w.document.activeElement, refresh);
    } finally { cleanup(c); }
  }
});
test("late verify success cannot overwrite refreshed challenge", async () => {
  let resolve;
  const c = await setup((url) =>
    url.endsWith("verify")
      ? new Promise((r) => (resolve = r))
      : response(url.endsWith("init") ? { csrfToken: "csrf" } : puzzle()),
  );
  const verification = c.widget.verify();
  await flush();
  await c.widget.refresh();
  resolve(response({ ok: true, token: "stale-proof", expiresIn: 60 }));
  await verification;
  assert.equal(c.widget.state, "ready");
  assert.equal(c.widget.getToken(), "");
  cleanup(c);
});
test("late challenge response cannot replace newer challenge", async () => {
  let count = 0,
    resolve;
  const c = await setup((url) =>
    url.endsWith("init")
      ? response({ csrfToken: "csrf" })
      : ++count === 2
        ? new Promise((r) => (resolve = r))
        : response(puzzle("challenge" + count)),
  );
  const old = c.widget.refresh();
  await flush();
  await c.widget.refresh();
  resolve(response(puzzle("stale")));
  await old;
  assert.equal(c.widget.challenge.challengeId, "challenge3");
  cleanup(c);
});
test("HTML CSRF rejection clears init cache and next refresh recovers", async () => {
  let rejects = true;
  const c = await setup((url) => {
    if (url.endsWith("init")) return response({ csrfToken: "csrf" });
    if (url.endsWith("challenge") && rejects) {
      rejects = false;
      return response(null, 403, "text/html");
    }
    return response(puzzle());
  });
  assert.equal(c.widget.state, "error");
  await c.widget.refresh();
  assert.equal(c.widget.state, "ready");
  assert.equal(c.calls.filter((x) => x.url.endsWith("init")).length, 2);
  cleanup(c);
});
test("challenge expiry invalidates pending verification and clears proof", async () => {
  let resolve;
  const c = await setup((url) =>
    url.endsWith("verify")
      ? new Promise((r) => (resolve = r))
      : response(url.endsWith("init") ? { csrfToken: "csrf" } : puzzle()),
  );
  const old = c.widget.verify();
  await flush();
  const expiry = [...c.timers.values()][0];
  expiry.fn();
  assert.equal(c.widget.state, "expired");
  resolve(response({ ok: true, token: "late", expiresIn: 60 }));
  await old;
  assert.equal(c.widget.state, "expired");
  assert.equal(c.widget.getToken(), "");
  cleanup(c);
});
test("proof expiry clears hidden input and emits reset", async () => {
  const c = await setup();
  await c.widget.verify();
  let count = 0;
  c.widget.addEventListener("captcha-reset", () => count++);
  [...c.timers.values()][0].fn();
  assert.equal(c.widget.getToken(), "");
  assert.equal(c.widget.state, "expired");
  assert.equal(count, 1);
  cleanup(c);
});
test("pointer release verifies, pointercancel does not", async () => {
  const c = await setup();
  pointer(c, "pointerdown");
  pointer(c, "pointercancel");
  pointer(c, "pointerup");
  await flush();
  assert.equal(c.calls.filter((x) => x.url.endsWith("verify")).length, 0);
  pointer(c, "pointerdown");
  pointer(c, "pointerup");
  await flush();
  assert.equal(c.calls.filter((x) => x.url.endsWith("verify")).length, 1);
  cleanup(c);
});
test("network failure is recoverable through refresh", async () => {
  let fail = true;
  const c = await setup((url) => {
    if (url.endsWith("init")) return response({ csrfToken: "csrf" });
    if (fail) {
      fail = false;
      throw Error("offline");
    }
    return response(puzzle());
  });
  assert.equal(c.widget.state, "error");
  await c.widget.refresh();
  assert.equal(c.widget.state, "ready");
  cleanup(c);
});
test("detach and reinsert keeps generation monotonic and one listener set", async () => {
  const c = await setup();
  const seq = c.widget.seq;
  c.widget.remove();
  c.w.document.body.append(c.widget);
  await flush();
  assert.ok(c.widget.seq > seq);
  c.widget.range.dispatchEvent(
    new c.w.KeyboardEvent("keydown", { key: "Enter" }),
  );
  await flush();
  assert.equal(c.calls.filter((x) => x.url.endsWith("verify")).length, 1);
  cleanup(c);
});
test("two simultaneous widgets share init but keep independent challenges and IDs", async () => {
  const c = await setup();
  const second = c.w.document.createElement("nova-slider");
  c.w.document.body.append(second);
  await flush();
  assert.equal(c.calls.filter((x) => x.url.endsWith("init")).length, 1);
  assert.notEqual(
    second.querySelector(".nsc-keyboard").id,
    c.widget.querySelector(".nsc-keyboard").id,
  );
  assert.equal(second.state, "ready");
  second.remove();
  cleanup(c);
});

test("Django init_required response clears cached initialization", async () => {
  let expired = false;
  const c = await setup((url) => {
    if (url.endsWith("init")) return response({ csrfToken: "csrf" });
    if (expired) {
      expired = false;
      return response({ ok: false, code: "init_required" }, 409);
    }
    return response(puzzle());
  });
  expired = true;
  await c.widget.refresh();
  assert.equal(c.widget.state, "error");
  await c.widget.refresh();
  assert.equal(c.widget.state, "ready");
  assert.equal(c.calls.filter((x) => x.url.endsWith("init")).length, 2);
  cleanup(c);
});

test("default remains Chinese regardless of document language, including ARIA", async () => {
  const c = await setup(undefined, { documentLang: "en" });
  assert.equal(c.widget.locale, "zh-CN");
  assert.equal(c.widget.getAttribute("aria-label"), "安全验证");
  assert.equal(c.widget.lang, "zh-CN");
  assert.equal(c.widget.status.textContent, "拖动拼图，对齐图中的缺口");
  assert.equal(c.widget.range.getAttribute("aria-label"), "移动拼图块");
  assert.equal(c.widget.range.getAttribute("aria-valuetext"), "0%，按 Enter 校验");
  assert.equal(c.widget.querySelector(".nsc-background").alt, "带有一处拼图缺口的山水图案");
  assert.equal(c.widget.querySelector(".nsc").lang, "zh-CN");
  cleanup(c);
});

test("locale aliases, invalid locales, and dynamic labels retain proof and requests", async () => {
  const c = await setup(undefined, { attrs: { locale: "en-US" } });
  assert.equal(c.widget.locale, "en");
  assert.equal(c.widget.status.textContent, "Slide the piece to fit the gap");
  assert.equal(c.widget.getAttribute("aria-label"), "Security verification");
  assert.equal(c.widget.lang, "en");
  assert.equal(c.widget.range.getAttribute("aria-label"), "Move the puzzle piece");
  assert.equal(c.widget.querySelector(".nsc-refresh").getAttribute("aria-label"), "Get a new puzzle");
  c.widget.move(138);
  assert.equal(c.widget.range.getAttribute("aria-valuetext"), "50%, press Enter to verify");
  await c.widget.verify();
  const seq = c.widget.seq, count = c.calls.length, timer = [...c.timers.keys()][0];
  c.widget.setLocale("zh-Hans");
  assert.equal(c.widget.getToken(), "proof");
  assert.equal(c.widget.state, "success");
  assert.equal(c.widget.overlay.textContent, "✓ 验证通过");
  assert.equal(c.widget.seq, seq);
  assert.equal(c.calls.length, count);
  assert.equal([...c.timers.keys()][0], timer);
  for (const locale of ["", " ", "en-<script>", null, {}, 123, "__proto__"]) {
    c.widget.setLocale(locale);
    assert.equal(c.widget.locale, "zh-CN");
  }
  for (const locale of ["fr", "fr-FR", "ja", "ja-JP", "de", "ar"])
    assert.equal(c.widget.setLocale(locale), "en");
  c.widget.setAttribute("locale", "EN_gb");
  assert.equal(c.widget.locale, "en");
  assert.match(c.widget.status.textContent, /^Verified\. Valid for \d+ seconds$/);
  c.timers.get(timer).fn();
  assert.equal(c.widget.status.textContent, "Your verification expired. Please verify again.");
  cleanup(c);
});

test("custom message merge is text-only, bounded, and supports pre-upgrade properties", async () => {
  const html = '<img src=x onerror="alert(1)">';
  const c = await setup(undefined, {
    localeProperty: "en-GB", messages: { ready: html, slider_label: html, keyboard: "X".repeat(5000), unknown: html },
  });
  assert.equal(c.widget.locale, "en");
  assert.equal(c.widget.status.textContent, html);
  assert.equal(c.widget.range.getAttribute("aria-label"), html);
  assert.equal(c.widget.querySelector(".nsc-keyboard").textContent.length, 2000);
  assert.equal(c.widget.querySelectorAll("img").length, 2);
  assert.equal(c.widget.querySelectorAll("[onerror]").length, 0);
  assert.equal(c.widget.messages.unknown, undefined);
  c.widget.messages = { refresh: "Again", ready: 99, value: "{percent} {remaining} {seconds} {other}" };
  assert.equal(c.widget.status.textContent, html);
  assert.equal(c.widget.querySelector(".nsc-refresh-text").textContent, "Again");
  assert.equal(c.widget.getText("value", { percent: 1000, remaining: -1, seconds: Infinity }), "100 0 0 {other}");
  assert.equal(c.widget.getText("value", { percent: html, remaining: 1e12, seconds: 1.2 }), "0 86400 2 {other}");
  assert.equal(c.widget.getText("__proto__"), "");
  c.widget.setLocale("zh-CN");
  assert.equal(c.widget.status.textContent, html);
  c.widget.messages = null;
  assert.equal(c.widget.status.textContent, "拖动拼图，对齐图中的缺口");
  cleanup(c);
});

test("known error codes localize and use actual rate-limit retryAfter safely", async () => {
  const cases = [
    [{ code: "rate_limited", retryAfter: 7.1 }, "Too many requests. Try again in 8 seconds."],
    [{ code: "rate_limited", retryAfter: '<script>' }, "Too many requests. Please try again later."],
    [{ code: "rate_limited", retryAfter: 1e12 }, "Too many requests. Try again in 86400 seconds."],
    [{ code: "rate_limit_unavailable" }, "Verification is temporarily unavailable. Please try again later."],
    [{ code: "constructor", message: "server secret" }, "Could not generate a puzzle. Please try again."],
    [{ code: "unexpected", message: "<script>alert(1)</script>" }, "Could not generate a puzzle. Please try again."],
  ];
  for (const [body, expected] of cases) {
    const c = await setup((url) => response(url.endsWith("init") ? { csrfToken: "csrf" } : body, url.endsWith("init") ? 200 : 429), { attrs: { locale: "en" } });
    assert.equal(c.widget.state, "error");
    assert.equal(c.widget.status.textContent, expected);
    assert.equal(c.widget.overlay.textContent, expected);
    assert.doesNotMatch(c.widget.textContent, /server secret|<script>/);
    cleanup(c);
  }
});

test("initialization, JSON, and network errors never display arbitrary error messages", async () => {
  for (const mode of ["http", "csrf", "network", "json"]) {
    const c = await setup(() => {
      if (mode === "network") throw Error("secret transport details");
      if (mode === "json") return { ...response({}), json: async () => { throw Error("secret JSON details"); } };
      return response(mode === "csrf" ? {} : { message: "secret server details" }, mode === "csrf" ? 200 : 500);
    }, { attrs: { locale: "en" } });
    assert.equal(c.widget.state, "error");
    assert.equal(c.widget.status.textContent, mode === "network" ? "Connection interrupted. Please get a new puzzle and try again." : "Initialization failed. Please try again.");
    assert.doesNotMatch(c.widget.textContent, /secret/);
    c.widget.setLocale("zh-CN");
    assert.match(c.widget.status.textContent, /初始化失败|网络连接中断/);
    cleanup(c);
  }
});

test("verification retries, unknown errors, and server expiry are localized", async () => {
  let answer = { ok: false, code: "incorrect", attemptsRemaining: 3 };
  const c = await setup((url) => response(url.endsWith("init") ? { csrfToken: "csrf" } : url.endsWith("challenge") ? puzzle() : answer), { attrs: { locale: "en" } });
  await c.widget.verify();
  assert.equal(c.widget.status.textContent, "Not aligned. Try again · 3 attempts remaining");
  c.widget.locale = "zh-CN";
  assert.equal(c.widget.status.textContent, "没有对齐，再试一次 · 剩余 3 次");
  c.widget.locale = "en";
  answer = { ok: false, code: "unexpected", message: "untrusted server body" };
  await c.widget.verify();
  assert.equal(c.widget.status.textContent, "Verification failed. Please get a new puzzle.");
  await c.widget.refresh();
  answer = { ok: true, token: "proof", expiresIn: 17 };
  await c.widget.verify();
  assert.match(c.widget.status.textContent, /Valid for 1[67] seconds/);
  assert.doesNotMatch(c.widget.status.textContent, /60 seconds/);
  cleanup(c);
});

test("locale switches during pending verification preserve duplicate and late-response guards", async () => {
  let resolve;
  const c = await setup((url) => url.endsWith("verify") ? new Promise(r => resolve = r) : response(url.endsWith("init") ? { csrfToken: "csrf" } : puzzle()));
  const pending = c.widget.verify();
  await flush();
  c.widget.setLocale("en");
  assert.equal(c.widget.status.textContent, "Checking with the server…");
  c.widget.verify();
  assert.equal(c.calls.filter(x => x.url.endsWith("verify")).length, 1);
  await c.widget.refresh();
  resolve(response({ ok: true, token: "stale", expiresIn: 60 }));
  await pending;
  assert.equal(c.widget.state, "ready");
  assert.equal(c.widget.getToken(), "");
  assert.equal(c.widget.status.textContent, "Slide the piece to fit the gap");
  cleanup(c);
});

test("invalid and cross-origin endpoints localize without making requests", async () => {
  for (const [endpoint, expected] of [["https://outside.test/", "The CAPTCHA endpoint must use the same origin as this page."], ["http://[", "The CAPTCHA endpoint is invalid."]]) {
    const c = await setup(undefined, { attrs: { endpoint, locale: "en" } });
    assert.equal(c.widget.status.textContent, expected);
    assert.equal(c.calls.length, 0);
    await c.widget.refresh();
    assert.equal(c.calls.length, 0);
    c.widget.setLocale("zh-CN");
    assert.match(c.widget.status.textContent, /验证码接口/);
    cleanup(c);
  }
});

test("long translated text uses wrapping CSS rather than fixed track and button widths", async () => {
  const c = await setup(undefined, { messages: { track: "Long translated instructions ".repeat(30), refresh: "Long translated refresh label ".repeat(15) } });
  const style = c.w.document.createElement("style");
  style.textContent = readFileSync(new URL("../src/nova_slider_captcha/static/nova_slider_captcha/slider.css", import.meta.url), "utf8");
  c.w.document.head.append(style);
  assert.equal(c.w.getComputedStyle(c.widget.querySelector(".nsc")).overflowWrap, "anywhere");
  assert.equal(c.w.getComputedStyle(c.widget.querySelector(".nsc-meta")).flexWrap, "wrap");
  assert.equal(c.w.getComputedStyle(c.widget.querySelector(".nsc-refresh")).whiteSpace, "normal");
  assert.equal(c.w.getComputedStyle(c.widget.querySelector(".nsc-track-text")).position, "relative");
  assert.equal(c.w.getComputedStyle(c.widget.querySelector(".nsc-track")).minHeight, "var(--nsc-handle-size)");
  assert.equal(c.w.getComputedStyle(c.widget).getPropertyValue("--nsc-handle-size"), "48px");
  cleanup(c);
});

test("demo success ignores server messages and dynamically localizes safe result", async () => {
  const c = await setup((url) => response(url.endsWith("init") ? { csrfToken: "csrf" } : url.endsWith("challenge") ? puzzle() : url.endsWith("submit") ? { ok: true, message: '<img onerror="alert(1)">' } : { ok: true, token: "proof", expiresIn: 60 }), { attrs: { endpoint: "/captcha/", locale: "en" }, demo: true });
  await c.widget.verify();
  c.w.document.querySelector("form").dispatchEvent(new c.w.Event("submit", { cancelable: true }));
  await flush();
  assert.equal(c.w.document.querySelector("#demo-result").textContent, "Request accepted. The verification token has been used.");
  assert.equal(c.w.document.querySelector("#demo-submit").disabled, true);
  assert.equal(c.w.document.querySelectorAll("[onerror]").length, 0);
  c.widget.setLocale("zh-CN");
  assert.equal(c.w.document.querySelector("#demo-result").textContent, "请求已接受，验证凭证已使用。");
  cleanup(c);
});

test("demo rejected and interrupted requests have localized messages", async () => {
  for (const network of [false, true]) {
    const c = await setup((url) => {
      if (network && url.endsWith("submit")) throw Error("private network error");
      return response(url.endsWith("init") ? { csrfToken: "csrf" } : url.endsWith("challenge") ? puzzle() : url.endsWith("submit") ? { ok: false, message: "private response" } : { ok: true, token: "proof", expiresIn: 60 });
    }, { attrs: { endpoint: "/captcha/", locale: "en" }, demo: true });
    await c.widget.verify();
    c.w.document.querySelector("form").dispatchEvent(new c.w.Event("submit", { cancelable: true }));
    await flush();
    assert.equal(c.w.document.querySelector("#demo-result").textContent, network ? "Network error. Please try a new challenge." : "Request rejected. Please complete a new challenge.");
    assert.doesNotMatch(c.w.document.body.textContent, /private/);
    cleanup(c);
  }
});

test("refresh interrupts an old drag so its pointerup cannot submit the new puzzle", async () => {
  const c = await setup(undefined, { attrs: { locale: "en" } });
  pointer(c, "pointerdown");
  await c.widget.refresh();
  pointer(c, "pointerup");
  await flush();
  assert.equal(c.calls.filter(x => x.url.endsWith("verify")).length, 0);
  assert.equal(c.widget.state, "ready");
  assert.equal(c.widget.getToken(), "");
  cleanup(c);
});

test("a stale pointer release or cancellation cannot submit or cancel a new drag", async () => {
  const c = await setup();
  const captures = [], releases = [];
  c.widget.range.setPointerCapture = id => captures.push(id);
  c.widget.range.releasePointerCapture = id => releases.push(id);
  pointer(c, "pointerdown", 1);
  assert.equal(c.widget.activePointerId, 1);
  await c.widget.refresh();
  assert.equal(c.widget.activePointerId, null);
  assert.deepEqual(releases, [1]);
  pointer(c, "pointerdown", 2);
  pointer(c, "pointerup", 1);
  pointer(c, "pointercancel", 1);
  pointer(c, "lostpointercapture", 1);
  await flush();
  assert.equal(c.widget.activePointerId, 2);
  assert.equal(c.calls.filter(x => x.url.endsWith("verify")).length, 0);
  c.widget.setLocale("en");
  c.widget.messages = { ready: "Keep dragging" };
  assert.equal(c.widget.activePointerId, 2);
  pointer(c, "pointerup", 2);
  pointer(c, "pointerup", 2);
  await flush();
  assert.equal(c.calls.filter(x => x.url.endsWith("verify")).length, 1);
  assert.equal(c.widget.activePointerId, null);
  assert.deepEqual(captures, [1, 2]);
  assert.deepEqual(releases, [1, 2]);
  cleanup(c);
});

test("concurrent pointers cannot replace the active drag and matching cancellation releases it", async () => {
  const c = await setup();
  const releases = [];
  c.widget.range.releasePointerCapture = id => releases.push(id);
  pointer(c, "pointerdown", 10);
  pointer(c, "pointerdown", 11);
  pointer(c, "pointerup", 11);
  pointer(c, "pointercancel", 11);
  assert.equal(c.widget.activePointerId, 10);
  pointer(c, "pointercancel", 10);
  pointer(c, "pointerup", 10);
  await flush();
  assert.equal(c.widget.activePointerId, null);
  assert.equal(c.calls.filter(x => x.url.endsWith("verify")).length, 0);
  assert.deepEqual(releases, [10]);
  pointer(c, "pointerdown", 12);
  pointer(c, "lostpointercapture", 12);
  pointer(c, "pointerup", 12);
  await flush();
  assert.equal(c.calls.filter(x => x.url.endsWith("verify")).length, 0);
  assert.equal(c.widget.activePointerId, null);
  cleanup(c);
});

test("expiry, keyboard checking, and disconnect release active pointer capture", async () => {
  const c = await setup();
  const releases = [];
  c.widget.range.releasePointerCapture = id => releases.push(id);
  pointer(c, "pointerdown", 20);
  [...c.timers.values()][0].fn();
  assert.equal(c.widget.activePointerId, null);
  assert.deepEqual(releases, [20]);
  pointer(c, "pointerdown", 21);
  assert.equal(c.widget.activePointerId, null);
  await c.widget.refresh();
  pointer(c, "pointerdown", 22);
  await c.widget.verify();
  assert.equal(c.widget.activePointerId, null);
  assert.deepEqual(releases, [20, 22]);
  await c.widget.refresh();
  pointer(c, "pointerdown", 23);
  c.widget.remove();
  assert.equal(c.widget.activePointerId, null);
  assert.deepEqual(releases, [20, 22, 23]);
  c.w.document.body.append(c.widget);
  await flush();
  pointer(c, "pointerup", 23);
  await flush();
  assert.equal(c.calls.filter(x => x.url.endsWith("verify")).length, 1);
  assert.equal(c.widget.state, "ready");
  cleanup(c);
});

test("nondefault geometry controls max, piece position, ratio and ARIA", async () => {
  const c = await setup(url => response(url.endsWith("init") ? { csrfToken: "csrf" } : url.endsWith("challenge")
    ? { ...puzzle(), width: 480, height: 240, pieceWidth: 60, pieceY: 90 }
    : { ok: true, token: "proof", expiresIn: 60 }), { attrs: { locale: "en", "field-name": "form-2-proof", purpose: "contact" } });
  const { widget } = c;
  assert.equal(widget.state, "ready");
  assert.equal(widget.maxX, 420);
  assert.equal(widget.range.max, "420");
  assert.equal(widget.querySelector(".nsc-image").style.aspectRatio, "480 / 240");
  assert.equal(widget.querySelector(".nsc-piece").style.width, "12.5%");
  assert.equal(widget.querySelector(".nsc-piece").style.top, "37.5%");
  widget.move(210);
  assert.equal(widget.range.value, "210");
  assert.equal(widget.querySelector(".nsc-piece").style.left, "43.75%");
  assert.equal(widget.range.getAttribute("aria-valuetext"), "50%, press Enter to verify");
  assert.match(widget.querySelector(".nsc-handle").style.left, /var\(--nsc-handle-size\)/);
  widget.setLocale("zh-CN");
  assert.equal(widget.range.getAttribute("aria-valuetext"), "50%，按 Enter 校验");
  widget.move(Infinity);
  assert.equal(widget.x, 0);
  widget.move(1000);
  assert.equal(widget.x, 420);
  assert.equal(widget.querySelector(".nsc-piece").style.left, "87.5%");
  await widget.verify();
  assert.equal(JSON.parse(c.calls.find(call => call.url.endsWith("verify")).options.body).x, 420);
  const form = c.w.document.createElement("form");
  c.w.document.body.append(form);
  form.append(widget); // Reconnect initializes a fresh, empty proof.
  await flush();
  await widget.verify();
  assert.equal(new c.w.FormData(form).get("form-2-proof"), "proof");
  assert.equal(new c.w.FormData(form).has("nova_slider_token"), false);
  cleanup(c);
});

test("invalid or hostile geometry fails closed before image loading or verification", async () => {
  const invalid = [
    { width: 0 }, { width: -1 }, { width: "320" }, { width: null }, { width: Infinity }, { width: NaN },
    { width: 1e100 }, { width: 8193 }, { width: {} }, { height: 0 }, { height: "160" }, { height: [] },
    { height: true }, { height: 10.5 }, { pieceWidth: 0 }, { pieceWidth: 320 }, { pieceWidth: 161 },
    { pieceWidth: "44" }, { pieceWidth: -44 }, { pieceWidth: NaN }, { pieceY: -1 }, { pieceY: 117 },
    { pieceY: "56" }, { pieceY: Infinity }, { pieceY: null }, { width: undefined },
  ];
  for (const geometry of invalid) {
    const c = await setup(url => response(url.endsWith("init") ? { csrfToken: "csrf" } : { ...puzzle(), ...geometry }), { images: imageEvents });
    assert.equal(c.widget.state, "error", JSON.stringify(geometry));
    assert.equal(c.widget.range.disabled, true);
    assert.equal(c.widget.getToken(), "");
    assert.equal(c.images.images.length, 0);
    await c.widget.verify();
    assert.equal(c.calls.some(call => call.url.endsWith("verify")), false);
    cleanup(c);
  }
});

test("two widgets submit distinct configurable hidden field names safely", async () => {
  const c = await setup(undefined, { demo: true, attrs: { "field-name": 'form-0-proof"<x>' } });
  const second = c.w.document.createElement("nova-slider");
  second.setAttribute("field-name", "form-1-proof");
  c.w.document.querySelector("form").append(second);
  await flush();
  await c.widget.verify();
  await second.verify();
  const data = new c.w.FormData(c.w.document.querySelector("form"));
  assert.equal(data.getAll('form-0-proof"<x>').length, 1);
  assert.equal(data.get('form-0-proof"<x>'), "proof");
  assert.equal(data.get("form-1-proof"), "proof");
  assert.equal(c.w.document.querySelectorAll("x").length, 0);
  cleanup(c);
});

test("theme fallback contracts retain explicit appearance and semantic host overrides", async () => {
  const css = readFileSync(new URL("../src/nova_slider_captcha/static/nova_slider_captcha/slider.css", import.meta.url), "utf8");
  assert.match(css, /@media\s*\(prefers-color-scheme:\s*dark\)/);
  assert.match(css, /:root:not\(\[data-theme="light"\]\)/);
  assert.match(css, /:root\[data-theme="dark"\]/);
  assert.match(css, /:root\[data-theme="light"\], \.nova-mode-light/);
  assert.match(css, /:where\(\.nova-mode-dark\)/);
  assert.match(css, /--nsc-accent:\s*var\(--link-fg,\s*var\(--accent,/);
  assert.match(css, /--nsc-error:\s*var\(--error-fg,\s*var\(--danger,/);
  assert.doesNotMatch(css, /color:\s*var\(--mint/);
  assert.match(css, /\.nsc\[data-state="expired"\] \.nsc-overlay\s*\{[^}]*background:\s*var\(--nsc-panel\);[^}]*color:\s*var\(--nsc-error\);/);
  const c = await setup();
  const style = c.w.document.createElement("style");
  style.textContent = css;
  c.w.document.head.append(style);
  c.widget.style.setProperty("--nsc-success", "#123456");
  assert.equal(c.w.getComputedStyle(c.widget).getPropertyValue("--nsc-success"), "#123456");
  cleanup(c);
});

test("default light and dark state palettes meet text contrast on fallback surfaces", () => {
  const css = readFileSync(new URL("../src/nova_slider_captcha/static/nova_slider_captcha/slider.css", import.meta.url), "utf8");
  const palettes = [...css.matchAll(/--nsc-fallback-accent:[\s\S]*?--nsc-fallback-error:\s*(#[0-9a-f]+);/g)]
    .slice(0, 2).map(match => Object.fromEntries([...match[0].matchAll(/--nsc-fallback-([a-z]+):\s*(#[0-9a-f]+);/g)].map(item => [item[1], item[2]])));
  const luminance = hex => {
    if (hex.length === 4) hex = "#" + [...hex.slice(1)].map(v => v + v).join("");
    const rgb = hex.slice(1).match(/../g).map(v => parseInt(v, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  };
  const ratio = (a, b) => (Math.max(luminance(a), luminance(b)) + .05) / (Math.min(luminance(a), luminance(b)) + .05);
  assert.equal(palettes.length, 2);
  for (const palette of palettes) {
    for (const role of ["muted", "text", "success", "error"]) {
      for (const surface of ["panel", "handle"])
        assert.ok(ratio(palette[role], palette[surface]) >= 4.5, `${role}/${surface} ${JSON.stringify(palette)}`);
    }
  }
  const successPanel = css.match(/--nsc-success-panel:\s*(#[0-9a-f]+);/)[1];
  const successText = css.match(/--nsc-success-text:\s*(#[0-9a-f]+);/)[1];
  assert.ok(ratio(successText, successPanel) >= 4.5);
  // Native Django's error token has little margin on a translucent overlay;
  // the opaque-panel contract above isolates it from arbitrary puzzle pixels.
  assert.ok(ratio("#e35f5f", "#212121") >= 4.5);
  assert.ok(ratio("#ba2121", "#f8f8f8") >= 4.5);
});

test("host alternative links outside the component survive render and refresh", async () => {
  const c = await setup();
  const wrapper = c.w.document.createElement("div");
  wrapper.className = "nova-slider-form-widget";
  const link = c.w.document.createElement("a");
  link.href = "/security/other/";
  link.textContent = "Use another secure method";
  c.w.document.body.append(wrapper);
  wrapper.append(c.widget, link);
  await flush();
  await c.widget.verify();
  await c.widget.refresh();
  assert.equal(wrapper.querySelector("a"), link);
  assert.equal(link.href, "https://demo.test/security/other/");
  assert.equal(link.closest("noscript"), null);
  assert.equal(link.closest("nova-slider"), null);
  cleanup(c);
});

test("explicit unsupported locales use English through attributes and property entry points", async () => {
  for (const locale of ["fr", "fr-FR", "ja", "ja-JP", "de", "ar"]) {
    for (const options of [{ attrs: { locale } }, { localeProperty: locale }]) {
      const c = await setup(undefined, options);
      assert.equal(c.widget.locale, "en", locale);
      assert.equal(c.widget.lang, "en");
      assert.equal(c.widget.querySelector(".nsc").lang, "en");
      assert.equal(c.widget.getAttribute("aria-label"), "Security verification");
      assert.equal(c.widget.range.getAttribute("aria-label"), "Move the puzzle piece");
      assert.equal(c.widget.status.textContent, "Slide the piece to fit the gap");
      assert.equal(c.widget.querySelector(".nsc-background").alt, "Landscape with a missing puzzle piece");
      c.widget.move(138);
      assert.equal(c.widget.range.getAttribute("aria-valuetext"), "50%, press Enter to verify");
      cleanup(c);
    }
  }
});

test("locale grammar keeps Chinese defaults and aliases without claiming BCP47 validation", async () => {
  const c = await setup();
  for (const value of [undefined, null, true, 123, {}, [], "", " \t ", "e", "en--US", "fr FR", "-ja", "en-123456789", "__proto__"]) {
    c.widget.locale = value;
    assert.equal(c.widget.locale, "zh-CN", String(value));
  }
  for (const value of ["zh", "zh-CN", "zh_Hans", "zh-Hant", "zh-TW", " ZH_hant_TW "]) {
    assert.equal(c.widget.setLocale(value), "zh-CN", value);
    assert.equal(c.widget.getAttribute("aria-label"), "安全验证");
  }
  for (const value of ["en", "en-US", "EN_gb", "fr_Latn_FR", " ja-JP "])
    assert.equal(c.widget.setLocale(value), "en", value);
  cleanup(c);
});

test("unsupported-language switches retain proof, requests, generation and exact expiry callback", async () => {
  const c = await setup();
  await c.widget.verify();
  const proof = c.widget.getToken(), seq = c.widget.seq, calls = c.calls.length;
  const [timerId, timer] = [...c.timers.entries()][0];
  for (const change of [() => c.widget.setAttribute("locale", "fr-FR"), () => { c.widget.locale = "ja-JP"; }, () => c.widget.setLocale("ar")]) {
    change();
    assert.equal(c.widget.locale, "en");
    assert.match(c.widget.status.textContent, /^Verified\. Valid for \d+ seconds$/);
    assert.equal(c.widget.overlay.textContent, "✓ Verified");
    assert.equal(c.widget.getToken(), proof);
    assert.equal(c.widget.seq, seq);
    assert.equal(c.calls.length, calls);
    assert.equal(c.timers.size, 1);
    assert.equal(c.timers.get(timerId), timer);
  }
  timer.fn();
  assert.equal(c.widget.getToken(), "");
  assert.equal(c.widget.state, "expired");
  assert.equal(c.widget.status.textContent, "Your verification expired. Please verify again.");
  cleanup(c);
});
