import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { handleCaptcha } from "../captcha.mjs";
import { makePuzzle } from "../puzzle.mjs";
class D1 {
  constructor() {
    this.db = new DatabaseSync(":memory:");
    this.db.exec(
      readFileSync(
        new URL("../schema.sql", import.meta.url),
        "utf8",
      ),
    );
  }
  prepare(sql) {
    const statement = this.db.prepare(sql);
    return {
      bind(...args) {
        return {
          first: async () => statement.get(...args) || null,
          run: async () => statement.run(...args),
        };
      },
      first: async () => statement.get() || null,
    };
  }
  async batch(items) {
    return Promise.all(items.map((x) => x.run()));
  }
}
async function ctx() {
  const db = new D1(),
    now = Date.now();
  const req = () => new Request("https://demo.test/captcha/init");
  const r = await handleCaptcha(req(), db, "init", now),
    { csrfToken } = await r.json(),
    cookie = r.headers.get("set-cookie").split(";")[0];
  const post = async (action, body, opts = {}) => {
    const request = new Request("https://demo.test/captcha/" + action, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        origin: "https://demo.test",
        cookie,
        "x-csrftoken": csrfToken,
        ...opts.headers,
      },
      body: typeof body === "string" ? body : JSON.stringify(body),
    });
    const response = await handleCaptcha(request, db, action, opts.now ?? now);
    return { status: response.status, ...(await response.json()) };
  };
  const issue = () => post("challenge", { purpose: "demo" });
  const answer = (id) =>
    db.db.prepare("SELECT answer FROM captcha_challenges WHERE id=?").get(id)
      .answer;
  return { db, now, csrfToken, cookie, post, issue, answer };
}
test("contract: opaque challenge raster images and exact dimensions", async () => {
  const c = await ctx(),
    p = await c.issue();
  assert.equal(p.status, 200);
  assert.deepEqual(
    Object.keys(p).sort(),
    [
      "status",
      "challengeId",
      "background",
      "piece",
      "pieceY",
      "width",
      "height",
      "pieceWidth",
      "expiresIn",
      "maxAttempts",
    ].sort(),
  );
  assert.equal(p.width, 320);
  assert.equal(p.height, 160);
  assert.equal(p.pieceWidth, 44);
  assert.equal(p.expiresIn, 120);
  assert.match(p.background, /^data:image\/png;base64,iVBOR/);
  assert.equal(JSON.stringify(p).includes("answer"), false);
});
test("solve + purpose-bound single-use business consumption", async () => {
  const c = await ctx(),
    p = await c.issue();
  const proof = await c.post("verify", {
    challengeId: p.challengeId,
    x: c.answer(p.challengeId),
  });
  assert.equal(proof.ok, true);
  assert.equal(
    (await c.post("submit", { token: proof.token, purpose: "login" })).ok,
    false,
  );
  assert.equal(
    (await c.post("submit", { token: proof.token, purpose: "demo" })).ok,
    true,
  );
  assert.equal(
    (await c.post("submit", { token: proof.token, purpose: "demo" })).status,
    409,
  );
});
test("five wrong attempts then challenge locked", async () => {
  const c = await ctx(),
    p = await c.issue();
  for (let i = 4; i >= 0; i--) {
    const r = await c.post("verify", { challengeId: p.challengeId, x: 0 });
    assert.equal(r.code, "incorrect");
    assert.equal(r.attemptsRemaining, i);
  }
  assert.equal(
    (
      await c.post("verify", {
        challengeId: p.challengeId,
        x: c.answer(p.challengeId),
      })
    ).status,
    409,
  );
});
test("tolerance 4 inclusive and 5 exclusive", async () => {
  const c = await ctx(),
    p = await c.issue(),
    x = c.answer(p.challengeId);
  assert.equal(
    (await c.post("verify", { challengeId: p.challengeId, x: x + 5 })).ok,
    false,
  );
  assert.equal(
    (await c.post("verify", { challengeId: p.challengeId, x: x + 4 })).ok,
    true,
  );
});
test("session and CSRF boundaries", async () => {
  const c = await ctx(),
    p = await c.issue(),
    x = c.answer(p.challengeId);
  for (const headers of [
    { origin: "https://evil.test" },
    { "x-csrftoken": "bad" },
    { cookie: "" },
    { "sec-fetch-site": "cross-site" },
  ])
    assert.equal(
      (await c.post("verify", { challengeId: p.challengeId, x }, { headers }))
        .status,
      403,
    );
  const other = await handleCaptcha(
    new Request("https://demo.test/captcha/init"),
    c.db,
    "init",
    c.now,
  );
  const csrf = await other.json(),
    cookie = other.headers.get("set-cookie").split(";")[0];
  assert.equal(
    (
      await c.post(
        "verify",
        { challengeId: p.challengeId, x },
        { headers: { cookie, "x-csrftoken": csrf.csrfToken } },
      )
    ).status,
    409,
  );
});
test("expiry of challenges, tokens and sessions", async () => {
  const c = await ctx(),
    p = await c.issue();
  assert.equal(
    (
      await c.post(
        "verify",
        { challengeId: p.challengeId, x: c.answer(p.challengeId) },
        { now: c.now + 120001 },
      )
    ).status,
    409,
  );
  const q = await c.issue(),
    proof = await c.post("verify", {
      challengeId: q.challengeId,
      x: c.answer(q.challengeId),
    });
  assert.equal(
    (
      await c.post(
        "submit",
        { token: proof.token, purpose: "demo" },
        { now: c.now + 60001 },
      )
    ).status,
    409,
  );
  assert.equal(
    (await c.post("challenge", { purpose: "demo" }, { now: c.now + 1800001 }))
      .status,
    403,
  );
});
test("parallel success issues a single proof; parallel submit consumes once", async () => {
  const c = await ctx(),
    p = await c.issue(),
    payload = { challengeId: p.challengeId, x: c.answer(p.challengeId) };
  const rs = await Promise.all(
    Array.from({ length: 8 }, () => c.post("verify", payload)),
  );
  assert.equal(rs.filter((x) => x.ok).length, 1);
  const token = rs.find((x) => x.ok).token;
  const business = await Promise.all(
    Array.from({ length: 8 }, () =>
      c.post("submit", { token, purpose: "demo" }),
    ),
  );
  assert.equal(business.filter((x) => x.ok).length, 1);
});
test("parallel wrong attempts never exceed five", async () => {
  const c = await ctx(),
    p = await c.issue();
  const rs = await Promise.all(
    Array.from({ length: 12 }, () =>
      c.post("verify", { challengeId: p.challengeId, x: 0 }),
    ),
  );
  assert.equal(rs.filter((x) => x.code === "incorrect").length, 5);
  assert.equal(
    c.db.db
      .prepare("SELECT attempts FROM captcha_challenges WHERE id=?")
      .get(p.challengeId).attempts,
    5,
  );
});
test("challenge issuance rate limited per session", async () => {
  const c = await ctx();
  for (let i = 0; i < 15; i++) assert.equal((await c.issue()).status, 200);
  assert.equal((await c.issue()).status, 429);
});
test("session creation rate limited by trusted edge IP", async () => {
  const c = await ctx();
  for (let i = 0; i < 40; i++) {
    const r = await handleCaptcha(
      new Request("https://demo.test/captcha/init", {
        headers: { "cf-connecting-ip": "192.0.2.1" },
      }),
      c.db,
      "init",
      c.now,
    );
    assert.equal(r.status, 200);
  }
  const r = await handleCaptcha(
    new Request("https://demo.test/captcha/init", {
      headers: { "cf-connecting-ip": "192.0.2.1" },
    }),
    c.db,
    "init",
    c.now,
  );
  assert.equal(r.status, 429);
});
test("malformed inputs, giant numbers and bounded bodies fail closed", async () => {
  const c = await ctx(),
    p = await c.issue();
  for (const x of [null, "10", {}, -1, 277, 1e100])
    assert.equal(
      (await c.post("verify", { challengeId: p.challengeId, x })).status,
      400,
    );
  for (const body of [
    "{",
    "[]",
    "null",
    JSON.stringify({ a: "x".repeat(2100) }),
  ])
    assert.equal((await c.post("challenge", body)).status, 400);
});
test("multiple challenges do not invalidate another tab", async () => {
  const c = await ctx(),
    a = await c.issue(),
    b = await c.issue();
  assert.equal(
    (
      await c.post("verify", {
        challengeId: a.challengeId,
        x: c.answer(a.challengeId),
      })
    ).ok,
    true,
  );
  assert.equal(
    (
      await c.post("verify", {
        challengeId: b.challengeId,
        x: c.answer(b.challengeId),
      })
    ).ok,
    true,
  );
});
test("PNG contains no plaintext answer metadata", () => {
  const p = makePuzzle(121, 55);
  const bytes = Buffer.from(p.background.split(",")[1], "base64");
  assert.equal(bytes.readUInt32BE(16), 320);
  assert.equal(bytes.readUInt32BE(20), 160);
  assert.equal(bytes.includes(Buffer.from("tEXt")), false);
  assert.equal(bytes.includes(Buffer.from("answer")), false);
});
