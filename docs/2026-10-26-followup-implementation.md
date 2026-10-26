# 2026-10-26 后续接入与出图实施自测

基线 `main` / `f3edfee`。开始时主控已有未提交的诊断复核报告及 docs/README.md 索引行，均保留；未编辑主控的诊断报告、followup-independent 报告或证据目录。当前仍为 **0.3.0 待首次 PyPI 发布**，没有提交、推送、tag、Release、上传、部署或启动项目服务，没有操作公共演示、线上 Worker/D1 或业务数据。

运行文件、测试、依赖与工作流在本记录生成前已冻结；其精确身份见本轮 freeze-manifest.json。之后只整理本实施记录和说明。没有开展语言改造，slider.js（含字典、normalizeLocale、默认/回退行为）及全部 po/mo 文件与 HEAD 字节一致。

## 最终变更

### 默认核心 URL 与显式演示

`nova_slider_captcha.urls` 只提供命名 api-root 的 JSON 根路径及 init / challenge / verify。根路径不签发挑战、不建 session，不再承载 HTML 演示页；核心挂载下的 submit / demo 都返回 404。

演示页和固定 purpose=demo 的消费移到显式 `nova_slider_captcha.demo_urls`；开发示例主动挂在 `/captcha-demo/`。可选挂载保留 submit 与 demo 消费别名。演示 form.action 使用当前演示 namespace 反解，demo.js 从该 action 提交，不再推断核心 API 的 submit。

Widget 默认使用 `nova_slider_captcha:api-root`，增加 `api_root=` 完整 URL 名参数以选择多实例或嵌套 namespace；保留挂载和 script prefix。自定义演示可为 views.demo 传可信 api_root URL kwarg。init/challenge/verify 协议不变；独立组件仍接受原 endpoint，示例 DOM 流程已一并迁移。README/RELEASING 写明旧 demo 名称和消费路径迁移，没有只删路由。

### 依赖、字段和包边界

Pillow 从精确 12.2.0 改为 `>=12.2,<13`。根据 [官方发布列表](https://pillow.readthedocs.io/en/stable/releasenotes/index.html) 和 PyPI JSON 核实本轮实际可用的 12.x 最新版为 12.3.0；12.2.0 / 12.3.0 都在矩阵实际测试，未开放 10/11/13。Django 6.0.9 的实际分发也通过 PyPI JSON 核实，证据见 dependency-availability.json。

CI 精确六格覆盖声明的 Python 3.10–3.14、Django 5.2/6.0/6.1 和 Pillow 两端。每格 source 与同一 wheel 检查；保留只构建一次、同一 artifact 发布及 OIDC job 最小权限。check_release 现比较运行文件集合（不接受残余旧文件）和依赖元数据。删除只有 __init__.py 的 templatetags 壳，增加 demo_urls，因此运行文件总数仍为29。

SliderCaptchaField 对 required=False / disabled=True 在构造时抛明确 ValueError；字段实例之后被改写时仍运行时拒绝。errors / full_clean 的缓存上下文复查、永久失效、多凭证原子消费保持，增加解释 `_captcha_check_errors` 防 add_error→errors 重入，以及 `_captcha_cleaning` 防半成品 cleaned_data 被误判的注释。

### 出图热点

用 Pillow C 层渐变、色彩映射、仿射波纹和通道混合代替 51,200 次 Python 像素/tuple 循环。仅一条短正弦 lookup 在 Python 生成；全尺寸噪声来自该图独立 PRNG 的 randbytes。每次仍用 secrets 生成两个秘密坐标和新鲜128位装饰种子，无有限图像缓存，无 NumPy 依赖。几何、扁平 PNG、透明轮廓和原形状绘制保持。

新增图像回归覆盖不同种子的像素新鲜度、无元数据、颜色变化、透明 mask 的边界、源图内部像素、缺口变暗和未裁切区域。已人工查看本地合成对比图，缺口/拼图可辨识；这不是用户可用性或抗自动解题验收。

同解释器/同进程预热后做25组交错配对，每组两算法使用相同合成种子，轮换先后顺序。没有访问任何 URL；机器外部负载不能完全控制，因此不推导生产吞吐。

| 中位数 | HEAD 基线 | 当前 |
|---|---:|---:|
| make_puzzle 总耗时 | 66.22 ms | 6.80 ms |
| 两张 PNG 保存合计 | 5.94 ms | 5.53 ms |
| 背景 PNG 大小 | 92,608 B | 86,339 B |
| 拼图 PNG 大小 | 4,663 B | 4,671 B |

总耗时中位降低约89.7%；当前主要时间转为 PNG 保存。图像艺术细节与 PRNG 消费顺序改变，大小差异不是画质或安全评分。未宣称增强抗自动化、未采集轨迹、未添加形状库。原始样本见 images-benchmark.json；[左基线/右当前的合成预览](../verification/2026-10-26-followup-implementation/images-comparison.png) 不包含种子或机器答案。

### 宿主安全替代入口

增加 `SliderCaptchaWidget(alternative_url=..., alternative_label=...)`，可覆盖全局 NOVA_SLIDER_ALTERNATIVE_URL / LABEL（便于 Admin）。未配置不显示链接。URL/标签只来自宿主设置或代码，不读取请求/HTML attrs。

URL 原始值和解码值均须为单个 `/` 开头的本地绝对路径；拒绝 scheme、外站/协议相对地址、编码双斜杠/反斜杠、空白/控制字符、超长值。特别覆盖 `%2Fhelp/` 这种解码后本地但浏览器原串会按相对地址解析的情况。标签限1–200可打印字符；模板使用 force_escape，即使 SafeString 也转义。非法全局设置检查为 E007，渲染时也拒绝。

链接在 nova-slider 和 noscript 之外，刷新重绘不会删除，JS 开/关都可见；有独立明暗兜底与 Django/Nova 显式主题优先级，窄容器允许换行。链接只导航，不签发/消费凭证、不免验证，不内置邮件、短信或音频；目的流程由宿主实现其身份、授权、CSRF、限流和等价保护。README 包含普通表单与 Admin 示例。

### 部署指引

新增 [DEPLOYMENT.md](DEPLOYMENT.md)：Nginx→Uvicorn 由受限代理中间件设置 scope.client，再由 Django 映射 REMOTE_ADDR；Nginx→uWSGI 使用真实 CGI 参数 REMOTE_ADDR，由 uWSGI 放入 WSGI environ。明确仅增加 X-Real-IP 不自动生效、代理必须覆盖客户端头、限制连接来源与后端可达性，多级 CDN/LB 不能盲目套用。

在独立环境安装 Uvicorn 0.54.0，直接调用 ProxyHeadersMiddleware 与 Django ASGIRequest，证明可信代理映射地址/scheme、不可信 peer 不能伪造、X-Real-IP 不覆盖；没有开 socket 或服务。Nginx/uWSGI 实际部署未验证。

补 check --deploy --fail-level WARNING 指引，以及 systemd/现有调度成功时间、exit code、耗时、删除数量与状态表增长监控。对本地开发 settings 实际运行 deploy check，预期得到 W002/W004/W008/W012/W016/W018 六项警告并退出1；保留日志，没有把示例设为生产或新增默认线程/可信 header 开关。

## 实际验证结果

六个自建 uv venv 均在 `/tmp/nova-slider-followup-impl-...-20261026`；基础解释器只读复用，包括主控提供的任务专用 Python 3.14.7，没有更改共享包。每个 triple/profile 使用独立 NOVA_TEST_DB，未接触 demo.sqlite3。

| Python | Django | Pillow | Source | 同一 wheel |
|---|---|---|---:|---:|
| 3.10.20 | 5.2.17 | 12.2.0 | 122通过 | 122通过 |
| 3.11.12 | 5.2.17 | 12.3.0 | 122通过 | 122通过 |
| 3.12.14 | 5.2.17 | 12.3.0 | 122通过 | 122通过 |
| 3.12.14 | 6.1.2 | 12.2.0 | 122通过 | 122通过 |
| 3.13.12 | 6.1.2 | 12.3.0 | 122通过 | 122通过 |
| 3.14.7 | 6.0.9 | 12.3.0 | 122通过 | 122通过 |

每格 check、makemigrations --check --dry-run、uv pip check 都通过；零跳过。相对基线110新增12项 Django测试，覆盖核心路由隔离/命名空间、替代链接与字段诊断及图像不变量；原有 Admin/通用表单、CSRF、绑定、一次消费、策略/限流并发、升级、语言等回归一起执行。

| 其他检查 | 结果 |
|---|---|
| Node24.21.0 / jsdom26.1.0 组件 | 41项通过 |
| 真实 Django test client + jsdom DOM | 12检查通过，显式演示与 Admin 可用 |
| 本地 Worker | 25项通过 |
| sdist解包 source（3.14.7/6.0.9/12.3.0） | 122项通过 |
| build / twine check --strict | wheel/sdist通过 |
| check_release --dist --tag v0.3.0 | 29运行文件集合/内容、依赖和链接检查通过 |
| 两 workflow actionlint1.7.12 | 零诊断 |
| CI矩阵/构建物/OIDC权限审计 | 通过，语言文件字节一致 |
| Uvicorn ASGI合成契约探针 | 可信/不可信来源和scheme映射通过 |
| git diff --check | 通过 |

已测包位于 `/tmp/nova-slider-followup-impl-dist-uv-20261026/`，未上传。首轮常规 pip 隔离构建成功但较慢，另以 build --installer uv 在新目录构建并以这同一份 wheel 做六格安装测试。初始 SafeString 回归暴露普通 autoescape 会尊重宿主 mark_safe，已改为 force_escape 后全部通过；初始日志保留。主控提出的原始URL斜杠及外部链接暗色缺口也已修复并回归。

## 命令与证据

[本轮证据目录](../verification/2026-10-26-followup-implementation/)：matrix-source.json / matrix-wheel.json 及对应六格日志、sdist-tests.log、component.log、dom.json/log、worker.log、build-uv.log、twine-final.log、payload-final.log、actionlint.log、workflow-contract.json、dependency-availability.json、proxy-probe.json、deploy-check-demo.log、images-benchmark.json。artifacts.json 记录已测 wheel/sdist 的大小与哈希；freeze-manifest.json 记录冻结源文件、测试、工作流和依赖身份。

```sh
# 任务专用构建环境，matrix脚本从当前CI精确配对读取并使用已准备的独立venv。
python verification/2026-10-26-followup-implementation/run_matrix.py --modes source --label new-source
python -m build --installer uv --outdir /absolute/new-dist
python -m twine check --strict /absolute/new-dist/*
python scripts/check_release.py --tag v0.3.0 --dist /absolute/new-dist
python verification/2026-10-26-followup-implementation/run_matrix.py \
  --modes wheel --label new-wheel --wheel /absolute/new-dist/nova_slider_captcha-0.3.0-py3-none-any.whl

PYTHONPATH=src:. python scripts/benchmark_images.py --baseline-ref f3edfee \
  --iterations 25 --output /absolute/new-benchmark.json --preview /absolute/new-preview.png
npm test
NOVA_PYTHON=/path/to/test/python NOVA_DOM_REPORT=/absolute/new-dom.json npm run test:dom
npm run test:worker
/path/to/actionlint
git diff --check
```

构建工具 Python3.12+，有 build/twine/packaging；本地额外 pyyaml 仅供矩阵脚本，不是运行依赖。输出标签/目录使用新名称，脚本以 x 模式保护已有矩阵和基准证据。可复用脚本中的临时解释器路径只用于本次实施，不是生产部署配置。

## 边界与未完成外部步骤

远端 GitHub Actions 本轮未执行；PyPI发布、publisher/environment设置、账号、tag与Release均未操作。没有运行生产配置的 check --deploy、真实Nginx/uWSGI部署、生产调度或数据库监控。

没有在本实施会话进行真实浏览器布局、真机/辅助技术、PostgreSQL/MySQL、生产负载或线上Worker/D1验证。图像预览与jsdom不代替这些证据；Uvicorn探针不等于代理上线验收。主控负责的浏览器与独立包/源码验证以其 followup-independent 报告为准，不并入本实施自测数量。只覆盖表中代表性版本组合，不宣称所有交叉版本或Pillow13已验证。
