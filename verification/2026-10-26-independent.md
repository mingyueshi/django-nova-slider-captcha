# 2026-10-26 主控独立验收

结论：本轮本地改进通过独立验收，无遗留阻断项。主控复核诊断、分派并验收；具体实现由新建的 GPT 6.1 sol 会话完成（`01a17557-fece-74a0-90fb-3e53d27d2748`）。本记录来自主控实际执行，独立于[实施自测](2026-10-26-implementation.md)。

基线为 `33b92ece5464ccc0b79ae99cb5d37ca6d62628f9`。所有改进保留为本地未提交改动，没有推送、部署或运行远端 CI。

## 实际结果

| 独立检查 | 结果 |
|---|---|
| Python 3.12.14 / Django 5.2.17 / Pillow 12.2.0，源码 | 71 项通过 |
| Python 3.10.20 / Django 5.2.17 / Pillow 12.2.0，源码 | 71 项通过 |
| Python 3.12.14，同依赖，隔离环境安装 wheel | 71 项通过；确认导入自 site-packages |
| Node 24.21.0，组件 | 35 项通过 |
| Node 24.21.0，Worker SQLite | 25 项通过 |
| jsdom + 真实 Django test client | 12 项流程通过 |
| Django check / 迁移漂移 / uv pip check / git diff --check | 通过 |
| sdist 与 wheel 构建 | 成功；wheel 27 个运行文件与最终源码逐字节一致 |
| 原版/新版 GCRA 独立对照 | 500 步允许结果、Retry-After 和每一步完整数据库状态一致 |

本机平台为 macOS arm64；所有数据库检查使用临时文件或内存 SQLite，不启动项目服务。Python 3.12 环境依赖还包括 asgiref 3.13.0、sqlparse 0.6.0。Python 3.10 使用实施会话已安装的隔离环境，由主控另行运行测试，未以实施日志替代独立执行。

GCRA 对照使用固定随机种子 20261026，覆盖时钟回退、补充边界、配额变更、IP/session/action 隔离、清理和升级冷却。原子并发竞争另由完整 Django 测试验证。可从源码根目录重跑：

```sh
PYTHONPATH=src:. DJANGO_SETTINGS_MODULE=tests.settings python \
  verification/2026-10-26-independent/gcra_trace.py
```

## 性能与查询

主控在 Python 3.12.14 环境中预热后，交错运行基线与新版各 25 次：

| 指标 | 基线 | 新版 |
|---|---:|---:|
| 出图中位耗时 | 129.14 ms | 68.57 ms |
| 已有 IP/session 桶接受请求 | 4 条 SQL | 2 条 SQL |
| 首次创建 IP/session 桶 | 10 条 SQL | 10 条 SQL |

出图中位耗时降低约 **46.9%**，已有桶接受路径查询数减半。首次创建计数包含 BEGIN/COMMIT。使用独立内存 SQLite 计数；出图测试期间存在其他本地自测负载，因此仅用于本机对比，不推导生产吞吐。

```sh
PYTHONPATH=src:. python scripts/benchmark_hotpaths.py \
  --baseline-ref 33b92ec --iterations 25
```

## 真实浏览器检查

使用 Playwright 驱动 Chromium 155.0.8059.86，测试页面加载真实生成的 PNG 和实际组件源码，HTTP 初始化/出题响应由本地 fixture 模拟，没有连接线上服务。

- 正常 decode 和主动移除 decode 两条路径均加载成功，实际图像尺寸为 320×160、44×44。
- 两条路径的损坏图片均进入 error，隐藏凭证为空。
- 降级路径刷新后，旧图片迟到的 error 不改变新题 ready 状态。
- 390 像素视口的文档宽度也是 390，无横向溢出，截图已人工检查。

这是真实 Chromium 的图片加载检查，不是旧 Safari/WebView 实机验证，也不是实际 Django HTTP 页面完整浏览器验收。Django 真实请求语义另由 test-client DOM 流程覆盖。

## 记录与边界

[机器摘要](2026-10-26-independent/summary.json)、[性能样本](2026-10-26-independent/hotpaths.json)、[运行文件哈希](2026-10-26-independent/wheel-runtime.json)、[浏览器结果](2026-10-26-independent/browser.json) 和各测试日志保存在 [独立验收目录](2026-10-26-independent/)。

已测试 wheel 的 SHA-256：`8434f733526e1fba9d0deb794260ccd234bba01a745b71f7cf440a7909c5aff2`。构建产物仅保存在本机临时目录；文档或构建元数据后续变化可能改变包哈希，运行文件身份以独立逐文件核对为准。

本轮未重跑历史完整 Django/Nova 主题矩阵；未验证 PostgreSQL/MySQL、生产压力、任意跨主机时钟偏差、线上 Worker/D1、旧浏览器实机、触控真机、屏幕阅读器或 RTL。GitHub Actions 配置已加入，远端执行仍待未来获授权的推送触发。
