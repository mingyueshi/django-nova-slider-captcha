# 验证索引：0.3.0 发布准备与历史结果

当前维护版本为 **0.3.0，尚未上传**。下方 0.2.0 数字和根目录 `verification/export-checks.json` 都是 2026-10-05 的历史结果；其中 “No workflow configured” 描述当时情况，不能用于判断当前 CI 配置或执行状态。当前已有 [Tests](../.github/workflows/tests.yml) 和 [Publish](../.github/workflows/publish.yml)，有工作流配置不等于本轮远端运行通过。

| 版本/日期 | 报告与新证据 | 范围 |
|---|---|---|
| 0.3.0 / 2026-10-29 补充 | [会话引擎补充复核](2026-10-29-session-engine-followup.md)、[任务证据](../verification/2026-10-29-session-engine-followup/) | 非法引擎受控拒绝、当前源码与新 wheel；不覆盖或改写前轮证据 |
| 0.3.0 / 2026-10-29 | [人工复核修复](2026-10-29-review-fixes.md)、[任务证据](../verification/2026-10-29-review-fixes/) | 焦点、子进程、会话后端、Worker、本地源码/wheel 配对与发布检查；具体结果以报告为准 |
| 0.3.0 / 2026-10-27 | [边界独立验收](2026-10-27-boundary-independent.md)、[任务证据](../verification/2026-10-27-boundary-independent/) | init、Admin、写库与会话配置；仅代表当时差异 |
| 0.3.0 / 2026-10-26 | [发布准备独立验收](2026-10-26-release-independent.md)、[任务证据](../verification/2026-10-26-release-independent/) | 当时的策略快照、主题、构建与本地矩阵 |

更细的实施/独立报告见 [文档目录](README.md)。本轮没有另设实施会话，2026-10-29 的结果是同一会话复核与自测，不冒称独立验收；历史独立报告也不自动覆盖之后的变更。未执行的远端 CI、上传、部署和数据库/设备验收不能由本地结果推定。

---

## 0.2.0 历史验证说明（保留原始结果）

验证日期：2026-10-05。此文件记录本轮优化后的实际执行结果，不把旧版测试视为本版重跑。0.1.0 历史记录已保存到 `verification/history-0.1.0/`。

Nova 集成基线是 Theme 0.6.0，对应公开源码 [b0fd37e](https://github.com/mingyueshi/nova-admin/commit/b0fd37e528a6ad76bec646a68d02f017cde3c4b9)。没有修改或把该主题内置到此包。

## 本轮 Python / Django 完整矩阵

| Python | Django | Pillow | source/wheel × native/Nova |
|---|---|---|---|
| 3.11.17 | 5.2.17 | 12.2.0 | 4 模式通过 |
| 3.12.15 | 5.2.17 | 12.2.0 | 4 模式通过 |
| 3.12.15 | 6.0.8 | 12.2.0 | 4 模式通过 |
| 3.12.15 | 6.1.1 | 12.2.0 | 4 模式通过 |
| 3.13.16 | 6.1.1 | 12.2.0 | 4 模式通过 |
| 3.14.8 | 5.2.17 | 12.2.0 | 4 模式通过 |
| 3.14.8 | 6.1.1 | 12.2.0 | 4 模式通过 |

每种模式实际运行 61 项测试，28 种模式共 **1708 次通过，无跳过**。最后一次重跑包含已修正的多指交错前端文件。系统检查、迁移漂移、`pip check`、源码/wheel 导入来源断言均通过。矩阵脚本现在强制重装指定 wheel，避免相同版本号掩盖旧安装包。

平台为 Linux x86-64、普通 GIL CPython；使用已存在的精确隔离运行时，不把运行时复用描述为重新下载。数据库并发使用文件型 SQLite 与独立线程连接。依赖为上述 Django/Pillow、asgiref 3.12.1、sqlparse 0.6.0。编译中文目录使用 polib 1.2.0；标准 Django `compilemessages` 也可在有 GNU gettext 的环境重建。

测试覆盖原有挑战/凭证/CSRF/Admin 约束，并新增：

- 微秒级补充边界，60 秒前后不恢复两个满桶；拒绝不延后债务
- IP/session/action 独立键、共享 purpose 额度、新 session 不能绕过 IP 限额
- 12 线程容量与单次补充竞争；清理与获取/更新竞争，包含注册删除信号的环境
- 非法配额配置、实际 Retry-After、数据库故障的 503 失败关闭
- 旧固定窗口升级保守保留最大过期时间，挑战与凭证保留，拒绝自动逆迁移
- `USE_TZ=False` 与正常时区配置；回退时钟保留债务
- Django 表单/模板的中文目录和活动语言；本地化不会更改机器错误代码

安装声明仍为 Python ≥3.10、Django ≥5.2.17 且 <6.2；Python 3.10 和其他笛卡尔组合没有因此变成已测组合。

## 本轮 Node / 前端矩阵

| Node | 配套 npm | jsdom | 组件 | 真实 Django-client DOM | Worker SQL |
|---|---|---|---:|---:|---:|
| 22.23.3 | 10.9.9 | 26.1.0 | 28 | 12 | 25 |
| 24.21.0 | 11.19.0 | 26.1.0 | 28 | 12 | 25 |
| 26.10.0 | 11.19.1 | 26.1.0 | 28 | 12 | 25 |

三组均通过：组件 84 次、Django DOM 36 次、Worker SQL 75 次。沿用各 Node 版本的独立干净 jsdom 安装；官方二进制校验记录保存在 `node-downloads.json`。

组件检查覆盖默认中文、英文及地区回退、未知语言、自定义文案、文本注入防护、数字占位符、ARIA/宿主 lang、初始化失败、重试秒数、动态切换不丢失凭证/不延长有效期、刷新/迟到响应/过期/重放、长文本换行样式，以及旧 pointerup/cancel/lost-capture 不影响新拖动。真实 Django-client DOM 流程使用 Python 3.12.15 / Django 5.2.17，保留真实 CSRF 检查与一次性凭证消费；图片解码在 DOM 测试中被替代，因此不把这些结果说成真实浏览器视觉验证。

`tests/fixtures/gcra.json` 同时驱动 Django 与 Worker，逐步核对允许/拒绝、Retry-After 和 TAT。Worker 使用真实 SQLite SQL，并验证原阈值继续保持：出题 15/session、120/IP，校验 60/session、240/IP，初始化 40/IP。

## 独立评审与真实 Worker 运行时

独立安全、升级和国际化评审通过；额外检查包括 32 线程清理/创建/条件更新、配置变更后的债务保留、SQL 故障注入和整数边界。发现的多指交错问题已修正并独立复现复测。

真实本地 workerd/D1 HTTP 检查通过：八路校验与八路消费各恰一成功；出题容量与 purpose 切换约束；计算后的 Retry-After；活跃旧窗口冷却继承，以及冷却到期后的恢复。

实际 D1 还暴露了长 LIKE 模式限制。旧键继承查询已改为有主键索引的精确前缀范围 `[key + ':', key + ';')`；独立检查在 2017 个边界样例上验证与此前前缀意图等价，实际 workerd 复测通过。没有把原始数据库错误返回给客户端。

## 产物身份

最终测试 wheel：`nova_slider_captcha-0.2.0-py3-none-any.whl`。
SHA-256：`7eb1199d1c324a1bb290c675532d7e1caa708d2fadb3bc03375a472e147f7e2a`。

已逐字节核对该 wheel 的全部 27 个运行文件与当前源码，含 `0002_ratelimitstate` 和中文 `.mo`。wheel 不包含测试用答案桥、示例数据库或开发环境。后续文档/报告元数据变化可能令重新构建的 wheel 整包哈希不同；运行文件身份另见 `source-runtime-sha256.json`。仓库不提交 wheel 或源码 ZIP。

## 报告与未验证范围

当前机器记录位于 `verification/matrix-results.json`、`node-results.json`、`dom-results.json`、各版本日志和 `source-runtime-sha256.json`。日志只替换机器专用根路径，不修改测试结果。

未执行：PostgreSQL/MySQL、生产负载、其他操作系统/架构、PyPy/无 GIL 版本、任意跨主机时钟偏差、真机 iOS/Android、屏幕阅读器或 RTL 语言。GCRA 不构成跨独立数据库的全局风控；视觉拼图不保证抵抗计算机视觉。生产仍需独立账号/IP 控制和安全的非视觉替代流程。

公开站点的中英文/小屏浏览器检查与维护切换另外执行；它的 Worker 页面不能冒充 Django 页面浏览器检查。仓库没有 GitHub Actions workflow 时，本地通过不等于远端 CI 通过。

## 公开演示的本轮浏览器检查

在云 Chromium 对0.2.0公开站点检查了中文/英文状态与ARIA、维护503的本地化、维护恢复后刷新、英文错误次数提示、桌面拖动成功、成功后切换语言仍可消费同一凭证、小屏键盘调节成功、中文/英文业务提交、凭证到期恢复，以及自定义长文案。400与333 CSS像素视口（通过窗口缩放与浏览器缩放得到）浅/深色布局均无横向溢出。此处是实际浏览器检查，仍不是iOS/Android真机或辅助技术检查。

部署切换先启用维护响应，读回全部旧桶并确认实际过期时间。约150秒维护后再次核实旧数据未新增且均已过期，移除维护配置并部署同一版本，公开服务恢复。线上演示仍是Worker/D1，不将该结果计入Django页面视觉验证。
