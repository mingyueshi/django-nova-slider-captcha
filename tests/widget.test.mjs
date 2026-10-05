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
async function setup(handler) {
  const dom = new JSDOM("<!doctype html><body></body>", {
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
  w.eval(script);
  const widget = w.document.createElement("nova-slider");
  w.document.body.append(widget);
  await flush();
  return { w, dom, widget, calls, timers };
}
function cleanup(c) {
  c.widget.remove();
  c.dom.window.close();
}
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
  c.widget.range.dispatchEvent(new c.w.Event("pointerdown"));
  c.widget.range.dispatchEvent(new c.w.Event("pointercancel"));
  c.widget.range.dispatchEvent(new c.w.Event("pointerup"));
  await flush();
  assert.equal(c.calls.filter((x) => x.url.endsWith("verify")).length, 0);
  c.widget.range.dispatchEvent(new c.w.Event("pointerdown"));
  c.widget.range.dispatchEvent(new c.w.Event("pointerup"));
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
