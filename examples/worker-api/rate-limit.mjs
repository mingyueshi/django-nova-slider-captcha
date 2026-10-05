// 数据库原子 GCRA。容量 N，按 ceil(60 秒 / N) 微秒均匀补充，不按整分钟重置。
const PERIOD_US = 60_000_000;
export class RateLimitStorageError extends Error {
  constructor() { super('rate_limit_unavailable'); }
}
function parameters(limit, nowMs) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 60_000) throw new TypeError('limit must be an integer in 1..60000');
  const nowUs = Math.floor(nowMs * 1000);
  if (!Number.isFinite(nowMs) || !Number.isSafeInteger(nowUs) || nowUs < 0 || nowUs > Number.MAX_SAFE_INTEGER - 2 * PERIOD_US) throw new TypeError('invalid clock');
  const interval = Math.ceil(PERIOD_US / limit);
  return { nowUs, interval, tolerance: (limit - 1) * interval };
}
const delay = (row, nowUs, tolerance) => Math.max(0, Math.ceil((Math.max(row?.blocked_until_us || 0, (row?.tat_us || 0) - tolerance) - nowUs) / 1_000_000));
async function readState(db, key) {
  return db.prepare('SELECT tat_us,blocked_until_us FROM captcha_rate_state WHERE id=?').bind(key).first();
}
export async function claimRate(db, key, limit, nowMs) {
  const {nowUs, interval, tolerance} = parameters(limit, nowMs);
  if (typeof key !== 'string' || !/^[a-z-]+:[a-f0-9]{64}$/.test(key)) throw new TypeError('invalid quota key');
  try {
    // 保留原固定窗口表：首次使用时继承仍有效的旧额度冷却期。
    // schema 升级前必须停写；旧新版并行写入不构成同一限流器。
    await db.prepare('INSERT INTO captcha_rate_state(id,tat_us,blocked_until_us) SELECT ?,0,COALESCE(MAX(expires)*1000,0) FROM captcha_rates WHERE id>=? AND id<? AND expires>? ON CONFLICT(id) DO NOTHING').bind(key,key+':',key+';',nowMs).run();
    const claimed = await db.prepare('UPDATE captcha_rate_state SET tat_us=MAX(tat_us,?)+? WHERE id=? AND blocked_until_us<=? AND tat_us<=? RETURNING tat_us,blocked_until_us').bind(nowUs,interval,key,nowUs,nowUs+tolerance).first();
    if (claimed) return {allowed:true,retryAfter:0};
    const row = await readState(db,key);
    // 并发清理可能移除已完全补充的行；本次仍拒绝，绝不无状态放行。
    return {allowed:false,retryAfter:Math.max(1,delay(row,nowUs,tolerance))};
  } catch (_) { throw new RateLimitStorageError(); }
}
export async function claimQuotas(db, quotas, nowMs) {
  const claimed=[];
  for (const [key,limit] of quotas) {
    const decision=await claimRate(db,key,limit,nowMs);
    if (!decision.allowed) {
      let retryAfter=decision.retryAfter;
      try {
        for (const [previous,capacity] of claimed) {
          const {nowUs,tolerance}=parameters(capacity,nowMs);
          retryAfter=Math.max(retryAfter,delay(await readState(db,previous),nowUs,tolerance));
        }
      } catch (_) { throw new RateLimitStorageError(); }
      return {allowed:false,retryAfter};
    }
    claimed.push([key,limit]);
  }
  return {allowed:true,retryAfter:0};
}
