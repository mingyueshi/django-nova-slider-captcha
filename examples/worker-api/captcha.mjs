import { makePuzzle } from "./puzzle.mjs";
const SID = "nova_captcha_session",
  SESSION_TTL = 1800000;
const random = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(32)), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
const sha = async (s) =>
  Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)),
    ),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
export const headers = {
  "Cache-Control": "no-store, max-age=0",
  Pragma: "no-cache",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
};
const json = (value, status = 200, extra = {}) =>
  Response.json(value, { status, headers: { ...headers, ...extra } });
const fail = (code, status = 400, extra = {}) =>
  json({ ok: false, code, ...extra }, status);
function cookie(req) {
  return (
    req.headers
      .get("cookie")
      ?.split(";")
      .map((x) => x.trim())
      .find((x) => x.startsWith(SID + "="))
      ?.slice(SID.length + 1) || ""
  );
}
async function rate(db, key, max, now) {
  const bucket = Math.floor(now / 60000),
    id = key + ":" + bucket;
  const r = await db
    .prepare(
      "INSERT INTO captcha_rates (id,count,expires) VALUES (?,1,?) ON CONFLICT(id) DO UPDATE SET count=count+1 RETURNING count",
    )
    .bind(id, now + 120000)
    .first();
  return r.count <= max;
}
async function session(req, db, now) {
  const sid = cookie(req);
  if (!/^[a-f0-9]{64}$/.test(sid)) return null;
  return await db
    .prepare("SELECT * FROM captcha_sessions WHERE id=? AND expires>?")
    .bind(await sha(sid), now)
    .first();
}
async function readJson(req) {
  if (!req.headers.get("content-type")?.startsWith("application/json"))
    throw Error("format");
  if (Number(req.headers.get("content-length") || 0) > 2048)
    throw Error("size");
  const reader = req.body?.getReader();
  if (!reader) throw Error("format");
  let text = "",
    size = 0;
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 2048) {
        await reader.cancel();
        throw Error("size");
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
  } finally {
    reader.releaseLock();
  }
  const data = JSON.parse(text);
  if (!data || Array.isArray(data) || typeof data !== "object")
    throw Error("format");
  return data;
}
export async function handleCaptcha(req, db, action, now = Date.now()) {
  if (!db) return fail("unavailable", 503);
  try {
    if (action === "init" && req.method === "GET") {
      let sess = await session(req, db, now);
      if (sess) return json({ csrfToken: sess.csrf });
      const ip = req.headers.get("cf-connecting-ip");
      if (ip && !(await rate(db, "init:" + (await sha(ip)), 40, now)))
        return fail("rate_limited", 429, { retryAfter: 60 });
      await db.batch([
        db.prepare("DELETE FROM captcha_sessions WHERE expires<?").bind(now),
        db.prepare("DELETE FROM captcha_rates WHERE expires<?").bind(now),
      ]);
      const sid = random(),
        csrf = random();
      await db
        .prepare("INSERT INTO captcha_sessions(id,csrf,expires) VALUES (?,?,?)")
        .bind(await sha(sid), csrf, now + SESSION_TTL)
        .run();
      return json({ csrfToken: csrf }, 200, {
        "Set-Cookie": `${SID}=${sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age=1800${new URL(req.url).protocol === "https:" ? "; Secure" : ""}`,
      });
    }
    if (req.method !== "POST") return fail("method_not_allowed", 405);
    if (
      req.headers.get("origin") !== new URL(req.url).origin ||
      req.headers.get("sec-fetch-site") === "cross-site"
    )
      return fail("csrf_failed", 403);
    const sess = await session(req, db, now);
    if (!sess) return fail("session_expired", 403);
    if (req.headers.get("x-csrftoken") !== sess.csrf)
      return fail("csrf_failed", 403);
    const body = await readJson(req);
    // Bound storage lifetime; no raw IP address or movement trail is retained.
    await db.batch([
      db
        .prepare("DELETE FROM captcha_challenges WHERE expires<?")
        .bind(now - 60000),
      db.prepare("DELETE FROM captcha_rates WHERE expires<?").bind(now),
      db.prepare("DELETE FROM captcha_sessions WHERE expires<?").bind(now),
    ]);
    if (action === "challenge") {
      if (!["demo", "login"].includes(body.purpose))
        return fail("invalid_purpose");
      const ip = req.headers.get("cf-connecting-ip");
      if (
        !(await rate(db, "issue:" + sess.id, 15, now)) ||
        (ip && !(await rate(db, "ip:" + (await sha(ip)), 120, now)))
      )
        return fail("rate_limited", 429, { retryAfter: 60 });
      const p = makePuzzle(),
        id = random();
      await db
        .prepare(
          "INSERT INTO captcha_challenges(id,session,purpose,answer,expires) VALUES (?,?,?,?,?)",
        )
        .bind(id, sess.id, body.purpose, p.answer, now + 120000)
        .run();
      const { answer, ...publicPuzzle } = p;
      return json({
        challengeId: id,
        ...publicPuzzle,
        expiresIn: 120,
        maxAttempts: 5,
      });
    }
    if (action === "verify") {
      if (
        typeof body.challengeId !== "string" ||
        !/^[a-f0-9]{64}$/.test(body.challengeId) ||
        typeof body.x !== "number" ||
        !Number.isFinite(body.x) ||
        body.x < 0 ||
        body.x > 276
      )
        return fail("invalid_input");
      const ip = req.headers.get("cf-connecting-ip");
      if (
        !(await rate(db, "verify:" + sess.id, 60, now)) ||
        (ip && !(await rate(db, "verify-ip:" + (await sha(ip)), 240, now)))
      )
        return fail("rate_limited", 429, { retryAfter: 60 });
      const token = random(),
        digest = await sha(token);
      const row = await db
        .prepare(
          "UPDATE captcha_challenges SET attempts=attempts+1, solved=CASE WHEN ABS(answer-?)<=4 THEN 1 ELSE 0 END, token=CASE WHEN ABS(answer-?)<=4 THEN ? ELSE NULL END, token_expires=CASE WHEN ABS(answer-?)<=4 THEN ? ELSE NULL END WHERE id=? AND session=? AND expires>? AND attempts<5 AND solved=0 RETURNING solved,attempts",
        )
        .bind(
          body.x,
          body.x,
          digest,
          body.x,
          now + 60000,
          body.challengeId,
          sess.id,
          now,
        )
        .first();
      if (!row) return fail("challenge_unavailable", 409);
      if (row.solved) return json({ ok: true, token, expiresIn: 60 });
      return fail("incorrect", 422, { attemptsRemaining: 5 - row.attempts });
    }
    if (action === "submit") {
      if (
        body.purpose !== "demo" ||
        typeof body.token !== "string" ||
        !/^[a-f0-9]{64}$/.test(body.token)
      )
        return fail("invalid_token");
      const row = await db
        .prepare(
          "UPDATE captcha_challenges SET used=1 WHERE token=? AND session=? AND purpose=? AND solved=1 AND used=0 AND token_expires>? RETURNING id",
        )
        .bind(await sha(body.token), sess.id, body.purpose, now)
        .first();
      if (!row) return fail("invalid_or_used_token", 409);
      return json({
        ok: true,
        message: "服务端已接受这次演示提交；验证凭证已消费。",
      });
    }
    return fail("not_found", 404);
  } catch (e) {
    if (e instanceof SyntaxError || ["format", "size"].includes(e.message))
      return fail("invalid_input");
    console.error("Captcha operation unavailable");
    return fail("unavailable", 503);
  }
}
