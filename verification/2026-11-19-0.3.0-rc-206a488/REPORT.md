# 0.3.0 发布候选构建与兼容矩阵验收

2026-11-19，发布候选 `206a48806d1793d29e6d66d95a98d1b4b34375f1` 通过本地验收。六组依赖配对分别运行源码和同一个已安装 wheel，均覆盖原生 Django Admin 与 Nova Admin。**24 组全部通过，每组 201 项完整测试，合计 4,824 次测试执行，其中 2,412 次使用安装后的 wheel。**

## 构建物

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `nova_slider_captcha-0.3.0-py3-none-any.whl` | 72,352 | `7827c4669efc7fd54137b0f9b46a9c86bcf18b3420434b612edb84cfdd1e00a1` |
| `nova_slider_captcha-0.3.0.tar.gz` | 289,652 | `00bf4241205864dadde07a330bf1d660a8aa97a2a270e674a73d39060ca6f7d1` |

两个文件保存在本地仓库的 `dist/0.3.0-206a488/`。可在仓库根目录执行 `shasum -a 256 dist/0.3.0-206a488/*` 复核。Git 提交仅包含本报告。

使用 `git archive` 导出候选提交，逐一核对了 748 个受版本控制文件的 Git 对象摘要。在 macOS 27.2.1 arm64 上，以独立的 CPython 3.12.11 环境执行一次 `python -m build`，先生成 sdist，再从该 sdist 生成 wheel。构建工具为 build 1.6.1、uv 0.12.17、setuptools 84.2.1、wheel 0.48.0，分发检查使用 twine 7.0.0。

- 项目版本与预期 tag 字符串 `v0.3.0` 一致。两个产物均通过 `twine check --strict` 和仓库发布检查，两包内的 34 个运行文件均与候选源码逐字节相符。
- wheel 元数据中的 Markdown 长描述与候选 README 正文相符。sdist 收录的 README、CHANGELOG 和 RELEASING 与该提交逐字节相同。
- 矩阵开始前将产物设为只读。六个虚拟环境均从表中同一个本地 wheel 强制安装。测试结束后，按每个环境的 pip 安装来源记录定位文件，重新计算 SHA-256，并逐字节核对已安装的运行文件及包元数据。矩阵输出记录的 wheel 摘要、六个环境复核的摘要和表中数值一致。wheel 与 sdist 在矩阵执行前后的哈希均一致。

## 兼容矩阵

每个结果格为该环境实际通过的测试数。每格均另外通过 Django 系统检查和迁移漂移检查；六个虚拟环境的 `pip check` 均通过。版本配对已与候选提交的 [Tests 工作流](../../.github/workflows/tests.yml) 逐项核对。

| CPython | Django | Pillow | SQLite | 源码 · 原生 | 源码 · Nova | wheel · 原生 | wheel · Nova |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| 3.10.20 | 5.2.17 | 12.2.0 | 3.54.0 | 201 | 201 | 201 | 201 |
| 3.11.12 | 5.2.17 | 12.3.0 | 3.54.0 | 201 | 201 | 201 | 201 |
| 3.12.16 | 5.2.17 | 12.3.0 | 3.54.0 | 201 | 201 | 201 | 201 |
| 3.12.16 | 6.1.2 | 12.2.0 | 3.54.0 | 201 | 201 | 201 | 201 |
| 3.13.12 | 6.1.2 | 12.3.0 | 3.50.4 | 201 | 201 | 201 | 201 |
| 3.14.7 | 6.0.9 | 12.3.0 | 3.53.1 | 201 | 201 | 201 | 201 |

每格使用独立的 SQLite 数据库文件。源码模式从候选 `src/` 导入，wheel 模式从该虚拟环境的 `site-packages` 导入。Nova 主题固定为 `django-nova-admin@376bce7c8ceeeeb5f0a62f07f969227eb66e4adf`。矩阵分别断言模块来源；复核时还在清除 `PYTHONPATH` 的升级子进程条件下，检查了四种模式的包来源和主题加载情况。

## 复核命令与范围

以下命令在导出的候选源码根目录执行。`$DIST` 是本次新建的产物目录，`$MATRIX` 是本次矩阵目录，`$RUNTIMES` 包含表中解释器，`$NOVA_SOURCE` 指向固定主题提交的 `django-theme/src`。本次预先为六个矩阵虚拟环境配置了仅在相应模式生效的导入路径，使清除 `PYTHONPATH` 的子进程也能定位候选源码或 Nova 主题。

```sh
python scripts/check_release.py --tag v0.3.0
python -m build --installer uv --outdir "$DIST"
python -m twine check --strict "$DIST"/*
python scripts/check_release.py --dist "$DIST"
python scripts/test_matrix.py --runtimes "$RUNTIMES" --work "$MATRIX" \
  --wheel "$DIST/nova_slider_captcha-0.3.0-py3-none-any.whl" \
  --nova-source "$NOVA_SOURCE" --workers 3
```

本报告的结论限于 `206a488` 的本地构建及上述 SQLite 完整矩阵。PostgreSQL、MySQL、真实 Chrome 和 HTTPS Webhook 的专项证据属于[上一轮综合验收](../2026-11-19-pre-release-integrated/REPORT.md)，本次未重跑这些专项。远端 CI、推送、打 tag 和发布均未执行。
