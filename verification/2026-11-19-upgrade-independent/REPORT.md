# 用途策略、审计事件和非视觉示例独立验收

2026-11-19，主控会话在独立临时目录、虚拟环境和 SQLite 库中复测了 GPT-6.2 SOL 实施会话的工作树差异。基线为 `f60e94cced3562835d9ff3f08f08786f5807120d`。版本为 0.3.0。

受验文件包括 Django app 的配置、系统检查、事件与服务，源码宿主示例的配置、视图、模板、批准记录与迁移、管理命令，以及相关测试、README、CHANGELOG 和 MANIFEST。最终受验快照的 SHA-256 为 `8cf7411967395ddce1ae898d08f7a7d7d7bb09a4b95bae4b239f80dbfd0df8c5`。计算时取 Git 已跟踪及未忽略的新增文件，排除本报告目录。按仓库相对路径的字节排序，依次拼接路径、一个零字节、文件内容的 32 字节 SHA-256 摘要，再对整体取 SHA-256。

## 独立核对的行为

| 场景 | 观察结果 |
| --- | --- |
| 用途覆盖与回退 | 分别向两个用途发题，响应和数据库快照与全局继承、局部覆盖一致。合法调参后旧题按原容差验证。删除用途后，其在途题和未消费凭证被拒绝。另一用途的非法覆盖也会触发拒绝。切换用途仍共用发题额度。 |
| 事务与审计 | 在三个独立库上模拟默认库、验证码写库和读取副本。只有实际写库提交后才收到对应的 INFO 成功事件。内层保存点或消费事务回滚后没有对应成功日志，回滚的凭证随后可以正常消费一次。事件里未出现受验凭证、会话绑定值或挑战编号。 |
| 宿主登录权限 | 初审发现示例登录允许范围过宽。修改后，已登记普通账号能登录，未登记账号及加入演示组的 staff、superuser 均不能通过该入口建立认证会话。限流先于密码认证，命中后返回 429 和重试时间。 |
| 无脚本的完整操作 | 在关闭 JavaScript 的 Chrome 中用键盘登录、从视觉表单进入替代页、输入错误代码，再用本地操作员签发的代码重试。数据库中的显示名称确实更新，批准记录已消费。重复提交相同代码和另一个名称后，页面提示失败，数据库保留第一次保存的值。 |

第一次全量回归识别出演示用途白名单影响核心默认值测试。实施修正了测试设置隔离，下面的全量结果来自修正后的快照。

## 源码和安装包

下列六组均在本机以 Django 原生主题分别运行源码与安装 wheel 的完整后端测试。每次均检查依赖、模块实际导入位置、Django 系统检查和迁移漂移。

| Python | Django | Pillow | 源码 | 同一 wheel |
| --- | --- | --- | ---: | ---: |
| 3.10.20 | 5.2.17 | 12.2.0 | 172/172 | 172/172 |
| 3.11.12 | 5.2.17 | 12.3.0 | 172/172 | 172/172 |
| 3.12.16 | 5.2.17 | 12.3.0 | 172/172 | 172/172 |
| 3.12.16 | 6.1.2 | 12.2.0 | 172/172 | 172/172 |
| 3.13.12 | 6.1.2 | 12.3.0 | 172/172 | 172/172 |
| 3.14.7 | 6.0.9 | 12.3.0 | 172/172 | 172/172 |

本次矩阵所用 wheel 的 SHA-256 为 `e04456f69fd148f417eecd38b3f5aaa59441fb4c1af9a0be00f4ee0b07451b18`，同次构建的 sdist 为 `04ff4e060cbdf60dac54f4e62544e36023c8eb8487c82d6807402912f36bf22a`。构建物通过 Twine 严格检查，wheel 和 sdist 的 29 个运行时文件与源码相符。另核对了 sdist 中的宿主模板、管理命令和示例迁移，wheel 仅包含可安装 app。

## 复测命令与环境

独立覆盖率环境为 Python 3.12.11、Django 5.2.17、Pillow 12.3.0、coverage.py 7.17.0。源码包覆盖 737/747 条语句（98.66%）、195/198 个分支（98.48%），表单模块两项均为 100%。Node 24.21.0 的 49 项组件测试和 20 项 Django-client DOM 检查通过。键盘流程使用 Chrome 158.0.8127.36，运行平台为 macOS arm64。

以下为主要命令。路径变量指向本次临时工作目录中的解释器、数据库、构建物和结果文件。源码检查使用 `DJANGO_SETTINGS_MODULE=tests.settings`、`PYTHONPATH=src:.` 和独立的 `NOVA_TEST_DB`。浏览器演示使用 `demo.settings` 及单独的 `NOVA_DEMO_DB`。

```sh
uv pip check --python "$PYTHON"
python -m django check
python -m django makemigrations nova_slider_captcha demo --check --dry-run
ruff check .
python scripts/test_policy_upgrade.py
python scripts/test_rate_upgrade.py
python -m coverage run -m django test tests --noinput -v 1
python -m coverage combine --keep
python -m coverage json -o "$COVERAGE_JSON"
python scripts/check_coverage.py "$COVERAGE_JSON"
python scripts/test_coverage_gate.py "$COVERAGE_JSON"
npm ci --ignore-scripts
npm test
NOVA_PYTHON="$PYTHON" NOVA_DOM_REPORT="$DOM_JSON" npm run test:dom
python -m build --installer uv --outdir "$DIST"
python -m twine check --strict "$DIST"/*
python scripts/check_release.py --dist "$DIST"
python scripts/test_matrix.py --work "$MATRIX" --runtimes "$RUNTIMES" --wheel "$WHEEL" --workers 3
```

本次可访问性验证覆盖无 JavaScript、键盘和实际保存，人工屏幕阅读器体验及真实人工交付渠道仍待宿主验证。数据库覆盖 SQLite，未实测 PostgreSQL、MySQL 或生产并发负载。此次未运行远端 CI 或执行上传、部署。
