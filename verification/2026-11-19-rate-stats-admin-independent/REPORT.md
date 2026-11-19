# 限流桶只读 Admin 视图独立验收

2026-11-19 验收通过。使用 `SliderCaptchaAdminSite` 的宿主可以从本站首页进入限流统计。页面从两张桶表各执行一次只读聚合。固定采样时刻后，实际 HTML 中显示的时间、六组 GCRA 计数与遗留桶计数均与管理命令 `--json` 一致。

原 GPT-6.2 SOL 会话负责实现和自测，主控在独立源码副本、数据库和安装包环境中复测。基线为 `3b8aac827faa1004bcc8b4198ac3db25b4def18a`。相对基线，Admin、共享统计函数、管理命令、模板、翻译、测试、README 与 CHANGELOG 共十个文件的 `git diff --binary` SHA-256 为 `9dad173bb4f7062dd8d7c1d3fe2283856fd34035283cd319a656eb1e1208d9d5`，不含本报告。

## 权限和入口

| 测试身份或操作 | 首页和直接访问的结果 |
| --- | --- |
| 匿名用户、非 staff 用户、未激活账号 | 标准站点转到自己的 Admin 登录页。普通账号即使已有两项查看权限也无法进入。 |
| 活动 staff，无桶权限、仅有其中一项查看权限、或仅有两项 change 权限 | 首页没有统计入口，直接 GET 返回 403。 |
| 个人或所属组获授两项查看权限的活动 staff，以及活动的 staff 超级管理员 | 首页有入口，统计页返回 200。两项权限分别为 `view_ratelimitstate` 和 `view_ratebucket`，所属应用均为 `nova_slider_captcha`。 |
| 同一已登录账号获授、随后撤销第二项权限 | 下一次请求分别返回 200 和 403。撤销后的首页入口也随之消失。 |
| 宿主放宽或收紧本站 `has_permission()` | 即使站点允许非 staff 登录，统计页也拒绝其访问。宿主设置更严格的站点门槛时，已具备两项权限的 staff 仍须满足该门槛。 |
| 演示账号在旧演示会话中升为 staff 且具备两项权限 | 访问统计页会转到 Admin 登录页。旧演示会话不会获得统计权限。 |

在两个不同挂载点和命名空间核对入口、面包屑和本站登录跳转。普通 Django `AdminSite` 没有新增统计路由，两个桶模型均未注册为可浏览或编辑的 Admin 模型。所有被拒绝的请求以及仅加载首页的请求，对两张桶表的查询数均为零。

## 只读行为与数字核对

主控把当前桶和遗留桶分别路由到两个独立写库，在默认读库中放入干扰数据。在三个 SQLite 连接同时开启 `PRAGMA query_only=ON` 后访问页面和运行命令，并逐条捕获 SQL。授权 GET 和 HEAD 对每张桶表各执行一次 SELECT 聚合，分别命中对应写库。鉴权、会话和页面导航可以读取常规 Admin 数据。请求完成后，三库中两类桶的全部字段与请求前一致。

带有效 CSRF 的 POST、PUT、PATCH、DELETE 及 OPTIONS 均返回 405，允许方法只有 GET 和 HEAD。缺失 CSRF 的 POST 返回 403。上述请求均未执行桶聚合。授权 HEAD 返回空响应体，授权页面带有 `Cache-Control: no-store`，正文不含清理、编辑或删除控件。

以 UTC 时间 `2026-11-19T06:23:44.567891+00:00` 为采样点，为每组构造债务和冷却分别早一微秒、相等、晚一微秒的九种组合，使用不同数量的样本区分每组、每列。主控解析渲染后的 HTML 表格、遗留桶字段及可见采样时间，与命令 JSON 逐项比较，并独立计算期望值。

| 动作 | 范围 | 桶总数 | 有债务 | 冷却中 | 可清理 |
| --- | --- | ---: | ---: | ---: | ---: |
| init | ip | 18 | 10 | 8 | 4 |
| issue | session | 30 | 16 | 12 | 8 |
| issue | ip | 42 | 22 | 16 | 12 |
| verify | session | 54 | 28 | 20 | 16 |
| verify | ip | 66 | 34 | 24 | 20 |
| other | other | 78 | 40 | 28 | 24 |
| **合计** | | **288** | **150** | **108** | **84** |

另有 9 个遗留桶，其中 4 个早于采样时刻、3 个恰好到期、2 个晚一微秒到期。页面和命令都报告 4 个可清理。采样时间向后移动两微秒，当前桶可清理数变为 288，遗留桶变为 9，两者均未被删除。空库也显示六组零值。在三个采样场景中，命令文本及 JSON 输出均与基线逐字节一致。原始桶键、测试主体哈希和干扰数据未出现在页面或命令输出中。

## 浏览器、主题与回归

使用真实 Chrome 158.0.8127.36，在 Django 原生 Admin 和 Nova Admin 0.6.1 中分别完成键盘滑块、密码登录、从首页进入统计页、返回本站首页。账号只有两项桶查看权限。两种主题均在 1180 和 375 像素宽度核对表格、时间和遗留桶字段。修正后的首页和统计页侧栏均呈现有效导航，页面不再同时提示已获授权的用户无权查看。中英文标签在 Django 客户端中分别验证。

主环境为 macOS arm64、Python 3.12.16、Django 5.2.17、Pillow 12.3.0、SQLite 3.54.0、Node 24.21.0。57 项定向后端测试、201 项完整后端测试、49 项组件测试及 20 项 Django-client DOM 联调通过。Django 系统检查、迁移漂移、Ruff、覆盖率门槛通过，包语句覆盖率为 98.76%，分支覆盖率为 97.64%。复编中文翻译目录与打包目录的译文相同。

wheel 与 sdist 通过 Twine 严格检查和 34 个运行时文件校验。同一 wheel 的 SHA-256 为 `370c19cb45cd61b5c2225de1217af6a9de605c3d327f3969b15af56ab9a476ef`。每组均确认源码和 wheel 的实际导入路径，Nova 主题取自已提交快照 `376bce7c8ceeeeb5f0a62f07f969227eb66e4adf`。该快照也加入矩阵专用虚拟环境的导入路径，使清空 `PYTHONPATH` 的升级子进程能加载相同主题。

| Python | Django | Pillow | 原生源码／wheel | Nova 源码／wheel |
| --- | --- | --- | ---: | ---: |
| 3.10.20 | 5.2.17 | 12.2.0 | 201／201 | 201／201 |
| 3.11.12 | 5.2.17 | 12.3.0 | 201／201 | 201／201 |
| 3.12.16 | 5.2.17 | 12.3.0 | 201／201 | 201／201 |
| 3.12.16 | 6.1.2 | 12.2.0 | 201／201 | 201／201 |
| 3.13.12 | 6.1.2 | 12.3.0 | 201／201 | 201／201 |
| 3.14.7 | 6.0.9 | 12.3.0 | 201／201 | 201／201 |

主要命令如下。源码使用 `DJANGO_SETTINGS_MODULE=tests.settings`、`PYTHONPATH=src:.` 和独立 `NOVA_TEST_DB`。安装包使用 `PYTHONPATH=.`。Nova 主题使用 `tests.nova_settings`。构建、矩阵与 DOM 输出均保存在任务临时目录。

```sh
python -m django check
python -m django makemigrations nova_slider_captcha --check --dry-run
python -m django test tests.test_rate_stats tests.test_rate_limit tests.test_demo_profile tests.test_localization --noinput -v 1
python -m coverage run -m django test tests --noinput -v 1
python -m django slider_captcha_rate_stats --json
ruff check .
npm ci --ignore-scripts
npm test
NOVA_PYTHON="$PYTHON" NOVA_DOM_REPORT="$DOM_REPORT" npm run test:dom
python -m build --installer uv --outdir "$DIST"
python -m twine check --strict "$DIST"/*
python scripts/check_release.py --dist "$DIST"
python scripts/test_matrix.py --runtimes "$RUNTIMES" --work "$MATRIX" --wheel "$WHEEL" --nova-source "$NOVA_SOURCE" --workers 3
```

本次实测使用本地 SQLite。页面和命令各自采样，现场有时间推移、并发写入或清理时，两次打开的数字可能不同。生产规模下的聚合耗时与远端 CI 未在本轮验证。
