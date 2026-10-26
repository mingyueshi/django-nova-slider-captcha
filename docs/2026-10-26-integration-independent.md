# 2026-10-26 通用接入改进独立验收

结论：本轮约定的五项改进已完成，主控独立复核与验证通过，未发现阻断验收的问题。代码基线为 `main` / `11dde38`；本轮尚未提交、推送或部署，包版本仍为 0.2.0。

实施由独立会话 `01a17598-dca2-7783-ad1e-27713d10800a` 使用 `gpt-6.1-sol` 完成；本会话负责范围控制、代码复核、独立探针、真实浏览器与安装包验证。实施自测见 [实施记录](2026-10-26-integration-implementation.md)，本报告的检查均由主控另行运行。

## 已验收的范围

1. `NOVA_SLIDER_PURPOSES` 动态配置与系统检查；配置替换默认集合，新增用途共用既有限流额度，错误配置拒绝请求，旧用途被移除后不能继续验证或消费。
2. `SliderCaptchaField` + `SliderCaptchaFormMixin` 支持 Form / ModelForm；Widget 可配置用途和完整提交字段名，支持前缀、formset、多组件。普通表单完成所有字段和模型校验后才消费；Admin 继续在密码认证前消费。
3. 前端从 challenge 响应计算尺寸、行程、位置、宽高比和 ARIA；手柄尺寸通过 CSS 变量独立控制，并拒绝不合法几何数据。
4. 结构化日志覆盖限流、服务不可用和消费拒绝。503 使用 ERROR；429 默认 DEBUG，可配置级别或关闭；成功保持安静。独立检查确认不记录 token、session 绑定秘密、答案或原始数据库异常。
5. README 补充可运行的通用表单接入和配置示例，新增 [CHANGELOG](CHANGELOG.md) 的 Unreleased 记录，说明 RateBucket 的历史清理用途。

本轮没有开放 TTL、尝试次数、容差或后端图片尺寸配置，没有调整拼图形状、删除 attemptsRemaining、删除 RateBucket 或新增迁移。暗色、减少动画和小屏规则未因缺少媒体查询而机械加入。

## 独立复核发现并推动修复

- 空 formset extra 子表单最初会因缺少验证码上下文而报错。独立探针复现后，实施修复为遵循 Django 对未填写 extra 表单的跳过行为；最终真实 formset 验证通过。
- 503 业务事件最初使用 WARNING，宿主仅收集 ERROR 时会漏掉服务故障。实施改为 ERROR 并补充回归；独立日志检查通过。
- 对成功缓存额外核查了 request 对象身份、session、用途、原始 token、清洗后 token，以及失效后的永久拒绝；不同 token 不能借用旧成功结果，也不会被误消费。

## 主控实测结果

| 检查 | 最终结果 |
|---|---|
| Python 3.10.20 + Django 5.2.17，源码 | 99 项通过 |
| Python 3.12.14 + Django 5.2.17，源码 | 99 项通过 |
| Python 3.12.14 + Django 6.1.1，源码 | 99 项通过 |
| Python 3.12.14 + Django 6.1.1，独立环境安装 wheel | 99 项通过 |
| wheel 与最终源码、实施冻结清单对照 | 28 个运行文件逐字节/hash 一致 |
| 安装包 check / makemigrations 检查 / 依赖检查 | 无问题、无迁移变化、依赖兼容 |
| Node 24.21.0 组件测试 | 38 项通过 |
| jsdom 26.1.0 + 真实 Django test client | 原有 12 项、独立通用表单 6 项通过 |
| 本地 Worker 测试 | 25 项通过 |
| 独立 Python 表单 / 协议探针 | 7 项 / 5 项通过 |
| Chromium 155.0.8059.86 几何、键盘与表单字段 | 通过 |
| git diff --check | 通过 |

后端使用独立 SQLite 测试数据库，探针使用内存库，没有迁移示例数据库。构建出的 wheel 在隔离环境安装，确认导入路径来自 site-packages；运行测试时未把 src 加入 PYTHONPATH。三组源码与 wheel 均针对实施冻结后的最终代码重新验证。Pillow 为 12.2.0。

真实 Chromium 使用 480×200 背景、60×60 拼图的实际 PNG，HTTP 响应为本地模拟。行程为 420，拼图最右端对齐；48px 和 56px 手柄均保持轨道定位。键盘实际提交 x=419 / x=420，两个组件分别填入 `join-security` / `recover-security`。390px 视口没有横向溢出。截图见 [geometry-mobile.png](../verification/2026-10-26-integration-independent/geometry-mobile.png)。这组证据验证浏览器解码、布局和键盘，不冒充真实 Django 网络链路；后者由真实 test client 与 jsdom 联合验证。

## 证据与复现

所有主控证据保存在 [verification/2026-10-26-integration-independent/](../verification/2026-10-26-integration-independent/)：`summary.json` 汇总环境和计数；`wheel-identity.json` 保存安装包及 28 个运行文件的 SHA-256；`django-*.log` / `django61.log` / `wheel-tests.log` 是最终后端结果。`browser-run.log` 保存执行过的浏览器断言，`browser-results.json` 保存成功状态和实际提交字段。基线日志也单独保留，没有覆盖此前验收记录。

在仓库根目录选择已安装依赖的 Python，使用未占用的输出路径：

```sh
PYTHONPATH=src:. DJANGO_SETTINGS_MODULE=tests.settings \
  NOVA_TEST_DB=/tmp/nova-independent-new.sqlite3 python -m django test tests
PYTHONPATH=src:. DJANGO_SETTINGS_MODULE=tests.settings \
  python verification/2026-10-26-integration-independent/forms_probe.py
PYTHONPATH=src:. DJANGO_SETTINGS_MODULE=tests.settings \
  python verification/2026-10-26-integration-independent/protocol_probe.py
NOVA_PYTHON=/absolute/path/to/python \
  node verification/2026-10-26-integration-independent/form_dom.cjs
npm test
NOVA_PYTHON=/absolute/path/to/python NOVA_DOM_REPORT=/tmp/nova-new-dom.json npm run test:dom
npm run test:worker
```

`build_browser.py` 可从当前源码生成浏览器模拟页；浏览器中的验证码 token 是固定测试字符串。wheel 和虚拟环境仅留在临时目录，没有加入仓库。

## 接入边界

- formset 消费以每个子表单为边界，整组验证失败不会自动恢复先前已消费的凭证；该限制已在 README 明示。
- 同一表单实例的重复校验不重复消费，但不提供业务幂等性。外层事务回滚后应丢弃实例；后续业务失败需要新凭证。
- Worker 示例仍保持其原有配置范围；本轮 Django 配置能力不代表 Worker 同步新增了对应设置。
- 本轮未重跑历史完整兼容矩阵、Nova 主题全量回归、远端 CI、PostgreSQL/MySQL、生产负载、真机或屏幕阅读器，也没有访问线上 Worker/D1。
