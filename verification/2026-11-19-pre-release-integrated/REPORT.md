# 0.3.0 发布前综合验收

2026-11-19，主控独立验收通过。限流桶命令、只读 Admin、自定义背景图池、配置缓存与变更失效、Webhook 在同一宿主和同一用户会话中按预期协作。本轮未发现需交回实施会话修复的问题，提交内容仅为这份报告。

验收对象为 `main` 的 `d874839c589fd9ef1bacafff456336299f0608dc`。从 `187016a` 到该提交依次包含限流命令 `d375777`、背景池 `e41baeb`、配置缓存 `5cd27b2`、Webhook `3b8aac8` 和 Admin `d874839`。从 Git 导出候选源码，另建虚拟环境、数据库、素材、测试证书和输出目录。本报告的数字均来自本轮执行。

## 同一会话里的五项功能

下列流程分别对候选源码和安装后的 wheel 执行一次。发题、验证和消费使用 Django HTTP 入口及真实 CSRF 会话，测试固定时钟和出题坐标。Webhook 指向独立的本机 HTTPS 接收端，接收时用另一数据库连接读取已提交的挑战状态。统计页使用单独的只读 staff 测试会话，完整的 Admin 登录流程在后文的真实浏览器中复测。

| 步骤 | 观测结果 |
| --- | --- |
| 用宿主 PNG 发两题，验证其中一题并保留未消费凭证。随后移除图片，原地把用途策略从 61 秒、2 次、容差 1 调为 93 秒、6 次、容差 5。 | 前两题取到素材像素。下一题调用程序背景生成器，响应和数据库都采用新策略。旧题的到期时间、次数及容差仍保留发题快照。 |
| 原地删除 `demo`，先保留其策略项，再移除该项。 | 配置不一致时验证返回 503。配置有效后，发该用途的新题返回 400，旧题返回 `invalid_challenge`，旧凭证消费返回 403。旧题尝试数仍为零，旧凭证仍未消费，接收端没有新增通知。 |
| 显式恢复同名用途，在验题写库事务中验证并消费，随后回滚。接着让回调接收端返回 503，再分别提交验证和消费。 | 回滚后独立连接仍看到未验证、未消费，接收端没有新增通知。两次真实提交后，接收端依次读到已验证、已消费；业务请求均成功，凭证重放返回 403。整条流程恰有 3 个签名通知，即最初验证 1 个、最后验证及消费各 1 个。 |
| 让只读 Admin 和命令观察上述请求产生的五个真实限流桶。另放入一个刚还清的桶、一个仍冷却的桶，以及两个分别早于和等于采样时刻到期的遗留桶。执行实际清理。 | 清理前后，HTML 与命令 JSON 每组每列及采样时间相等。当前桶的总数、债务、冷却、可清理数从 **7 / 5 / 1 / 1** 变为 **6 / 5 / 1 / 0**；遗留桶从 **2 / 1** 变为 **1 / 0**。五个真实桶和挑战状态全部保留。 |

删除用途的约束在禁用期间生效。另用尚在有效期内的一张旧题和一个未消费凭证复测，宿主显式恢复同名用途后两者又可使用，凭证再次消费仍被拒绝。

## 限流统计、权限与实际清理

- **统计与清理边界。** 对每组分别组合债务和冷却截止时间早一微秒、恰好相等、晚一微秒的九种情况。固定同一采样时刻，用夹具逐键计算预期，再运行 `prune_slider_captcha` 核对被删键和保留键。结果在 SQLite 3.54.0、PostgreSQL 18.7 和 MySQL 8.0.46 上相同。

  | 采样阶段 | 当前桶 | 有债务 | 冷却中 | 当前可清理 | 遗留桶 | 遗留可清理 |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | 执行清理前 | 189 | 63 | 63 | 84 | 6 | 2 |
  | 执行清理后 | 105 | 63 | 63 | 0 | 4 | 0 |

  当前桶只有在债务和冷却均已到期时才可删除，等于采样时刻也计入。遗留桶使用严格早于条件，到期恰等于采样时刻的两条记录均保留。将当前桶、遗留桶路由至不同写库，在默认库放入干扰数据。统计期间三个连接均设为只读；文本和 JSON 每次分别在两个写库各执行一次 SELECT。

- **页面与命令。** 另一组夹具设置 288 个当前桶和 9 个遗留桶，六组计数各不相同，覆盖未知格式。中、英文双站点实际渲染的 HTML 与 `--json` 逐项一致。当前桶四列合计为 288 / 150 / 108 / 84，遗留桶为 9 / 4。采样时钟前进两微秒后均可清理。空库、混合和推进时钟三个快照下，两种命令输出与加入 Admin 前的 `3b8aac8` 逐字节一致。
- **访问权限。** 在 10 类身份上核对首页入口和直接访问。启用该视图的站点要求活动 staff 同时具备 `view_ratelimitstate`、`view_ratebucket` 并通过站点自身的权限判断；个人授权、组授权、超级管理员、授权后撤回均已覆盖。演示账号升权后，旧演示会话直访统计页转回 Admin 登录。仅有一项查看权限或仅有 change 权限的 staff 收到 403。
- **只读行为。** 授权 GET、HEAD 对两表各执行一次聚合；HEAD 响应体为空。持有效 CSRF 提交 POST、PUT、PATCH、DELETE、OPTIONS 均返回 405，缺 CSRF 的 POST 返回 403；这些请求没有查询桶表。逐字段比对三库数据，读前读后一致。页面未显示原始桶键或变更入口。

## 素材、缓存与回调的专项复测

| 功能 | 独立证据 |
| --- | --- |
| 图片和前端协议 | 同一素材用两个预设位置发题，逐像素核对缺口正好覆盖对应遮罩、拼块内部来自原图对应区域，素材文件摘要不变。固定装饰随机源后，默认背景、拼块及透明通道与背景池引入前的 `d375777` 摘要一致。PNG、调色板 PNG、JPEG、混合图片池、失效素材及 Pillow 解码警告均覆盖。新旧流程的九个发题字段一致，图像仍为 320 × 160 背景和 44 × 44 PNG 拼块，响应未带本地路径或素材元数据。 |
| 配置缓存 | 分别用 Django 设置覆盖、直接重新赋值和集合原地修改预热后的配置。下一次调用即读取新值；删除用途后，新题、旧挑战、旧凭证和已经成功过的表单均拒绝。并发测试刻意延迟一个读取者，后续读取仍取新配置。切换 80 组配置并查询 150 个未知用途后，两处缓存各不超过 16 项。原地调整限流容量时，已有债务仍有效。 |
| Webhook 时序与失败隔离 | 默认配置下正常验证及消费产生零次外发。分别覆盖写库提交、外层回滚、保存点回滚、多凭证表单和手动事务。让接收端超时、返回 503、返回 307、证书不受信或连接失败，并占满四个发送名额；业务成功状态和单次消费约束均保持。307 未跟随跳转，名额释放后后续通知可送达。 |
| Webhook 数据 | 源码和 wheel 的专项测试各收到 22 个本机 HTTPS 回调，另各收到综合流程中的 3 个。用收到的原始字节独立验算 HMAC-SHA256，检查请求头和 JSON 字段白名单。正文只有 `event` 与 `notification_id`，同秒通知 ID 各异；未发现 token、会话标识、挑战 ID、用途、IP、签名密钥或私有请求标记。 |

真实 Chrome 158.0.8127.36 中，安装包的演示页先使用宿主图片，再实际撤下文件、刷新并使用程序背景。两次均完成图片解码、键盘验证和受保护提交，数据库恰有两条已消费记录。另用只读 staff 在原生与 Nova Admin 分别完成验证码及密码登录，在 1180 和 375 像素宽度下比较所有可见统计与命令，末列可达，面包屑可返回本站首页。

## 构建、环境与回归

在 macOS 27.2.1 arm64、Python 3.12.16 下从候选源码一次构建 wheel 和 sdist。版本及 tag 字符串校验、两包的 `twine check --strict` 均通过。发布检查逐文件比对了 34 个运行文件，包含模板、静态资源、翻译和迁移。以下为此次实际测试的产物。

| 文件 | SHA-256 |
| --- | --- |
| `nova_slider_captcha-0.3.0-py3-none-any.whl` | `c4a1568fd85b619e5a99d153a5d280ac465f9c2b33b0857560ae8e11c16b7283` |
| `nova_slider_captcha-0.3.0.tar.gz` | `f1fd69cde739cdacb4fb8c885d51aada167f5bfc78d4830b5c0f408cad682edd` |

每个配对各跑源码及同一个已安装 wheel，分别使用原生与 Nova Admin、独立 SQLite 文件，并断言实际模块来源。每个环境均通过 Django checks、迁移漂移检查和完整测试。Nova 主题取自 `django-nova-admin@376bce7c8ceeeeb5f0a62f07f969227eb66e4adf`。

| Python | Django | Pillow | 四种环境的完整测试 |
| --- | --- | --- | --- |
| 3.10.20 | 5.2.17 | 12.2.0 | 各 201 项通过 |
| 3.11.12 | 5.2.17 | 12.3.0 | 各 201 项通过 |
| 3.12.16 | 5.2.17 | 12.3.0 | 各 201 项通过 |
| 3.12.16 | 6.1.2 | 12.2.0 | 各 201 项通过 |
| 3.13.12 | 6.1.2 | 12.3.0 | 各 201 项通过 |
| 3.14.7 | 6.0.9 | 12.3.0 | 各 201 项通过 |

- Python 3.12.16 / Django 5.2.17 / Pillow 12.3.0 源码专项 76 项通过。完整 201 项覆盖率为语句 954/966（98.76%）、分支 248/254（97.64%），表单语句与分支均为 100%。Ruff、依赖检查、覆盖门槛及其反例、限流升级（含无时区模式）、挑战策略旧数据升级均通过。
- 同一个 wheel 在 PostgreSQL 18.7（psycopg 3.3.9）的五个专项模块跑过 76 项，在 MySQL 8.0.46（mysqlclient 2.3.2，`utf8mb4_0900_ai_ci`）的统计/Admin、图片、策略、Webhook 模块跑过 47 项。两者另做了上表的实际清理核对。升级子测试按仓库脚本另起 SQLite；PostgreSQL 的首次尝试因子进程清除 `PYTHONPATH` 而无法导入验收配置，分别指定父进程和升级子进程的配置后整组复跑通过。两个数据库实例仅使用任务私有 Unix socket，验收后均已关闭。
- Node 24.21.0、npm 11.19.0 下，组件测试 49 项、Django test client + jsdom 联调 20 项、独立 Worker 示例测试 29 项均通过。

复跑时从上述候选提交导出源码，在仓库根目录执行。以下命令中的 `$WORK` 为新建工作目录，`$RUNTIMES` 为六个配对所需解释器的根目录，`$NOVA_SOURCE` 为上述主题提交的 `django-theme/src`。使用已安装相应依赖的任务虚拟环境；Nova 主题也须能由矩阵虚拟环境中清除 `PYTHONPATH` 的升级子进程导入。构建工具为 build 1.6.1、twine 7.0.0，覆盖工具为 coverage 7.17.0，Ruff 为 0.17.2。

```sh
export DJANGO_SETTINGS_MODULE=tests.settings PYTHONPATH=src:.
export NOVA_TEST_DB="$WORK/source.sqlite3" COVERAGE_FILE="$WORK/.coverage"
python -m django check
python -m django makemigrations nova_slider_captcha --check --dry-run
python -m coverage run -m django test tests --noinput -v 1
python -m coverage combine --keep
python -m coverage json -o "$WORK/coverage.json"
python scripts/check_coverage.py "$WORK/coverage.json"
python scripts/test_coverage_gate.py "$WORK/coverage.json"
python scripts/test_rate_upgrade.py
python scripts/test_rate_upgrade.py --naive-time
python scripts/test_policy_upgrade.py
python scripts/check_release.py --tag v0.3.0
python -m build --installer uv --outdir "$WORK/dist"
python -m twine check --strict "$WORK"/dist/*
python scripts/check_release.py --dist "$WORK/dist"
python scripts/test_matrix.py --runtimes "$RUNTIMES" --wheel "$WORK"/dist/*.whl \
  --work "$WORK/matrix" --nova-source "$NOVA_SOURCE" --workers 3
npm ci --ignore-scripts
npm test
NOVA_PYTHON="$(python -c 'import sys; print(sys.executable)')" NOVA_DOM_REPORT="$WORK/dom.json" npm run test:dom
npm run test:worker
```

验收范围为本地候选源码和上述安装包。24 个完整环境均使用 SQLite；PostgreSQL 和 MySQL 的结论限于列出的专项和清理数据。Webhook 接收端为本机 TLS 服务。生产流量、跨主机复制、外部接收方及远端 CI 均未验证。本轮未推送、打 tag 或发布。
