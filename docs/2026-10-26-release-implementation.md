# 2026-10-26 0.3.0 发布准备实施自测

基线 `main` / `2aca457`，实施会话本地记录。当前版本为 **0.3.0 待首次 PyPI 发布**。用户已选择本轮只做准备：没有提交、推送、打 tag、创建 Release、上传 PyPI、配置账号/publisher、启动服务或改线上数据。没有修改共享 Python 环境或覆盖旧验证记录；主控的 release-independent 文档和目录由主控维护。

## 配置与迁移

新增动态 `challenge_policy()`，只接受严格整数，bool / 字符串 / 浮点 / 负值和超限全部拒绝：

| 设置 | 默认 | 允许范围 |
|---|---:|---:|
| NOVA_SLIDER_CHALLENGE_TTL | 120 秒 | 30–600 秒 |
| NOVA_SLIDER_MAX_ATTEMPTS | 5 | 1–20 |
| NOVA_SLIDER_TOLERANCE | 4 原图像素 | 0–10 |

系统检查为 `E006`；错误策略下签发/校验直接调用抛 ValueError，consume 返回 False，JSON API 返回 503 configuration_invalid，通用 Form/Mixin 拒绝。值支持 override_settings，默认行为不变。有效的新配置仅影响新挑战，不重解释在途挑战。

Challenge 新增 max_attempts / tolerance 字段，签发写快照，TTL 仍写 expires_at。迁移 `0003_challenge_policy` 用固定 literal 默认 5/4 填旧行，完全不读取部署的新配置，不重置 attempts、时间、solved、token 或已消费状态。校验按持久化快照比较，原子 UPDATE 使用 `attempts < F(max_attempts)` 并保持快照谓词。迁移回归在独立临时数据库真实执行 0002→0003，并证明旧挑战在新配置20/10下仍不能获得新额度或容差。

TOKEN_TTL 固定 60 秒，图片尺寸固定 320×160 / 44，未开放新配置。测试覆盖 600 秒挑战临近到期签发凭证及 prune 保留；没有把延长 token TTL 混进本轮。保留 RateBucket 和单一 mask；README 说明增加次数、容差或 TTL 可以削弱拦截效果，形状随机化不能阻止通用视觉/像素解题。

## CSS 与发布准备

- 独立嵌入提供暗色兜底；Django data-theme 和 Nova 显式 mode 类覆盖 OS 偏好，宿主语义变量仍优先。link/error 语义 token 优先于装饰 accent/danger，避免 Django 黄色 accent 被拿来作文字。
- success 使用独立可覆盖语义色与不透明深色面板。主控发现原 error/expired 93%透明背景受亮底图影响后，改为不透明 nsc-panel，补原生 Django 暗色 e35f5f/212121 对比度和遮罩规则回归。
- 窄容器用流式留白和换行，无新增断点或无效果 reduced-motion；继续使用统一手柄变量。宿主自定义色仍需由接入方检查实际对比度。
- Python、__version__、package.json / lock、README 和 CHANGELOG 同步 0.3.0。project.urls 与实际 origin `mingyueshi/django-nova-slider-captcha` 一致；README Markdown 链接改绝对 GitHub URL，PyPI 页面可导航。
- MANIFEST 包括运行资源、测试 fixture、脚本和维护文档；不再把 verification 旧日志打入 sdist，也排除数据库/缓存。wheel/sdist 逐一比对全部 **29 个运行文件**，包含静态、模板、翻译和 0003 迁移。
- Tests 改为明确四格 Python/Django 配对并真实安装 matrix.django。原 job.env 的 runner.temp 解析错误已修复，临时路径位于 step.env；源码/wheel 数据库区分 Python、Django 和 profile。build job 构建 wheel/sdist、twine check 和 payload 检查，所有 wheel 测试用同一 artifact，前端 DOM/Worker 保留。
- publish.yml 只由正式 release.published 触发；拒绝草稿、prerelease、错误 tag。版本 job 核对严格 vX.Y.Z 与全部元数据，verify 调 reusable Tests；只有测试都通过才进入 pypi environment 的 publish job。仅该 job 有 id-token:write，无 checkout/build/install/script，下载并上传同一 python-distributions artifact；不从任意旧 run 下载，也不启用 skip-existing。
- [RELEASING.md](RELEASING.md) 写明未来首次 pending publisher、environment、tag/Release 和验收步骤。本次未执行外部设置。参考 [PyPI 官方首次项目说明](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) 和 [PyPA 官方 action](https://github.com/pypa/gh-action-pypi-publish)，没有要求或创建长期 token。

## 实际本地结果

macOS arm64，SQLite、Pillow 12.2.0；Node 24.21.0，jsdom 26.1.0。四个矩阵环境均为实施自建 `/tmp/nova-slider-release-impl-...-20261026`，没有更改主控/历史环境。

| Python / Django | Source 完整测试 | 同一 wheel 完整测试 | check / 迁移漂移 / uv pip check |
|---|---:|---:|---|
| 3.10.20 / 5.2.17 | 110 通过 | 110 通过 | 全通过 |
| 3.12.14 / 5.2.17 | 110 通过 | 110 通过 | 全通过 |
| 3.12.14 / 6.1.2 | 110 通过 | 110 通过 | 全通过 |
| 3.13.12 / 6.1.2 | 110 通过 | 110 通过 | 全通过 |

每格零跳过，运行总计八个 profile；各自独立 NOVA_TEST_DB。相对基线新增 11 项策略测试，涵盖动态边界/类型、配置错误不写入、签发快照、旧行升级、严格/宽松配置互换、精确过期、固定 token 期限、prune 和两个并发验证回归。原 Admin、通用表单、用途/限流、消费原子性、语言和图片测试一起运行。

| 其他检查 | 实测 |
|---|---|
| 组件 | 40 通过，含两项主题/对比度静态回归 |
| jsdom + 真实 Django test client | 12 检查通过 |
| 本地 Worker | 25 通过 |
| sdist 解包后完整测试（3.12 / 6.1.2） | 110 通过 |
| build wheel/sdist + twine check --strict | 通过 |
| check_release.py --tag v0.3.0 --dist | 29 文件逐一相同；元数据/链接一致 |
| tag 负向检查 | 缺 v、旧版本、rc、换行、注入形式均拒绝 |
| 两份 workflow actionlint 1.7.12 | 通过，无诊断 |
| git diff --check | 通过 |

已测包位于 `/tmp/nova-slider-release-impl-candidate-20261026/`，未上传：wheel 为 49,346 字节，sdist 为 145,825 字节。精确 SHA256 在 `matrix-final-results.json` / `artifacts.json`。此记录在构建后生成，不将自测报告视为运行 payload；当前运行源码与已测包的 29 文件仍完全一致。

## 命令与证据

[证据目录](../verification/2026-10-26-release-implementation/) 保留真实输出：

- 四格 `py310-dj5217-final.log` / `py312-dj5217-final.log` / `py312-dj612-final.log` / `py313-dj612-final.log`，摘要 `matrix-final-results.json`。
- `build-candidate.log`、`twine.log`、`payload.log`、`tag-guards.json`、`sdist-tests.log`、`artifacts.json`。
- `component-final.log`、`dom.log` / `dom.json`、`worker.log`。
- `actionlint-final.log` 是成功的空诊断输出，版本在 actionlint-version.log，二进制临时路径 `/tmp/nova-slider-release-impl-tools-20261026/actionlint`。

早期 wheel 身份断言把 `/tmp` 与 macOS 的 `/private/tmp` 当不同路径，导致本地 harness 中断，未进入那些 profile 的 wheel 测试；修复为两端 resolve 后重跑，旧日志保留，最终以 `*-final.log` 为准。GitHub 下载 actionlint 因 TLS 失败；Homebrew 下载到了 bottle，但后续 manifest 请求也失败。已将 bottle SHA256 与其缓存签名 package API 内的校验值比对，再从 bottle 提取 actionlint，本机实际运行 lint 成功；过程记录均保留，没有改全局网络或安装全局工具。

主要可复现命令：

```sh
# 实施自建 venv 已装对应 Django/Pillow；日志默认 x 模式，不覆盖旧记录。
/tmp/nova-slider-release-impl-build-20261026/bin/python \
  verification/2026-10-26-release-implementation/run_matrix.py \
  /tmp/nova-slider-release-impl-candidate-20261026/nova_slider_captcha-0.3.0-py3-none-any.whl new-label

/tmp/nova-slider-release-impl-build-20261026/bin/python -m build --outdir /absolute/new-dist
/tmp/nova-slider-release-impl-build-20261026/bin/python -m twine check --strict /absolute/new-dist/*
/tmp/nova-slider-release-impl-build-20261026/bin/python scripts/check_release.py --tag v0.3.0 --dist /absolute/new-dist
/tmp/nova-slider-release-impl-tools-20261026/actionlint
npm test
NOVA_PYTHON=/tmp/nova-slider-review-20261026/bin/python \
  NOVA_TEST_DB=/tmp/nova-slider-release-impl-dom.sqlite3 \
  NOVA_DOM_REPORT=/absolute/new-dom.json npm run test:dom
npm run test:worker
```

## 尚未执行的外部步骤与证据边界

本轮远端 Tests / Publish 工作流未运行；仅在本地 actionlint、构建和矩阵通过。PyPI 名称/账号权限、pending publisher、GitHub pypi environment 规则和 OIDC 真正上传未验证也未配置。待维护者选择实际发布时再按 RELEASING 执行；当前工作无需账号输入。

实施会话没有做真实浏览器布局、真机触控、屏幕阅读器、PostgreSQL/MySQL、生产负载、多主机代理或线上 Worker/D1 验证。jsdom 和对比度静态计算不能代替这些证据。主控真实浏览器、独立矩阵/负向包测试以 [独立验收](2026-10-26-release-independent.md) 为准，不计为本实施会话的测试。
