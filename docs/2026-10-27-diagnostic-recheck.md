# 2026-10-27 残余诊断独立复核

基于本地提交 `62a93e7`。本轮只做源码检查、官方框架行为核对与隔离探针，不实施业务修复。工作区原有 `.mimosa/`、`.video_agent/` 保留；本地追踪的 origin/main 多一条 CSS 提交 `c65110b`，不涉及本次后端问题，未拉取或改变分支。

结论：第 1、3 项成立；第 2 项关于 ORM 默认数据库的推断错误，但存在另一种读写分离一致性风险；第 4 项应区分直接服务调用、公开 HTTP 路径与会话后端配置。不能照原报告逐项修复。

## 1. Admin 字段错误时仍消费：成立，低优先级修复

[forms.py:186](../src/nova_slider_captcha/forms.py) 的 clean 在字段清洗后执行，没有先检查字段错误。主控分别测试用户名缺失、用户名空白、密码缺失：表单无效、密码认证调用次数为 0，但有效凭证已消费。完整 HTTP 探针也得到用户名缺失时 200 重渲染且凭证已消费。对照坏密码场景则消费凭证并调用认证一次。

这不是认证绕过。普通表单 Mixin 与 Admin 本来就有不同的消费顺序，不能把 Admin 改为认证后消费；但尚未具备可认证字段时消耗凭证确实没有价值。

建议：已有字段错误时保留错误直接退出，不消费且不调用父类密码认证；字段完整时继续先消费、再认证。回归应覆盖缺用户名、空用户名、缺密码、额外字段错误及完整字段但坏密码。README 补充这个边界。

注意 Widget 重渲染本来就会清空传入 proof 值。因此调整服务端消费时机，不等于单独完成浏览器错误重渲染时的凭证保留体验；不要为此贸然回填未经审查的原始 token。

## 2. “ORM 都走 default”不成立；应评估读写分离

Django QuerySet 的 create、update、get_or_create 会设置写操作标记，并通过 `router.db_for_write()` 选择连接。未写 `.using()` 不意味着绕开路由。`_retry_after()` 显式选择写库与 GCRA 写操作一致，prune 同理。[Django 自动路由说明](https://docs.djangoproject.com/en/5.2/topics/db/multi-db/#automatic-database-routing)

主控在两个独立 SQLite 数据库中把整个验证码 app 的读写都路由到非 default 的 captcha 库，确认：

- issue → verify → consume 成功。
- 同一表单第一枚凭证有效、第二枚无效时，第一枚消费回滚；两枚有效时一起提交。
- GCRA 容量 2 时结果为允许、允许、拒绝，retryAfter=30；两条状态均在 captcha 库，default 没有状态行。

因此不应写成“不支持自定义 database router”，也不能认定当前多凭证事务无效。

真正需要关注的是 [services.py:127、145](../src/nova_slider_captcha/services.py)：verify 的首次读取和错误尝试后的 refresh 没有绑定写库。把读取路由到滞后副本、写入路由到主库时，探针复现：

1. 新签发挑战在主库存在，副本尚无记录，verify 返回 invalid_challenge。
2. 副本已有初始挑战但尚未复制错误次数，主库 attempts 已为 1，响应却仍称剩余 5 次。
3. 已有有效凭证的 consume 仍成功走主库，不是“永远失败”。

建议把挑战验证的相关读写固定在同一个稳定写库，并补主从延迟模拟回归；若暂不支持读写分离，准确说明验证码模型须读写同库即可。现有写条件仍在主库限制次数与一次消费，上述复现不是超额放行。Django 文档也明确提示通用主从示例不解决复制延迟与事务配合问题。[官方限制说明](https://docs.djangoproject.com/en/5.2/topics/db/multi-db/#an-example)

## 3. init 无额度限制：成立，建议优先处理

[views.py:100](../src/nova_slider_captcha/views.py) 在同源检查后直接创建绑定，不经过限流。默认数据库 session 后端下，45 次不带 cookie 的 GET 全部 200，新增 45 条 session；重用同一 cookie 的后续请求不新增 session。当前 SESSION_COOKIE_AGE 为 1,209,600 秒，即两周。

影响取决于 session 后端：db/cached_db 会增加数据库记录，文件后端会增加文件，缓存后端占用缓存；signed_cookies 不产生服务器会话表记录，探针也验证了这一点。过期不会自动删除数据库 session；需单独调度 Django clearsessions，组件 prune 不负责清理宿主会话。[Django 会话清理说明](https://docs.djangoproject.com/en/5.2/topics/http/sessions/#clearing-the-session-store)

建议先明确生产入口对 init 的限流与 clearsessions 要求，再补创建新绑定前的 IP 额度控制。既有 session 的正常初始化应保持兼容，拒绝路径不能反而创建新 session。

实现时不能直接把现有 allow_request 套到 init：它在开始遍历 IP 额度之前，就调用 session_binding(create=True)。另外，ensure_csrf_cookie 与 CSRF_USE_SESSIONS=True 会带来额外会话写入；独立探针证明，在此配置下跨源 init 虽返回 403，仍新增一条 session。因此应验证完整中间件响应阶段的记录增量，不能只看视图返回 429/403。入口限流可在进入 Django 前阻断这一成本。

## 4. 缺会话的 500：原描述不准确，存在有限的健壮性改进

- 直接对无 session 属性的 RequestFactory 请求调用 services.issue，确实抛 IntegrityError，因为绑定为空仍尝试创建记录。这值得改成明确前置校验，且应在图片生成/数据库写入之前拒绝。
- 公开 challenge 接口有 [views.py:75](../src/nova_slider_captcha/views.py) 的会话前置检查。只保留 CSRF 中间件、使用真实 CSRF token 请求时，init=200，challenge=409/init_required，不会沿报告描述的路径创建空绑定记录。数据库异常也有 HTTP 包装层捕获。
- 若保留依赖 session 的 Django AuthenticationMiddleware，却移除 SessionMiddleware，Django 自己可以在到达视图前报配置错误；不能把这个 500 归因于 issue 的数据库插入。
- init 在无会话能力时仍返回 200 不够清晰，可与直接服务前置校验一起改进。
- 本组件检查确实没有按 SESSION_ENGINE 验证 sessions app。新进程探针中，db/cached_db 后端缺少 app 时自身检查为空，但 init 返回 500/RuntimeError；signed_cookies 缺少该 app 则正常 200。应仅对确实需要 sessions 模型的后端做检查，不能一概要求安装该 app。[会话后端前提](https://docs.djangoproject.com/en/5.2/topics/http/sessions/#using-database-backed-sessions)

## 观察项

| 项目 | 判断与建议 |
|---|---|
| max_attempts/tolerance 条件“恒真” | 不成立。条件使用前一次读取的 Python 值，是快照参数，不是 SQL 字段与自身比较。探针在读取后改变数据库 tolerance，原条件不再匹配；应保留这一并发防御，可补注释。 |
| Origin 与显式默认端口 | 成立。https://testserver 与 Host testserver:443 会被拒绝，规范 Host 则允许。属于兼容性边界；现有代理契约已要求准确保留外部 Host，可后续小范围规范化 scheme/host/有效端口，不能放宽为同站即可。 |
| blocked_until_us 注释 | 适合顺手补充。运行时创建记录会填默认 0，之后不增加非零冷却期限；已有非零值来自迁移继承，额度判断和清理继续尊重它。无需改模型或迁移。 |
| Worker 与 Django 差异 | 错误码、Fetch Metadata 检查和示例 submit 无额度限制的观察成立，但不必强行统一独立示例协议。Worker 仍要求 Origin 精确相等并验证 CSRF，不应把 same-site 检查差异直接认定为跨源放行。 |
| “demo submit 每次只有一个 UPDATE” | 对 Worker 不准确。它还查询会话，并在 action 分支前执行清理 DELETE 批次；核心 URLConf 隔离不等于零数据库成本。可在公开示例入口按实际容量限流，不因此重写核心协议。 |
| 陈旧构建缓存 | 本地确实存在，通常不是产品缺陷；.gitignore 本身不控制发行包。现有 MANIFEST 排除与运行文件集合/字节检查才是发布保护，应继续使用干净构建和包检查；无需为本次复核清理他人可能使用的缓存。 |

## 验证范围及证据

主控在 Python 3.12.14 / Django 5.2.17 的既有独立工具环境中执行新探针；所有写入仅落到新建任务临时目录中的两个 SQLite 库，不使用示例或业务数据库。本次是有针对性的诊断验证，未运行完整矩阵，未验证真实 PostgreSQL/MySQL 复制。

[证据目录](../verification/2026-10-27-diagnostic-recheck/)包含可复现探针、结构化结果与受查源码哈希，不包含数据库、真实凭证或会话内容。复现时在仓库根目录新建临时目录，设置 NOVA_REVIEW_DIR，使用 PYTHONPATH=src:. 执行 probe.py；它会创建并迁移该目录下的隔离库。session_app_probe.py 每种后端须各起一个新进程。csrf_session_probe.py 在 probe.py 后运行，并把 NOVA_TEST_DB 指向同一临时目录下 default.sqlite3。

建议顺序：先控制 init 的资源写入，再修正 Admin 字段错误消费；随后按真实边界处理会话配置诊断和主从读取一致性。策略快照过滤保留；注释和准确的部署说明可以随对应修复补齐。此报告不自动授权实施、提交或发布。
