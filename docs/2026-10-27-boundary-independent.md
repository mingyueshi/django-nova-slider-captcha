# 初始化、Admin、读写分离与会话配置独立验收

日期：2026-10-27。实施由原 GPT-6.1 SOL 会话完成；本报告记录主控自行执行的代码复核、行为探针和验证，不以实施自测代替独立验收。

结论：本轮四项修复通过独立验收，无阻塞项。代码基线为 `62a93e7` 加本轮未提交差异；70 个运行代码、测试、脚本、配置及 README 文件的候选哈希在独立验证后未变化。完整清单见 [candidate.json](../verification/2026-10-27-boundary-independent/candidate.json)。之后新增的实施/独立报告与索引不改变已验收的运行代码。

## 修复与边界

| 项目 | 独立确认的行为 |
|---|---|
| init 限流 | `NOVA_SLIDER_RATE_LIMITS.init_ip` 默认 40，沿用严格配置检查和原子 GCRA。创建绑定前扣直接连接 IP 额度；已有有效绑定重复 init 豁免，不增加 issue/verify 额度。403/429/503 拒绝路径不生成 CSRF token，避免 `CSRF_USE_SESSIONS=True` 的响应阶段间接创建会话。 |
| Admin 字段错误 | 缺用户名、空白用户名、缺密码、两者均缺或宿主额外字段错误时，不消费、不调用认证。字段有效时仍先消费后认证；密码错误消费一次，重放不能进入认证。错误页面不回填 token，所以本轮不承诺完整页面重渲染后免做拼图。 |
| 读写分离 | verify 的决策读取、条件更新和次数刷新固定于该次选择的写库；保留次数/容差快照竞态条件。普通 ORM 写入原本已遵循写路由，本轮没有把它误改成固定 default。稳定写路由下，多凭证局部事务继续全部成功或全部回滚。 |
| 会话配置 | 内置 db/cached_db 缺 sessions app 产生 E008；其他内置及自定义后端不被无依据拒绝。init 无会话能力或无法取得有效绑定返回 503/configuration_invalid；直接 issue 在出图/写挑战前拒绝空绑定；未初始化 POST 保留 409/init_required。 |

主控预审要求补齐了 init 缺会话能力的状态码，以及已有非字符串绑定导致 init 伪成功的分支；实施完成补充后通过下述检查。具体设计、配置和运维契约已同步 README、CHANGELOG 与 DEPLOYMENT。

## 主控行为验证

独立探针通过 26 项行为检查，见 [结果](../verification/2026-10-27-boundary-independent/probe-results.json) 与 [探针源码](../verification/2026-10-27-boundary-independent/independent_probe.py)：

- 使用真实 Django Client、CSRF 和 SessionMiddleware，分别验证 cookie CSRF 与 session CSRF。容量 2 时连续拒绝 3 个新客户端，session 行数和 GCRA 债务不增长，响应头与响应体均给出 30 秒等待时间；跨源拒绝也不创建 session。
- 8 个无 cookie 请求并发竞争 3 个额度，恰好 3 个成功、5 个 429、3 条新 session；另一个直接连接 IP 可独立初始化，伪造转发头不能绕过原 IP 配额。
- 已有绑定可重复 init，返回的 CSRF token 可用于实际 challenge POST。非法布尔配置、数据库故障、缺中间件和非字符串绑定均受控拒绝；直接 issue 缺会话时不调用出图函数。
- Admin 通过真实数据库凭证验证字段错误保留、认证调用顺序、错误密码、成功认证和重放；另做带真实 CSRF 的 Admin POST，并检查返回 HTML 不含 token。
- 用两个独立 SQLite 数据库模拟写库和故意滞后的读副本：仅主库存在的新挑战可以验证；读副本 attempts 保持 0 时，主库两次错误返回剩余 4、3；主库已成功状态阻止再次验证；消费、回滚、双凭证提交及限流等待时间正确。

另在独立 Python 进程中验证 12 组会话后端/app 组合：db、cached_db、signed_cookies、cache、file、自定义签名 cookie 后端，各自有/无 sessions app。缺 app 的前两种得到 E008 和 init 503；其余组合 init 与带 CSRF 的 challenge POST 均为 200。见 [结果](../verification/2026-10-27-boundary-independent/session-checks.json)。

## 完整回归与包验证

以下六组各执行源码与同一个已安装 wheel 两轮，均通过 149 项后端测试；每轮还执行依赖检查、Django checks、迁移漂移检查及模块来源断言。升级与并发回归包含在完整测试集中。

| Python | Django | Pillow | 源码 / wheel |
|---|---|---|---|
| 3.10.20 | 5.2.17 | 12.2.0 | 149 / 149 |
| 3.11.12 | 5.2.17 | 12.3.0 | 149 / 149 |
| 3.12.14 | 5.2.17 | 12.3.0 | 149 / 149 |
| 3.12.14 | 6.1.2 | 12.2.0 | 149 / 149 |
| 3.13.12 | 6.1.2 | 12.3.0 | 149 / 149 |
| 3.14.7 | 6.0.9 | 12.3.0 | 149 / 149 |

矩阵命令与输出见 [matrix/](../verification/2026-10-27-boundary-independent/matrix/)，明确运行时清单见 [environments.json](../verification/2026-10-27-boundary-independent/environments.json)。wheel 测试使用 `PYTHONPATH=.` 与 `python -m django`，断言模块不来自 `src`。

- coverage 7.17.0，Python 3.12.14 / Django 5.2.17 / Pillow 12.3.0：全包语句 690/700（98.57%）、纯分支 175/178（98.31%）；forms 语句 142/142、分支 44/44，均为 100%。原门槛和严格统计范围未降低，12 项无效报告反例均被拒绝。见 [门槛输出](../verification/2026-10-27-boundary-independent/coverage/05.log)。
- Ruff 0.17.2 通过。Node 24.21.0 下组件 47 项、Django-client DOM 联调 20 项通过；本轮没有前端代码改动，未追加浏览器布局或像素验收。
- 主控自行运行 `twine check --strict` 与 `scripts/check_release.py --dist`：29 个运行文件在 wheel/sdist 中与工作区一致。另逐字节核对 sdist 的新增测试、测试配置、README、CHANGELOG、DEPLOYMENT，及 wheel 元数据中的 UTF-8 README。见 [产物记录](../verification/2026-10-27-boundary-independent/artifacts.json)。

本轮复测使用实施会话构建的同一份产物，没有重建后替换已测 wheel：

```text
wheel SHA256: 9715fcb2f88e13dace52e1dd47a2df8cf410689d39bb1273758fdbea2095f9e9
sdist SHA256: aea7f1452bd31475d405fb2d3d9d283dec88657b8d7aed086520cc57de86708a
```

构建物位于任务临时目录 `/tmp/nova-slider-boundary-impl-dist-20261027/`。主控验证的独立数据库和输出目录为 `/tmp/nova-slider-four-fixes-independent-20261027-bendJW/`；仓库证据不包含数据库、凭证或会话数据。[证据校验清单](../verification/2026-10-27-boundary-independent/evidence-sha256.json) 保留实际日志与探针的哈希。

## 验证范围与状态

本结论是本地源码、安装 wheel、SQLite 多库模拟及 DOM 联调验收；没有执行远端 CI、真实 PostgreSQL/MySQL 复制、生产部署或 PyPI 上传。不同数据库间的事务和任意变化的写路由不在承诺范围，宿主在进入视图前抛出的中间件配置异常仍须由宿主管理。

TOKEN_TTL、几何、Worker、既有语言行为及无关 CSS 未改动。历史诊断记录、用户目录和远端领先的 CSS 提交均保留。本轮尚未提交 Git；未推送、打 tag 或发布，0.3.0 仍处于发布准备状态。
