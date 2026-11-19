# Admin 旧会话隔离最终复跑

2026-11-19，主控在独立临时环境中复跑了最终工作树。开始时六个受验文件位于基线 `534ee59796f43ea2078180072ab545f14208f52e` 的工作树差异中。复跑后比较了该差异与本地修复提交 `ab77f9b8381f4c776db7a058ec83211ddf5371a3` 的六文件差异，两者逐字节一致。受验的 `git diff --binary --no-ext-diff` 输出 SHA-256 为 `6521b9890666fcab5e540f0eb568176900ce826ac14bf5d42a57cbe40f780c1c`。此前覆盖真实旧版登录入口的结果见 [演示账号升权后的 Admin 登录补充验收](../2026-11-19-admin-promotion-independent/REPORT.md)。

## Admin 登录回归

定向测试在 Python 3.12.11、Django 5.2.17、Pillow 12.3.0 和隔离 SQLite 库中通过 3/3。

- 旧设置仅用于生成具有 `django.contrib.auth.backends.ModelBackend` 标识的数据库会话。恢复最终设置后再提升账号权限，Admin 将旧会话转到登录页。只提交正确密码时依然无法进入后台。
- 新版普通演示会话在账号升权后也被转到 Admin 登录页，并须重新通过同样的滑块和密码校验。
- 两类会话重新认证成功后，均以 `demo.profile.DemoPasswordBackend` 登录。测试确认新会话可访问 Admin，旧会话键对应的行已删除，`login` 凭证已消费。正常的新建 Admin 会话也通过既有登录回归。

升级本地演示后，使用旧认证标识的普通用户和管理员都需要重新登录一次。

## 完整测试

六组 CI 配对均运行完整的源码测试和本次同一构建 wheel 的安装测试。矩阵同时通过依赖检查、导入位置检查、Django 系统检查和核心 app 迁移漂移检查。

| Python | Django | Pillow | 源码 | 安装 wheel |
| --- | --- | --- | ---: | ---: |
| 3.10.20 | 5.2.17 | 12.2.0 | 174/174 | 174/174 |
| 3.11.12 | 5.2.17 | 12.3.0 | 174/174 | 174/174 |
| 3.12.16 | 5.2.17 | 12.3.0 | 174/174 | 174/174 |
| 3.12.16 | 6.1.2 | 12.2.0 | 174/174 | 174/174 |
| 3.13.12 | 6.1.2 | 12.3.0 | 174/174 | 174/174 |
| 3.14.7 | 6.0.9 | 12.3.0 | 174/174 | 174/174 |

定向环境同时通过 `demo` 与核心 app 的迁移漂移检查、Ruff 0.17.2、两项 SQLite 升级脚本和 `git diff --check`。coverage.py 7.17.0 下完整套件通过 174/174，核心包语句覆盖率 98.66%、分支覆盖率 98.48%，表单模块两项均为 100%，通过覆盖率门槛及门槛脚本回归。Node 24.21.0 下通过组件测试 49/49、Django-client DOM 联调 20/20 和本地 Worker 示例测试 29/29。

Python 3.12.11 环境构建的 wheel 和 sdist 均通过 Twine 严格检查。发布检查核对了 29 个运行时文件。wheel 的 SHA-256 为 `1051db57aa46ae92a5278beef6835cbfab1638ded17519c0b4c9a1b1eff34ac4`，sdist 为 `af13bbd7ae6e6332e1e6101f9a5c9a4bf48a011d044f986162cd97ee38854f9a`。

## 复测命令

源码和覆盖率检查使用 `DJANGO_SETTINGS_MODULE=tests.settings`、`PYTHONPATH=src:.` 和各自独立的 `NOVA_TEST_DB`。矩阵脚本为每组源码和 wheel 分配独立数据库，并为安装包模式设置仓库根目录作为导入路径。

```sh
uv pip check --python "$PYTHON"
"$PYTHON" -m django check
"$PYTHON" -m django makemigrations nova_slider_captcha demo --check --dry-run
"$PYTHON" -m django test \
  tests.test_demo_profile.ProfileDemoTests.test_legacy_model_backend_session_requires_fresh_admin_login \
  tests.test_demo_profile.ProfileDemoTests.test_promotion_requires_a_fresh_admin_login \
  tests.test_captcha.CaptchaTests.test_admin_login_success_and_proof_consumed --noinput -v 2
"$PYTHON" -m coverage run -m django test tests --noinput -v 1
"$PYTHON" -m coverage combine --keep
"$PYTHON" -m coverage json -o "$COVERAGE_JSON"
"$PYTHON" scripts/check_coverage.py "$COVERAGE_JSON"
"$PYTHON" scripts/test_coverage_gate.py "$COVERAGE_JSON"
"$PYTHON" scripts/test_policy_upgrade.py
"$PYTHON" scripts/test_rate_upgrade.py
ruff check .
npm test
NOVA_PYTHON="$PYTHON" NOVA_DOM_REPORT="$DOM_JSON" npm run test:dom
npm run test:worker
"$BUILD_PYTHON" -m build --installer uv --outdir "$DIST"
"$BUILD_PYTHON" -m twine check --strict "$DIST"/*
"$BUILD_PYTHON" scripts/check_release.py --dist "$DIST"
"$BUILD_PYTHON" scripts/test_matrix.py --runtimes "$RUNTIMES" --wheel "$WHEEL" --work "$MATRIX" --workers 4
git diff --check
```

本轮复跑覆盖本地 SQLite、Django test client 与 DOM 联调。真实浏览器、其他会话存储及远端 CI 不在本轮复跑范围内。
