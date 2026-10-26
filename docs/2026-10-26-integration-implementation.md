# 2026-10-26 通用接入实施与自测

实施基线：`main` / `11dde38`。本记录仅说明实施会话实际修改与本地自测，不替代主控独立验收。没有提交、推送、部署、启动项目服务、操作线上 Worker/D1 或修改共享 Python 环境。未编辑主控独占的 `docs/2026-10-26-integration-independent.md` 和 `verification/2026-10-26-integration-independent/`。版本仍为 0.2.0。

## API 与行为

- `NOVA_SLIDER_PURPOSES` 动态读取，配置**替换**默认 `demo` / `login`；只允许非空 list/tuple/set/frozenset，名称遵循 `[a-z][a-z0-9_:-]{0,31}`。检查 `E004`、出题、校验、消费、HTTP 均失败关闭。移除 purpose 会阻止旧挑战继续校验/消费。action/IP/session 限流键没有加入 purpose，新用途不赠送额度。
- 通用方案为 `SliderCaptchaField(purpose=...)` + `SliderCaptchaFormMixin`，Mixin 在 Form / ModelForm 左侧，初始化须传 `request=`。字段必填且不能 disabled；遗漏 Mixin 会拒绝校验。Widget 通过 `purpose=` 配置用途，模板输出 `field-name` 为 Django 完整字段名，支持 prefix、formset 和多组件。
- 普通表单在所有字段、Form.clean 和 ModelForm 的 `_post_clean`（模型 clean、唯一性、约束）完成且无错误后才消费。多个验证码字段使用 Challenge 写数据库的一个事务，任一失败全部回滚；缺 request、绑定不匹配或数据库错误会拒绝。
- 同一实例重复 is_valid / errors / full_clean 不重复消费。成功缓存绑定 request 对象身份、session 绑定、字段 purpose、原始 token 与清洗后 token；发现上下文改变后永久使本实例失效。最后收尾另补了“自定义 clean_proof 返回新 token / 修改 cleaned_data”回归，防止清洗后的 token 绕过缓存边界。新表单的重放依然由数据库原子 UPDATE 拒绝。
- 未填写的 formset extra 表单按 Django 标准跳过，不消费、不产生错误。formset 的消费边界是单个子表单；其他子表单或 formset.clean 后续失败不保证已消费凭证自动恢复。README 明确此边界、外层事务回滚后丢弃实例、后续业务失败需新凭证，以及不在 clean 中执行业务写入。
- Admin 行为保持：验证码在密码认证前消费，错误密码也消费凭证。
- challenge 几何由 WIDTH / HEIGHT / PIECE_SIZE 常量产生。前端严格检查有限正整数尺寸（最高 8192）、拼图块边界和 pieceY，随后计算 maxX、range max、移动比例、ARIA 和宽高比。非默认几何测试同时验证实际 PNG 尺寸。手柄 48px 仅在 `--nsc-handle-size` 声明一次，CSS 和前端定位共同使用，独立于拼图块尺寸。
- `nova_slider_captcha` 命名 logger 的固定消息配合 extra：captcha_event / captcha_reason / captcha_status / captcha_purpose / captcha_action。503 为 ERROR，消费拒绝为 WARNING，429 默认 DEBUG，可通过 `NOVA_SLIDER_RATE_LOG_LEVEL` 改级别或 OFF，检查 `E005`。成功无业务日志。日志中没有 token、绑定秘密、答案、请求体、原始异常或任意客户端字符串；handler 抛异常不改变结果。
- README 包含独立 Form、ModelForm、模板、用途配置、事务说明与宿主 logging 示例；新增 CHANGELOG / Unreleased，记录本轮和此前未发布修复。RateBucket 注释/文档标注仅升级清理使用，未来删除必须独立迁移。

没有开放 TTL / MAX_ATTEMPTS / TOLERANCE / 图片尺寸配置，没有改随机形状、attemptsRemaining 或 RateBucket 表结构。没有增加外部依赖或迁移。

## 实际验证

环境：macOS arm64；SQLite 3.54.0；Node 24.21.0；jsdom 26.1.0。两个只读复用环境如下：

- `/tmp/nova-slider-implementation-20261026-py310/bin/python`：Python 3.10.20、Django 5.2.17、Pillow 12.2.0。
- `/tmp/nova-slider-review-20261026/bin/python`：Python 3.12.14、Django 5.2.17、Pillow 12.2.0。

| 最终检查 | 结果 |
|---|---|
| Python 3.10 完整 source 测试 | 99 项通过，零跳过 |
| Python 3.12 完整 source 测试 | 99 项通过，零跳过 |
| 两种 Python 的 Django check | 均无问题 |
| 两种 Python 的 makemigrations --check --dry-run | 均无迁移变化 |
| 两种环境 uv pip check | 均兼容；没有安装或更改包 |
| npm test | 38 项组件测试通过，含非默认/恶意几何、自定义提交字段 |
| npm run test:dom | 12 项 jsdom + 真实 Django test client 检查通过 |
| npm run test:worker | 25 项本地 Worker 测试通过 |
| git diff --check | 通过 |

本轮新增 28 项 Django 测试（基线 71 → 最终 99）与 3 项组件测试（35 → 38）。Django 增补包含集合语法/动态配置、用途共享额度、固定 demo 消费、ModelForm 模型/唯一性/约束失败保留、重复验证与上下文变更、前缀/formset、空 extra、多字段整体回滚、数据库失败、结构化级别、429 控制、成功安静及日志脱敏。原有原子消费/并发验证/限流、Admin、语言、图片和升级回归也一起运行。

所有后端检查使用实施专属 NOVA_TEST_DB（`/tmp/nova-slider-integration-py310-20261026.sqlite3` / `...-py312-20261026.sqlite3`）。DOM bridge 自建独立临时数据库；DOM 报告显式写入本轮新目录。未迁移示例数据库。

最终日志见 [verification/2026-10-26-integration-implementation/](../verification/2026-10-26-integration-implementation/)：

- `py310-acceptance.log`、`py312-acceptance.log` 与 `python-acceptance-results.json` 是最终 **99 项**结果。
- `component-final.log` 为最终 38 项；`component.log` 保留首次 37/38 的结果：旧断言固定要求 48px，但本轮改成 CSS 变量。更新断言同时检查变量引用与默认变量 48px 后通过，未改变交互尺寸。
- `dom.log` / `dom-results.json` 为 12 项；`worker.log` 为 25 项。
- `py312-initial.log` 为收尾前 94 项，`py312-final.log` 为 95 项，`py310-complete.log` / `py312-complete.log` 为 98 项；均保留，不冒充最终结果。
- `runtime-source-sha256.json` 记录实施冻结时源文件身份，未覆盖历史 manifest。

可复现命令（仓库根目录；输出标签应换成未使用名称以保留已有日志）：

```sh
# 脚本设置 PYTHONPATH=src:.、DJANGO_SETTINGS_MODULE=tests.settings、专属数据库，
# 两环境分别执行版本、check、迁移漂移、完整 tests、uv pip check。
/tmp/nova-slider-review-20261026/bin/python \
  verification/2026-10-26-integration-implementation/run_checks.py new-label

npm test
NOVA_PYTHON=/tmp/nova-slider-review-20261026/bin/python \
  NOVA_TEST_DB=/tmp/nova-slider-integration-dom-20261026.sqlite3 \
  NOVA_DOM_REPORT=/absolute/path/new-dom-report.json npm run test:dom
npm run test:worker
git diff --check
```

## 证据范围

以上为实施会话本地 source / 原生 Django 配置及 jsdom 的证据。未在实施会话重跑 wheel、Nova 主题、Django 6.x 或历史完整 Python/Django 矩阵；未运行远端 GitHub Actions。主控另行执行的真实浏览器、Django 6.1、wheel 等独立检查，以主控报告为准，本记录不据消息代称自己完成了那些验证。

jsdom 不能验证真实浏览器布局、像素、真实鼠标/多指触控或辅助技术。未做 PostgreSQL/MySQL、生产负载、多主机代理、真机、屏幕阅读器或线上 Worker/D1 验证。没有把本地 Worker 测试当成线上 Worker 数据验收。
