# 2026-10-26 本地改进自测

本记录由实施会话生成，仅记录本轮真实执行结果，不替代主控独立验收。实施基线为 `main` / `33b92ece5464ccc0b79ae99cb5d37ca6d62628f9`。没有提交、推送、发布、部署、启动服务或操作线上数据；没有编辑主控的诊断报告或独立验收记录。旧 `VERIFICATION.md` 和旧验证日志保持原样。

## 改动

- 背景装饰使用每图独立的 128 位安全种子初始化本地 PRNG；缺口横纵坐标继续使用 `secrets`，session/凭证保持安全随机，图像尺寸和遮罩不变，无 numpy 或缓存体系。
- GCRA 已有桶先执行 ORM 条件 UPDATE；未更新时安全创建已扣一次的桶，竞争创建时再次条件 UPDATE。保留 IP 先扣、拒绝不延债、冷却、失败关闭和清理竞争语义，无数据库专用方言。
- 图片加载在 `src` 前安装 load/error/abort 监听；有 `decode` 时保留解码失败语义，缺少时按 load/error 和缓存完成状态处理。刷新更换图片节点，取消和完成均清理监听，旧图事件不能影响新题。
- 删除冗余 `isfinite`，保留严格数值类型/范围检查及巨大整数测试；集中凭证字节数和编码长度；Widget 反解既有根路由，补挂载/脚本前缀测试。
- README 补同源反代、可信 Host/HTTPS scheme、Cookie、prune 调度和密钥轮换对限流身份的影响。
- 增加 GitHub Actions；测试配置使系统检查和迁移漂移检查也使用临时数据库。DOM 测试仅在显式设置 `NOVA_DOM_REPORT` 时保存报告，避免默认覆盖历史结果。

## 环境与结果

平台：macOS 27.0.1 arm64，SQLite 3.54.0。精确版本见 [versions.json](2026-10-26-implementation/versions.json)。

| 检查 | 实际结果 |
|---|---|
| Python 3.10.20 / Django 5.2.17 / Pillow 12.2.0 | 71 项完整测试通过，零跳过 |
| Python 3.12.14 / Django 5.2.17 / Pillow 12.2.0 | 71 项完整测试通过，零跳过 |
| 两种 Python 的 Django check / makemigrations --check --dry-run | 均通过，无迁移变化 |
| Python 3.10 editable 安装 / pip check | 通过 |
| Python 3.12 依赖检查 | uv pip check 通过，4 个包兼容 |
| Node 24.21.0 / npm 11.19.0 / jsdom 26.1.0 | npm ci 成功；最终组件测试 35 项通过 |
| 真实 Django test client + jsdom DOM | 12 项流程检查通过 |
| Worker，Node 内置 SQLite | 25 项通过 |
| Workflow YAML / git diff --check | 本地解析及差异检查通过 |

Python 环境：

- 新建实施环境：`/tmp/nova-slider-implementation-20261026-py310/bin/python`。
- 主控提供的只读环境：`/tmp/nova-slider-review-20261026/bin/python`。该环境由 uv 创建，无 pip；初次 `python -m pip check` 的失败如实保留在日志中，随后改用只读 `uv pip check --python ...` 成功，未安装或修改其任何包。

使用本实施会话专属 `NOVA_TEST_DB` 临时路径；完整测试的并发检查使用文件 SQLite。DOM bridge 和迁移升级子进程还会自行创建独立临时目录。未迁移项目 `demo.sqlite3`。

主要重跑命令（从仓库根目录执行；两种 Python 分别设置 `PY` 和不同的临时数据库名）：

```sh
export PY=/tmp/nova-slider-implementation-20261026-py310/bin/python
export PYTHONPATH=src:.
export DJANGO_SETTINGS_MODULE=tests.settings
export NOVA_TEST_DB=/tmp/nova-slider-implementation-py310-20261026.sqlite3
"$PY" -m django check
"$PY" -m django makemigrations nova_slider_captcha --check --dry-run
"$PY" -m django test tests --noinput -v 1
"$PY" -m pip check

uv pip check --python /tmp/nova-slider-review-20261026/bin/python
npm ci
npm test
NOVA_PYTHON=/tmp/nova-slider-review-20261026/bin/python \
  NOVA_DOM_REPORT=/tmp/nova-slider-implementation-dom-new-results.json npm run test:dom
npm run test:worker
```

原始命令与输出见 [本轮日志目录](2026-10-26-implementation/) 的 `py310.log`、`py312.log`、`py312-uv-pip-check.log`、`install-editable-py310.log`、`component-final.log`、`dom.log`、`worker.log`。`component.log` 是新增最后两项测试前的 33 项通过结果，最终以 `component-final.log` 的 35 项为准。DOM 日志中的 `Forbidden: /captcha/submit` 是预期的重复消费拒绝检查。

## 性能与查询数

用同一 Python 3.12 环境读取基线源码，预热后交错运行基线/当前各 15 次；[原始样本与 SQL 统计](2026-10-26-implementation/hotpaths.json) 均保留。

| 检查 | 33b92ec 基线 | 当前 |
|---|---:|---:|
| make_puzzle 中位数 | 131.01 ms | 70.94 ms |
| make_puzzle 最小值 | 125.73 ms | 67.41 ms |
| make_puzzle 最大值 | 137.73 ms | 94.19 ms |
| 首次创建 IP + session scope | 10 条 SQL | 10 条 SQL |
| 已有 IP + session scope，接受请求 | 4 条 SQL | 2 条 SQL |

本次出图中位耗时降低约 45.9%；已有桶的接受路径移除两次 SELECT。首次创建仍包含两组 BEGIN/COMMIT，无查询数改善。测量期间还运行了其他本地自测，绝对耗时会随机器负载变化；该微基准不是生产吞吐、压力或跨数据库测试。

可重跑命令（数据库仅为隔离内存 SQLite，不迁移示例数据库）：

```sh
PYTHONPATH=src:. /tmp/nova-slider-review-20261026/bin/python \
  scripts/benchmark_hotpaths.py --baseline-ref 33b92ec --iterations 15
```

## CI 与边界

Workflow 采用 Python 3.10 / 3.12 + Django 5.2.17 两个作业配置，以及 Node 24 组件/DOM/Worker 作业；作业数据库和 DOM 输出位于各自 `runner.temp`。已对照官方标签文档核实 [checkout v5](https://github.com/actions/checkout/blob/v5/README.md)、[setup-python v6](https://github.com/actions/setup-python/blob/v6/README.md)、[setup-node v6](https://github.com/actions/setup-node/blob/v6/README.md) 的用法，并在本地解析 YAML。**远端 GitHub Actions 尚未运行，不能宣称 CI 通过。**

本轮实施自测覆盖原生 Django 配置；没有重跑历史全部 Python/Django/Nova/wheel 矩阵。没有把组件中模拟的图片事件/解码和 jsdom 流程当成真实浏览器视觉证据，也不据此声称支持所有旧浏览器。PostgreSQL/MySQL、生产压力、多主机代理、线上 Worker/D1、真机触控、屏幕阅读器和 RTL 均未在本实施会话验证。主控另行执行的独立验收由主控记录。
