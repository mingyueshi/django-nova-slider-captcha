# 人工复核核实与修复

日期：2026-10-29（Asia/Shanghai）。基线 `75117ebdfc032d00e140d050fcc2e7fe9b571e52`，开始时工作区干净；本报告针对该提交后的未提交差异。此轮由同一会话复核、修改与自测，没有另设实施会话，不将这些结果称为独立验收。没有提交、推送、打 tag、创建 Release、上传 PyPI 或部署。

## 逐项结论

| 人工观察 | 核实与处理 |
|---|---|
| 校验中焦点丢失、答错后不恢复 | 成立。在真实 Chromium 加载基线 JS 重现 checking / ready 的 activeElement 均为 BODY。修复后 checking 保持 range 焦点，以 aria-disabled 标注暂不可操作，并阻止键盘/指针修改及重复提交；Tab 可正常离开，无异步 refocus。覆盖直接重试、Tab 离开及等待时刷新后的迟到响应。 |
| 子进程依赖 PYTHONPATH | 成立。两个升级脚本和会话探针显式把仓库根加入 sys.path，不加入 src，保留 wheel 测试的安装来源。相关回归启动子进程前主动删除 PYTHONPATH，使 CI 也持续覆盖该条件；另在清除 PYTHONPATH 的 editable 环境重新执行完整后端测试。 |
| 0.3.0 证据缺口 | 总入口陈旧成立；“没有新证据目录”不符合当前仓库，2026-10-26/27 已有实施、独立报告和日期目录。VERIFICATION 改为版本索引，旧结果保留，export-checks.json 不改写历史；本轮另建日期目录。 |
| overlay 双份可访问状态 | 成立，固定 aria-hidden=true；原 role=status 保留。DOM/ARIA 与浏览器检查不能代替人工屏幕阅读器体验。 |
| dragging 死状态 | 成立，删除重复布尔值与对应断言，继续以 activePointerId 判定、释放和隔离指针。原多指/取消/刷新回归保留。 |
| CI DOM 数据库变量无效 | 成立，移除无效 step.env；桥在 settings 初始化前指定自身临时库，使 default 和派生 captcha/replica 路径都在该临时目录。DOM 只迁移和使用 default，其他别名按需使用时才应迁移。 |
| OIDC job 浮动第三方 action | 成立。固定 pypa/gh-action-pypi-publish 至上游 v1.14.3 / 7245906fb61fa33a13554f9d5fb856fe61758086。job 仍只下载已测试 artifact 并上传，未增加构建、安装或执行项目脚本；actionlint 通过。 |
| 本地矩阵漂移 | 成立。六组配对与 tests.yml 一致，覆盖 Django 5.2.17/6.1.2/6.0.9 及 Pillow 12.2.0/12.3.0。运行时支持 uv/pyenv 布局并记录实际补丁版；报告输出到指定 work 目录，不再覆盖根目录历史 matrix-results.json。Nova profile 通过可选 --nova-source 启用。 |
| Node 下限缺失 | 成立。package.json/lock 声明 >=22.13.0；该版本可直接导入 node:sqlite，22.5 还需要额外启动标志。CI 保持 Node 24；下限版本实际重跑 Worker 测试。Django 普通接入不增加 Node 依赖。 |
| issue/consume 走 default | 不成立。Django ORM create/update 自动选择写路由；现有三个独立 SQLite alias 的回归验证非默认写库、滞后副本、消费一次与多凭证回滚。保留实现，没有无故固定 default；未验证 PostgreSQL/MySQL 复制或跨库事务。 |
| session_backend 仅匹配字面路径 | 成立，检查 SessionStore 是否继承 Django DB SessionStore；新增 custom_db/custom_cached_db 新进程探针。缺少 sessions app 时 E008、init 503 以及直接 issue 拒绝均覆盖，其他自定义后端继续遵循自身契约。 |
| Worker submit 无限流 | 成立。新增独立 60/session、240/IP 的 GCRA，先 IP 后 session；错误凭证和 purpose 切换也计费，拒绝不消费有效凭证，已有动作额度不变。补精确补充、共享 IP、存储故障拒绝回归。 |
| Worker 入口无测试、重复常量 | 成立。测试实际 worker.fetch 的完整链路、未知路径、错误方法及缺少 DB；TTL、次数、容差统一为内部常量，SQL 使用绑定参数。Worker/Django 既有状态码/原因码差异保留；新增 submit 429 已写入说明。 |
| .mimosa/.video_agent 未忽略 | 当前不成立。基线 .gitignore 已包含两条目录规则，git check-ignore 均命中；未修改或删除这些目录，也未纳入证据。 |
| demo 只挂 demo_urls 会 500 | 属已声明接入前提，README 要求同时挂核心 urls；不扩展 demo-only 接入契约。 |
| init 的 rate_limit 返回值被丢弃 | 属有意配置校验，补注释说明已有绑定无需扣额仍需校验配置。 |
| verify 并发竞争返回 invalid_challenge | 保守拒绝且保留兼容原因码，本轮不更改。 |

## 验证与证据

本轮机器摘要、逐 profile 日志、浏览器脚本/结果和源码文件哈希位于 [新证据目录](../verification/2026-10-29-review-fixes/)。完整命令由该目录 commands.json 记录，路径仅作脱敏替换。SQLite 数据库、虚拟环境、构建物及 Playwright 会话均使用新的任务临时目录，不操作 demo.sqlite3。源码和 wheel 的结果分别记录，构建一次并安装同一个 wheel，不把 manage.py 的 src 注入当作安装包验证。

- Python 3.12.14 / Django 5.2.17 / Pillow 12.3.0 的 editable 环境，在无 PYTHONPATH 下执行 149 项完整后端测试；其中包含升级脚本子进程、写路由和八种会话引擎的新进程验证。
- coverage.py 7.17.0 包含子进程：包纯语句 695/705（98.58%）、纯分支 177/180（98.33%），forms 语句 142/142、分支 44/44。原门槛及十二类反例检查通过，没有改门槛或排除源码。
- Node 24.21.0：49 项组件、20 项 Django-client DOM、29 项 Worker SQL/路由检查；Node 22.13.0：29 项 Worker 检查。DOM 替代图片 decode，不能证明浏览器焦点行为。
- 真实 Chromium 的基线复现与四组修复检查，涵盖中文/英文、浅/深色、1280/360px 视口及 240px 组件、输入守卫、Tab 与刷新竞态；精确浏览器版本见 browser.json。使用真实 Django HTTP 响应，仅在页面 fetch 包装层延迟交付 verify 响应以检查等待状态；没有记录 token、session 秘密或答案。
- Ruff 0.17.2、actionlint 1.7.12、pip check、Django checks、迁移漂移、版本/分发内容和 twine strict 检查；本次 wheel/sdist 的 SHA-256 见 summary.json。
- 同一 wheel 的六组 CI 配对各执行 source/wheel 检查与完整后端测试，实际 Python 补丁版和逐 profile 结果以 matrix-results.json 为准。本轮默认原生主题 profile；不将可选 Nova 路径或历史 Nova 验收称为本轮重跑。

复现主要命令（仓库根目录，`NOVA_REVIEW_WORK` 为新临时目录，`NOVA_REVIEW_PY` 指向任务环境解释器）：

```sh
env -u PYTHONPATH DJANGO_SETTINGS_MODULE=tests.settings NOVA_TEST_DB="$NOVA_REVIEW_WORK/source.sqlite3" "$NOVA_REVIEW_PY" -m django test tests --noinput -v 1
npm ci --ignore-scripts
npm test
NOVA_PYTHON="$NOVA_REVIEW_PY" NOVA_DOM_REPORT="$NOVA_REVIEW_WORK/dom.json" npm run test:dom
npm run test:worker
"$NOVA_REVIEW_PY" -m build --outdir "$NOVA_REVIEW_WORK/dist"
"$NOVA_REVIEW_PY" -m twine check --strict "$NOVA_REVIEW_WORK/dist/"*
"$NOVA_REVIEW_PY" scripts/check_release.py --dist "$NOVA_REVIEW_WORK/dist"
"$NOVA_REVIEW_PY" scripts/test_matrix.py --runtimes "$NOVA_REVIEW_WORK/runtimes" --wheel "$NOVA_REVIEW_WORK/dist/nova_slider_captcha-0.3.0-py3-none-any.whl" --work "$NOVA_REVIEW_WORK/matrix"
```

## 未验证范围

本轮未运行远端 GitHub Actions、发布 OIDC 上传、PyPI 上传、公开 Worker/D1 或真实 workerd、PostgreSQL/MySQL、生产负载、iOS/Android 真机及人工屏幕阅读器。已有工作流和本地矩阵不构成上述验收。0.3.0 继续处于发布准备状态。
