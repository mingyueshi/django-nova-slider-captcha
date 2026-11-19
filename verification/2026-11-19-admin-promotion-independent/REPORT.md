# 演示账号升权后的 Admin 登录补充验收

2026-11-19，主控会话独立验收通过。已登录的普通演示账号升为 staff 或超级管理员后，再次访问 Admin 会进入登录页。只有当前会话中的有效 `login` 滑块凭证与正确密码同时通过，才可访问后台。成功登录会更换会话键，原键对应的数据库记录已删除。

## 受验范围与升级影响

基线为 `534ee59796f43ea2078180072ab545f14208f52e`。受验内容为 `README.md`、`demo/profile.py`、`demo/settings.py`、`demo/urls.py`、`docs/CHANGELOG.md` 和 `tests/test_demo_profile.py`。这六个文件相对基线的 `git diff --binary` 输出的 SHA-256 为 `6521b9890666fcab5e540f0eb568176900ce826ac14bf5d42a57cbe40f780c1c`。

初审发现，基线的演示登录与 Admin 登录使用相同的 Django 认证后端标识。实施会话据此调整了本地示例的后端配置。新版演示会话在恢复用户身份时复核账号资格，Admin 使用独立的密码认证后端。升级本地示例时，升级前已登录的普通用户和管理员均需重新登录一次。配置和表单变更位于源码宿主示例，未修改可安装的 Django app。

## 独立验证

主控在三个隔离环境中使用启用 CSRF 检查的 Django test client。先由基线代码经过正常登录表单建立旧版演示会话和 Admin 会话，再将同一临时数据库和客户端 cookie 交给运行最终快照的新进程。新版账号也经过演示登录表单。验证码使用固定出图测试夹具，签发、核验、消费、密码认证和 Admin 访问均经过实际服务端入口。

| 进入新版时的账号与会话 | 访问 Admin | 通过滑块和密码校验后 |
| --- | --- | --- |
| 新版普通演示账号提升为 staff | 转到 Admin 登录页 | 可访问后台，会话换键 |
| 新版普通演示账号同时取得 staff 和超级管理员身份 | 转到 Admin 登录页 | 可访问后台，会话换键 |
| 旧版已登录的演示账号在升级后提升为 staff | 转到 Admin 登录页 | 可访问后台，会话换键 |
| 旧版已通过 Admin 登录的管理员升级到新版 | 转到 Admin 登录页 | 可访问后台，会话换键 |

四种场景均分别核对了缺少滑块凭证、凭证用途错误和密码错误的拒绝路径。密码错误时，有效的登录凭证已被消费，改用正确密码重复提交该凭证仍被拒绝。提交新凭证和正确密码后，再次请求后台返回 200，并核实数据库中原会话记录已删除。

## 回归结果

以下均为主控对最终源码快照的独立复测。各环境使用 Python 3.12.16、Pillow 12.3.0 和 SQLite 3.54.0。

| Django | 演示与 Admin 表单定向测试 | 完整后端套件 | 独立会话场景 |
| --- | ---: | ---: | ---: |
| 5.2.17 | 14/14 | 174/174 | 4/4 |
| 6.0.9 | 14/14 | 174/174 | 4/4 |
| 6.1.2 | 14/14 | 174/174 | 4/4 |

三个环境的依赖检查、Django 系统检查及两个 app 的迁移漂移检查均通过。改动的 Python 文件通过 Ruff 0.17.2 检查。

```sh
uv pip check --python "$PYTHON"
export DJANGO_SETTINGS_MODULE=tests.settings PYTHONPATH=src:.
export NOVA_TEST_DB="$REVIEW_DIR/suite.sqlite3"
"$PYTHON" -m django check
"$PYTHON" -m django makemigrations demo nova_slider_captcha --check --dry-run
"$PYTHON" -m django test tests.test_demo_profile tests.test_boundaries.AdminFieldBoundaryTests --noinput -v 1
"$PYTHON" -m django test tests --noinput -v 1
ruff check demo/profile.py demo/settings.py demo/urls.py tests/test_demo_profile.py
```

各 Django 版本分别使用独立的目录和数据库。跨版本会话场景另用 `demo.settings` 和专用 `NOVA_DEMO_DB`。本次结果覆盖本地数据库会话和服务端登录流程；浏览器手势、其他会话存储和远端 CI 不在本次复测范围内。
