import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { handleCaptcha } from "../captcha.mjs";
import { makePuzzle } from "../puzzle.mjs";
import {claimRate,claimQuotas} from "../rate-limit.mjs";
class D1 {
  constructor() {
    this.db = new DatabaseSync(":memory:");
    this.db.exec(
      readFileSync(
        new URL("../schema.sql", import.meta.url),
        "utf8",
      ),
    );
    this.db.exec(readFileSync(new URL('../migrations-0002-gcra.sql',import.meta.url),'utf8'));
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
  const c=await ctx(),a=await c.issue(),b=await c.issue();
  const proof=await c.post('verify',{challengeId:b.challengeId,x:c.answer(b.challengeId)});
  assert.equal(proof.ok,true);
  assert.equal((await c.post('submit',{token:proof.token,purpose:'demo'},{now:c.now+60001})).status,409);
  assert.equal((await c.post('verify',{challengeId:a.challengeId,x:c.answer(a.challengeId)},{now:c.now+120001})).status,409);
  assert.equal((await c.post('challenge',{purpose:'demo'},{now:c.now+1800001})).status,403);
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

const quotaKey=(name='issue',char='a')=>name+':'+char.repeat(64);
test('GCRA blocks minute-boundary double burst and admits exact refill',async()=>{
 const db=new D1(),key=quotaKey(),t=59999.999;
 for(let i=0;i<3;i++)assert.equal((await claimRate(db,key,3,t)).allowed,true);
 const before=db.db.prepare('SELECT * FROM captcha_rate_state WHERE id=?').get(key);
 assert.deepEqual(await claimRate(db,key,3,60000.001),{allowed:false,retryAfter:20});
 assert.deepEqual(db.db.prepare('SELECT * FROM captcha_rate_state WHERE id=?').get(key),before);
 assert.equal((await claimRate(db,key,3,79999.998)).allowed,false);
 assert.equal((await claimRate(db,key,3,79999.999)).allowed,true);
 assert.equal((await claimRate(db,key,3,79999.999)).allowed,false);
});
test('GCRA concurrency claims at most configured capacity',async()=>{
 const db=new D1(),key=quotaKey();
 const r=await Promise.all(Array.from({length:24},()=>claimRate(db,key,5,1000)));
 assert.equal(r.filter(x=>x.allowed).length,5);
 assert.equal(db.db.prepare('SELECT tat_us FROM captcha_rate_state WHERE id=?').get(key).tat_us,61000000);
});
test('backwards clock cannot reset debt and rejected requests do not extend it',async()=>{
 const db=new D1(),key=quotaKey();await claimRate(db,key,1,90000);
 const tat=db.db.prepare('SELECT tat_us FROM captcha_rate_state WHERE id=?').get(key).tat_us;
 assert.deepEqual(await claimRate(db,key,1,30000),{allowed:false,retryAfter:120});
 assert.equal(db.db.prepare('SELECT tat_us FROM captcha_rate_state WHERE id=?').get(key).tat_us,tat);
 assert.equal((await claimRate(db,key,1,150000)).allowed,true);
});
test('fractional refill rounds toward stricter rate; invalid configs fail closed',async()=>{
 const db=new D1(),key=quotaKey();
 for(let i=0;i<7;i++)assert.equal((await claimRate(db,key,7,0)).allowed,true);
 assert.equal(db.db.prepare('SELECT tat_us FROM captcha_rate_state WHERE id=?').get(key).tat_us,60000003);
 for(const n of [0,-1,1.5,60001,NaN,Infinity,'3'])await assert.rejects(()=>claimRate(db,key,n,0),TypeError);
 for(const t of [-1,Infinity,NaN,Number.MAX_SAFE_INTEGER])await assert.rejects(()=>claimRate(db,key,3,t),TypeError);
});
test('legacy active fixed window inherits cooldown without reopening quota',async()=>{
 const db=new D1(),key=quotaKey();
 db.db.prepare('INSERT INTO captcha_rates(id,count,expires) VALUES (?,?,?)').run(key+':1',3,180000);
 db.db.prepare('INSERT INTO captcha_rates(id,count,expires) VALUES (?,?,?)').run(key+':2',1,210000);
 assert.deepEqual(await claimRate(db,key,3,90000),{allowed:false,retryAfter:120});
 assert.equal((await claimRate(db,key,3,209999.999)).allowed,false);
 assert.equal((await claimRate(db,key,3,210000)).allowed,true);
});
test('stable IP quota is shared by new sessions; retry accounts for charged IP',async()=>{
 const db=new D1(),ip=quotaKey('ip'),sess1=quotaKey('issue','b'),sess2=quotaKey('issue','c');
 assert.equal((await claimQuotas(db,[[ip,1],[sess1,1]],0)).allowed,true);
 assert.equal((await claimQuotas(db,[[ip,1],[sess2,1]],0)).allowed,false);
 const db2=new D1();await claimRate(db2,sess1,1,0);
 assert.deepEqual(await claimQuotas(db2,[[ip,1],[sess1,1]],30000),{allowed:false,retryAfter:60});
 assert.equal((await claimRate(db2,quotaKey('verify','b'),1,30000)).allowed,true);
});
test('cleanup only removes fully replenished states; pruning never grants while debt remains',async()=>{
 const db=new D1(),key=quotaKey();await claimRate(db,key,2,1000);
 db.db.prepare('DELETE FROM captcha_rate_state WHERE tat_us<=? AND blocked_until_us<=?').run(1000000,1000000);
 assert.equal(db.db.prepare('SELECT count(*) AS n FROM captcha_rate_state').get().n,1);
 db.db.prepare('DELETE FROM captcha_rate_state WHERE tat_us<=? AND blocked_until_us<=?').run(31000000,31000000);
 assert.equal(db.db.prepare('SELECT count(*) AS n FROM captcha_rate_state').get().n,0);
 assert.equal((await claimRate(db,key,2,31000)).allowed,true);
});
test('HTTP rate-limited responses carry computed Retry-After and machine code',async()=>{
 const c=await ctx();for(let i=0;i<15;i++)await c.issue();
 const r=await handleCaptcha(new Request('https://demo.test/captcha/challenge',{method:'POST',headers:{'Content-Type':'application/json',Origin:'https://demo.test',Cookie:c.cookie,'X-CSRFToken':c.csrfToken},body:JSON.stringify({purpose:'demo'})}),c.db,'challenge',c.now);
 assert.equal(r.status,429);assert.equal(r.headers.get('Retry-After'),'4');
 assert.deepEqual(await r.json(),{ok:false,code:'rate_limited',retryAfter:4});
});
test('database limiter failure returns stable unavailable response, never a challenge',async()=>{
 const c=await ctx();c.db.db.exec('DROP TABLE captcha_rate_state');
 assert.equal((await c.issue()).status,503);
});

test('shared Django/Worker fixture agrees at each microsecond boundary',async()=>{
 const fixture=JSON.parse(readFileSync(new URL('../../../tests/fixtures/gcra.json',import.meta.url),'utf8'));
 const db=new D1(),key=quotaKey();
 for(const step of fixture.steps){
  assert.deepEqual(await claimRate(db,key,fixture.capacity,step.nowUs/1000),{allowed:step.allowed,retryAfter:step.retryAfter});
  assert.equal(db.db.prepare('SELECT tat_us FROM captcha_rate_state WHERE id=?').get(key).tat_us,step.tatUs);
 }
});
test('changing purpose does not reset the shared issuance quota',async()=>{
 const c=await ctx();for(let i=0;i<15;i++)await c.issue();
 assert.equal((await c.post('challenge',{purpose:'login'})).status,429);
});

test('legacy lookup uses indexed exact-prefix range without long LIKE patterns',async()=>{
 const db=new D1(),key=quotaKey(),other=quotaKey('issue','b');
 db.db.prepare('INSERT INTO captcha_rates(id,count,expires) VALUES (?,?,?)').run(other+':1',1,999999);
 db.db.prepare('INSERT INTO captcha_rates(id,count,expires) VALUES (?,?,?)').run(key+'-not-a-window',1,999999);
 const prepare=db.prepare.bind(db);db.prepare=sql=>{assert.equal(/\bLIKE\b|\bGLOB\b/i.test(sql),false);return prepare(sql)};
 assert.equal((await claimRate(db,key,3,0)).allowed,true);
});
