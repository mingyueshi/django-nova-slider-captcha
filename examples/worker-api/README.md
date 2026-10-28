# 可选 Worker / D1 API 示例

本目录保留公开演示所使用的服务端协议实现，不包含实际托管项目、数据库 ID、凭据、部署历史或 React 展示页面。主要交付仍是仓库根目录的 Django app；只有选择 Worker 运行时的接入方才需要本示例。

## 文件

- `captcha.mjs`：会话、CSRF、挑战、验证与一次性凭证消费
- `puzzle.mjs`：程序生成 PNG 拼图
- `rate-limit.mjs`：数据库原子 GCRA 限流与旧桶冷却期继承
- `schema.sql`：0.1.0 原始 schema，仅新建数据库应用一次
- `migrations-0002-gcra.sql`：0.2.0 新增 GCRA 表；旧库只应用此新增迁移，不重复建旧表
- `worker.mjs`：最小 fetch 入口，仅挂载 `/captcha/init`、`challenge`、`verify`、`submit`
- `tests/backend.test.mjs`：以真实 SQLite SQL 适配 D1 接口的协议与并发回归

需要部署方自行配置名为 `DB` 的 D1 binding，并开启支持 `node:zlib` 的 `nodejs_compat`。仓库不会创建账户、数据库或线上资源，没有可直接使用的部署 ID。

## 升级和运行

升级前停止旧版写入。新建表后，第一次访问稳定限流键时会读取尚未过期的旧窗口行，继承其最大过期时间到 `blocked_until_us`。这样可能短暂保守拒绝，避免升级时立即恢复一个新满桶。新旧版同时写入不构成一个统一限流器；不得声称这个流程是无停机混合版本升级。

不要在仍有债务或冷却期时删除 GCRA 表或回退旧代码。回退需要停写、等待状态安全消退并进行经审查的人工运维；schema 脚本未提供自动 down migration。

同源提供 `src/nova_slider_captcha/static/nova_slider_captcha/slider.js` 与 `slider.css`，再放置：

```html
<nova-slider endpoint="/captcha/" purpose="demo" locale="zh-CN"></nova-slider>
```

`GET init` 创建 HttpOnly 会话并返回 CSRF token；POST 同时检查精确 Origin 与 `X-CSRFToken`。演示提交只消费凭证，不执行真实业务。成功/失败使用稳定机器代码，客户端通过字典展示提示，不直接显示后端原文。

## 与 Django 的关系

两个实现共享图片尺寸、坐标/容差、120 秒挑战、5 次尝试、60 秒单次凭证及组件协议。限流都采用容量 N、每 `ceil(60,000,000/N)` 微秒补充一次的 GCRA 令牌桶，没有整分钟重置，也不承诺任意滑动一分钟最多 N 次。

Worker 继续沿用原有默认阈值：出题 15/session、120/IP，校验 60/session、240/IP，初始化 40/IP。演示 submit 有独立的 60/session、240/IP 额度，包含无效凭证请求；超额返回 429 / `rate_limited`，不消费凭证。Django 的阈值见根目录说明；两者算法语义一致，但不会共用数据库或额度。同动作下 `demo`/`login` 共享配额。先扣 IP 再扣 session，后续拒绝不退还前面的额度。`Retry-After` 是当时状态下的等待估计。

Worker 使用 Cloudflare 提供的可信边缘 IP。缺少时使用共同的 unknown 桶，而非跳过保护；不能在非可信代理上接受任意客户端伪造此头。Django 使用经部署配置的 `REMOTE_ADDR` 和 keyed HMAC，二者不是数据库层面的逐字节相同实现。错误代码、初始化限制与运维方式也存在差异。

生产接入仍需 HTTPS、可信代理、安全响应头、独立登录/账号风控与同等安全的非视觉替代验证。原在线站点在外层加了 `frame-ancestors` / `X-Frame-Options` 等响应保护；这里的最小 API 入口不含整个托管壳，不会替接入方配置全部安全头。

## 测试

在仓库根目录、Node >=22.13.0（CI 使用 24）中运行：

```sh
npm run test:worker
```

本测试覆盖 `worker.mjs` 的实际 fetch 路由、会话/CSRF/验证/消费完整链路、未知路径和方法、缺少 DB，以及 submit 的共享 IP/会话额度、精确补充和存储失败拒绝。它使用 SQLite 执行实际 SQL，不会部署 Cloudflare，也不替代你的 D1/生产运行时验证。测试范围和历史真实 workerd 检查分别记录在 [验证索引](../../docs/VERIFICATION.md)。
