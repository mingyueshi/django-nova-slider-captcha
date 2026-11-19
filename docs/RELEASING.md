# 0.3.0 发布说明与流程（待首次发布）

2026-11-19，候选代码 `d874839` 通过五项升级的本地综合验收，验收报告已在 `c9db8fb` 提交。0.3.0 尚未上传 PyPI。正式发布流程须另行授权。

## 升级后的默认行为与接入

| 宿主需求 | 0.3.0 的行为与操作 |
| --- | --- |
| 查看当前限流桶 | 安装 Django app 后按需运行 `python manage.py slider_captcha_rate_stats`。默认输出文本，监控脚本可加 `--json`。命令只读，原有清理任务继续运行 `prune_slider_captcha`。 |
| 在 Admin 查看同一统计 | 普通 Django Admin 默认没有统计页。挂载 `SliderCaptchaAdminSite` 后，给通过本站授权的活动 staff 同时授予 `nova_slider_captcha.view_ratelimitstate` 和 `nova_slider_captcha.view_ratebucket`。只读页面与命令使用相同的写库聚合。 |
| 换用宿主图片 | 默认生成程序背景。设置 `NOVA_SLIDER_BACKGROUND_IMAGES` 为本地 JPEG、PNG 绝对路径列表或元组。每题独立生成缺口和拼块，本题尝试的素材都不可用时自动回退。已有前端继续使用相同字段和图片尺寸。 |
| 更新挑战策略或禁用用途 | 各进程自动复用已校验的全局策略和小型用途白名单，无需缓存服务。将设置更新到每个 worker，该进程下次读取即生效。旧题保留签发策略；禁用用途时同步删除策略覆盖，禁用期间旧挑战和旧凭证都被拒绝。 |
| 接收服务端通知 | Webhook 默认关闭。用 `NOVA_SLIDER_WEBHOOK` 指定可信 HTTPS 地址和独立的 32 字节密钥（编码为 64 个小写十六进制字符）。验证或消费成功后，仅在写库事务提交后才尝试投递。回调失败不影响验证或消费。接收方对时间戳和原始正文验签，正文仅含 `event` 与 `notification_id`。 |

五项升级沿用现有表结构。从 0.2.0 升级仍须在停写后执行 `0003_challenge_policy`；已经应用该迁移的宿主无需为这五项再迁移。详细设置、权限、统计字段与签名格式见 [README](../README.md)，版本变更见 [CHANGELOG](CHANGELOG.md)。

## 本地验收覆盖

| 环境 | 已验证范围 |
| --- | --- |
| SQLite 完整矩阵 | 六组 Python/Django/Pillow 配对，各跑源码和同一个已安装 wheel，各测原生与 Nova Admin。24 个环境分别通过 201 项完整测试。 |
| 数据库专项 | 同一个 wheel 在 PostgreSQL 18.7、MySQL 8.0.46 上分别通过 76 项、47 项专项。与 SQLite 使用同一边界数据，三者都实际删去预计可清理的 84 条当前桶和 2 条遗留桶；升级子测试使用独立 SQLite。 |
| 浏览器与前端 | 真实 Chrome 验证原生与 Nova Admin 登录、桌面和窄屏统计，以及素材撤下后的键盘验证与提交。Node 24 下另通过组件 49 项、Django client + jsdom 联调 20 项、独立 Worker 示例 29 项。 |
| Webhook | 本机 HTTPS 接收端从独立数据库连接确认提交后才收到通知，回滚没有通知。验签、正文白名单、超时和接收端返回 503 时的单次消费均已核对。 |

报告内的 wheel、sdist 哈希对应候选代码 `d874839`。README 会进入包元数据，正式发布应以发布工作流针对最终 tag 构建、测试并上传的同一份产物为准。远端 CI、跨主机复制、外部接收方和生产流量仍无本轮验收结果。[综合验收报告与产物摘要](../verification/2026-11-19-pre-release-integrated/REPORT.md)

## 本地构建与验收

构建工具使用 Python 3.12+；运行包仍支持 Python >=3.10。使用独立构建环境，避免更改生产或其他共享环境：

```sh
python3.12 -m venv /tmp/nova-slider-build
/tmp/nova-slider-build/bin/python -m pip install build twine
/tmp/nova-slider-build/bin/python scripts/check_release.py --tag v0.3.0
/tmp/nova-slider-build/bin/python -m build --outdir /tmp/nova-slider-dist
/tmp/nova-slider-build/bin/python -m twine check --strict /tmp/nova-slider-dist/*
/tmp/nova-slider-build/bin/python scripts/check_release.py --dist /tmp/nova-slider-dist
```

输出目录必须为空或新建，只接受一个对应版本的 wheel 和一个 sdist。版本检查比对 pyproject.toml、Python `__version__`、package.json / lock 和 README；拒绝不完全匹配的 tag 及预发布格式。构建物检查逐文件比对整个 app，包含静态、模板、翻译和全部迁移，检查 README 无相对 Markdown 链接，并检查核心 sdist 文件。twine check 通过仅说明分发元数据可解析，不代表 PyPI 已接收、项目名可用或账号有权限。

CI 的 `tests.yml` 在 push、PR、手动运行和 reusable 调用时构建一份 wheel/sdist，检查后保存为不可变的 `python-distributions` artifact；六格 Python/Django/Pillow source 测试和 wheel 安装测试使用同一份构建物。源码与 wheel 测试各有独立临时数据库；只有 step.env 使用 runner.temp，避免 job.env 不支持该上下文造成工作流未启动。另保留组件、Django-client DOM 和 Worker 检查。GitHub 的上下文可用范围见 [官方上下文表](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability)。

首次本地矩阵、真实浏览器与远端 CI 的状态分别记录，不能互相代替。旧 0002→0003 迁移回归使用独立临时 SQLite；生产升级需先停止旧写入，执行 migrate，再恢复服务。不要把旧行快照改成当前更宽松配置。

此前 0.3.0 的日期证据及 0.2.0 历史记录见 [验证索引](VERIFICATION.md)。2026-10-29 的会话引擎修复见 [补充复核](2026-10-29-session-engine-followup.md)，同日其他检查见 [复核报告](2026-10-29-review-fixes.md)。发布 job 的 `pypa/gh-action-pypi-publish` 固定为上游 [v1.14.3](https://github.com/pypa/gh-action-pypi-publish/releases/tag/v1.14.3) 对应的完整 commit SHA；升级时须核对上游 release/commit 并复核工作流，不恢复浮动分支。

## 将来首次配置 Trusted Publishing

待发布时由维护者确认 `nova-slider-captcha` 名称和账号权限，在 [PyPI 的 Publishing 管理页](https://pypi.org/manage/account/publishing/) 添加 pending publisher，字段为：项目名 `nova-slider-captcha`，GitHub owner `mingyueshi`，repository `django-nova-slider-captcha`，workflow filename `publish.yml`，environment `pypi`。pending publisher 不会提前创建或保留项目；首次成功发布才创建项目。流程依据 [PyPI 首次项目说明](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)。若项目已经存在，使用该项目的 Publishing 页面添加相同 publisher，按 [现有项目说明](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) 操作。

在 GitHub 仓库建立 `pypi` environment，按账号计划可用能力配置人工审核和受限 tag；这些是账号/仓库外部设置，本次没有执行。环境名与 PyPI 表单必须完全一致。无需在仓库放长期 PyPI token、用户名或密码；官方流程由发布 job 的短期 OIDC 身份完成，见 [PyPI 使用说明](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。

## 将来执行发布

1. 独立验收代码、迁移、包内容、版本、文档与工作流；提交并推送经过审查的更改，确认远端 Tests 全部通过。
2. 维护者确认 publisher 和 pypi environment 已配置。对同一验收提交创建 `v0.3.0` tag，并发布对应的正式 GitHub Release。此动作会启动上传流程；草稿、prerelease、PR、普通 push、Tests 的 workflow_dispatch 均不会触发上传。
3. `publish.yml` 先校验 tag 与源码元数据，调用同一版本的 reusable Tests 工作流，重新构建并完整验收 artifact；不是复用任意旧 workflow run 的产物。
4. 仅当版本检查和全部测试成功，独立 publish job 才进入 pypi environment。这个 job 只有下载 artifact 和官方发布 action，无源码 checkout、构建、依赖安装或业务脚本；只有它持有 `id-token: write`。上传的是所有 wheel 测试已使用的同一个 `python-distributions` artifact，不会再次构建。
5. 维护者确认 PyPI 页面、文件哈希和安装结果，再将“待发布”更新为实际发布状态；独立记录发布时间和远端 run URL。本次不代做这些步骤。

上传使用 [PyPA 官方 action](https://github.com/pypa/gh-action-pypi-publish)。构建/测试 job 不持有发布 OIDC 权限；发布 job 位于顶层 workflow，避免将 Trusted Publishing 本身放进 reusable workflow。版本不可覆盖；若部分上传或运行失败，先核对 PyPI 实际文件状态和失败原因，不启用 `skip-existing` 来隐藏结果，也不无依据改版本重试。

## 未来版本维护

每次版本同步项目元数据、`__version__`、前端 package/lock、README 和 CHANGELOG；tag 必须严格为 `v` + 稳定版本。改工作流 filename 或 environment 后也需更新 PyPI publisher。不要删除 RateBucket 或开放 TOKEN_TTL 来凑版本；这些需要独立迁移/清理设计和验证。单一 mask 不阻碍本次发布，随机形状不能替代服务端限流、单次凭证和业务授权。

## 当前 0.3.0 待发布接入变化

默认挂载仅核心 API，演示须显式 include nova_slider_captcha.demo_urls，旧 demo 反解名改 api-root，演示消费移到单独挂载。自定义 namespace 通过 Widget.api_root 明确指定；init/challenge/verify 协议不变。首次发布前按 README 迁移现有源码接入，不能仅更新包后保留旧演示 URL。

兼容范围为 Pillow >=12.2,<13，CI 精确锁定两端 12.2.0 / 12.3.0；六格代表性配对覆盖 Python 3.10–3.14 和 Django 5.2 / 6.0 / 6.1。不是声明所有交叉组合均已实测。空 templatetags 已删除；check_release 会比对运行文件集合和依赖元数据，防止旧文件残留。演示 URLConf、模板、静态、翻译和全部迁移必须一起进入 wheel/sdist。

[部署说明](DEPLOYMENT.md) 包含 ASGI/WSGI REMOTE_ADDR 的具体映射责任和生产 check --deploy、prune 监控；替代入口由宿主实现，未提供可用替代流程时不要配置占位链接。显式未知但格式有效的语言现回退英文，未指定/空白或格式非法输入仍默认简中；zh系列简中，en系列英文。未新增Django翻译目录，迁移语言规则见README。新结果见 [后续实施自测](2026-10-26-followup-implementation.md)；远端 CI/账号/上传仍留待实际发布授权。

嵌套命名空间下，宿主可显式组合可选演示：

```python
from django.urls import include, path
from nova_slider_captcha import views

preview_patterns = [
    path("", views.demo, {"api_root": "portal:public_captcha:api-root"}, name="index"),
    path("submit", views.submit, name="submit"),
]
# 放在 portal 的 urlpatterns 之中：
urlpatterns = [
    path("proof/", include("nova_slider_captcha.urls", namespace="public_captcha")),
    path("preview/", include((preview_patterns, "nova_slider_captcha_demo"), namespace="preview")),
]
```

## 开发静态检查

首次发布前运行 `python -m pip install -r requirements-lint.txt` 与 `ruff check .`。Ruff精确锁定0.17.2、target py310，选择错误类规则，未启用格式化/mypy，详情见 [STATIC_CHECKS.md](STATIC_CHECKS.md)。sdist包含requirements-lint.txt和pyproject配置；不增加运行依赖。独立lint job无OIDC权限，发布job仍只下载同一已测构建物和上传，不运行新的检查代码。

2026-10-26 的 i18n 和 Ruff 检查保留了当时的实施自测及独立复核，涵盖构建、六组源码与 wheel 配对、真实浏览器和静态检查反例。[实施记录](2026-10-26-i18n-lint-implementation.md) · [独立验收](2026-10-26-i18n-lint-independent.md)
