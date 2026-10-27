# 2026-10-27 初始化与验证边界实施自测

基于本地 `62a93e7efc2d4f1cca0a9390627f5a821c4c742c` 的未提交差异；版本仍为 0.3.0 待发布。未拉取本地追踪分支上的其他 CSS 提交，未改动 `.mimosa/`、`.video_agent/` 或主控诊断证据。本报告仅记录实施自测，独立验收由主控另行记录。

## 实施范围

- `init_ip` 默认 40，动态严格整数校验；初始化新绑定前执行 IP GCRA，已有有效绑定重入豁免。限流器延迟取得 session 主体，IP 拒绝之前不创建绑定。issue / verify 的额度、稳定键、整数微秒、拒绝不延长债务与 IP 优先扣减保持原语义。
- init 仅在成功取得有效绑定后调用 `get_token`；去除 init 的 `ensure_csrf_cookie` 包装，避免拒绝路径因生成 CSRF token 而在响应阶段创建 session。两种 CSRF 存储模式均经过真实 Django Client 中间件链验证。缺 SessionMiddleware、无法取得有效绑定返回固定 503 / `configuration_invalid`；未初始化 POST 仍为 409 / `init_required`。
- Admin 已有字段错误直接保留 `cleaned_data` 与错误，不消费、不调用父类认证；字段完整仍先消费后认证，坏密码会消费。错误 HTML 不回填 token。
- verify 每次选定 Challenge 写库，将首次读取、条件更新、错误次数刷新固定到该连接；保留 `max_attempts` / `tolerance` 的字面快照条件。consume 本已通过写操作路由，普通表单事务本已选择 Challenge 写库，不作无依据重写。
- 新增 E008：仅 Django 内置 db / cached_db 缺少 sessions app 时拒绝；init、JSON 包装层与直接 issue 也受控拒绝。无会话的直接 issue 在出图/插入前抛明确 ValueError。signed_cookies / cache / file 及自定义后端不因没有 sessions app 被拒绝。
- README、CHANGELOG、部署说明补充上述契约、全部 init 流量的入口限速与独立 clearsessions 责任。未改模型、迁移、TOKEN_TTL、几何、Worker 或前端资源。

## 回归与覆盖率

主工具环境：Python 3.12.14 / Django 5.2.17 / Pillow 12.3.0 / coverage.py 7.17.0 / Ruff 0.17.2；Node 24.21.0 / npm 11.19.0。所有数据库、会话文件、环境和输出使用本任务路径，不触及示例/业务数据库。

| 自测 | 结果 |
|---|---|
| 定向后端（boundaries、rate_limit、captcha、integration） | 96 项通过 |
| 完整后端（覆盖率运行） | 149 项通过，零跳过 |
| Django checks、迁移漂移、依赖一致性 | 通过 |
| Ruff、git diff --check | 通过 |
| 组件 | 47 项通过 |
| Django-client DOM | 20 项通过 |
| Worker 本地测试 | 25 项通过 |
| 覆盖率严格门槛与 12 种伪报告反例 | 通过 |

包纯语句 690/700（98.57%），纯分支 175/178（98.31%）；forms 语句 142/142、分支 44/44（均 100%）。包含升级和新进程会话测试的子进程；无排除配置。原升级回归随每次完整后端套件执行。

新增 12 项测试，重点覆盖：init 403/429/503 的响应阶段无新增 session、CSRF session/cookie 两模式成功后仍可 POST、准确补充时点与债务保留、伪造转发头无效、有效绑定重入、不合法绑定拒绝、配置/数据库失败、Admin 字段错误/认证顺序/HTML、非默认写库和真实分离的滞后副本、策略竞态、多凭证回滚。db / cached_db / signed_cookies / cache / file / 自定义后端各起全新进程，在无 sessions app 下核对 checks、init、challenge 与直接 issue。

`focused.log` 保留首次新测试运行的两个断言与一个测试替身签名错误：调整了新增 init 状态行计数、改变容量仍保留债务的预期、认证替身的 request 参数。最终结果以 `focused-final.log`、完整覆盖率和六格日志为准。

复现主命令（在仓库根目录，用本任务已安装依赖的解释器；替换临时路径）：

```sh
export PYTHONPATH=src:.
export DJANGO_SETTINGS_MODULE=tests.settings
export NOVA_TEST_DB=/tmp/nova-boundary-tests.sqlite3
python -m django check
python -m django makemigrations nova_slider_captcha --check --dry-run
python -m coverage run -m django test tests --noinput -v 1
python -m coverage combine --keep
python -m coverage json -o /tmp/nova-boundary-coverage.json
python scripts/check_coverage.py /tmp/nova-boundary-coverage.json
python scripts/test_coverage_gate.py /tmp/nova-boundary-coverage.json
ruff check .
npm test
NOVA_PYTHON="$(python -c 'import sys; print(sys.executable)')" NOVA_DOM_REPORT=/tmp/nova-boundary-dom.json npm run test:dom
npm run test:worker
```

## 同一构建物的六格验证

独立 Python 3.12.14 工具环境一次构建到新目录，`build --installer uv`、`twine check --strict`、`check_release.py --dist` 通过，wheel / sdist 的 29 个运行文件集合与字节一致。每格分别在源码与安装同一 wheel 后运行 checks、迁移漂移、完整 149 项测试、依赖检查，并断言实际模块导入位置；12 个 profile 均通过。

| Python 实际版本 | Django | Pillow | source / wheel |
|---|---|---|---|
| 3.10.20 | 5.2.17 | 12.2.0 | 各 149 项通过 |
| 3.11.12 | 5.2.17 | 12.3.0 | 各 149 项通过 |
| 3.12.14 | 5.2.17 | 12.3.0 | 各 149 项通过 |
| 3.12.14 | 6.1.2 | 12.2.0 | 各 149 项通过 |
| 3.13.12 | 6.1.2 | 12.3.0 | 各 149 项通过 |
| 3.14.7 | 6.0.9 | 12.3.0 | 各 149 项通过 |

构建目录 `/tmp/nova-slider-boundary-impl-dist-20261027/`：

- wheel `nova_slider_captcha-0.3.0-py3-none-any.whl`，SHA-256 `9715fcb2f88e13dace52e1dd47a2df8cf410689d39bb1273758fdbea2095f9e9`
- sdist `nova_slider_captcha-0.3.0.tar.gz`，SHA-256 `aea7f1452bd31475d405fb2d3d9d283dec88657b8d7aed086520cc57de86708a`

五个运行文件已经冻结，`candidate.json` 记录精确源码 SHA-256 与构建物身份，`runtime.diff` 保存运行差异。随后仅整理本报告、索引和证据。实施证据见 [任务目录](../verification/2026-10-27-boundary-implementation/)，含矩阵运行器、12 个 profile 日志、覆盖率 JSON/门槛结果、组件/DOM/Worker 日志及构建检查结果；原始 coverage 数据和 HTML/XML 在任务临时目录中保留。

## 验证边界

主控于本轮后续回执确认独立验收通过：70 个候选代码/测试/配置/README 文件在检查前后哈希一致；六格 source / 同一 wheel 共 12 轮各 149 项、26 个行为探针、12 个后端/app 新进程组合通过；覆盖率与本报告一致，Ruff、47 项组件、20 项 DOM、twine / check_release 及 sdist 关键测试/说明字节比对通过。独立结果见 [主控报告](2026-10-27-boundary-independent.md) 与 [独立证据](../verification/2026-10-27-boundary-independent/)，不计作实施自测。此回执后仅补充本段与文档索引，未改运行代码、测试、README 或重新构建产物。

读写分离使用隔离 SQLite writer / replica 模拟，未验证真实 PostgreSQL/MySQL 复制。DOM 使用 jsdom 与真实 Django Client，不是浏览器布局或辅助技术验证；本实施会话没有声称真实浏览器独立验收。未修改工作流，无新增工作流检查需求。未执行远端 CI、部署、PyPI 上传、提交、推送或打 tag。当前会话继续供主控基于冻结差异独立收口。
