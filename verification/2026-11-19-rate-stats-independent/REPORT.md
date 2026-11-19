# 限流桶只读统计命令独立验收

2026-11-19，主控独立复核了 GPT-6.2 SOL 实施会话交付的 `slider_captcha_rate_stats`。基线为 `187016a8eb30cdf2b7e537456a0c5260bcb3449d`。相对该基线，命令、回归测试、README 和 CHANGELOG 四个文件的 `git diff --binary` 摘要为 SHA-256 `f525aab453ea0d8805f42eea9604d41cb133bf2ff176dfc899faf4d10d05d34c`。

## 统计与实际删除

主控在隔离 SQLite 库中固定 UTC 时间为 `2026-11-19T00:07:01.123457Z`。五个已知动作/范围组合和一个未知组分别写入不同数量的样本。每组覆盖债务时间和冷却时间相对采样点的全部九种组合：两者各取前一微秒、恰好相等、后一微秒。遗留表的六行分别在采样前、恰好相等、采样后各放两行。

对同一批行先运行文本和 JSON 统计，再调用原有的 `prune_slider_captcha`，按主键核对真实删除和保留的记录，最后重新统计。

| 当前桶分组 | 总数 | 有债务 | 冷却中 | 报告可清理 | 实际删除 |
| --- | ---: | ---: | ---: | ---: | ---: |
| init / ip | 9 | 3 | 3 | 4 | 4 |
| issue / ip | 18 | 6 | 6 | 8 | 8 |
| issue / session | 27 | 9 | 9 | 12 | 12 |
| verify / ip | 36 | 12 | 12 | 16 | 16 |
| verify / session | 45 | 15 | 15 | 20 | 20 |
| other / other | 54 | 18 | 18 | 24 | 24 |
| **合计** | **189** | **63** | **63** | **84** | **84** |

- 当前桶在 `tat_us <= now_us` 且 `blocked_until_us <= now_us` 时才可清理。清理后剩余 105 行，可清理数为 0。21 行同时有债务且处于冷却期，均被保留。
- 遗留桶在 `expires_at < now` 时才可清理。报告可清理 2 行，实际删除 2 行。与采样时间相等的两行保留，清理后共剩 4 行，可清理数为 0。
- 空库、清理前和清理后的两种输出均逐组一致。另用真实限流服务确认，在容量为 2 的场景，首次放行后两个范围都已有债务，下一次请求仍可放行，后续拒绝也未改变聚合数字。

## 只读、路由与输出

主控将 `RateLimitState` 和 `RateBucket` 分配给不同写库，另在默认读库放入干扰数据。统计时三个连接均启用 SQLite 的 `PRAGMA query_only=ON`，并逐条检查 SQL。每种输出各执行两条 SELECT，两张表分别命中各自的写库。默认读库没有收到统计查询，运行前后的行与字段值一致。两种输出中均未出现测试桶的主体哈希或原始键。

同一份报告使用同一个时间判断资格。并发请求仍可在采样与实际清理之间改变桶状态，因此运维现场的删除数可能随时间变化。

## 回归与构建

在独立 Python 3.12.16、Django 5.2.17、Pillow 12.3.0、SQLite 3.54.0 环境中，31 项定向测试和 176 项完整后端测试均通过。Django 系统检查、迁移漂移、旧限流数据升级与回退保护、Ruff 和覆盖率门槛均通过。源码包语句覆盖率为 98.72%，分支覆盖率为 98.51%。

主要命令如下。源码检查使用 `DJANGO_SETTINGS_MODULE=tests.settings`、`PYTHONPATH=src:.` 和每次独立的 `NOVA_TEST_DB`。安装 wheel 后使用 `PYTHONPATH=.` 并核对导入位置。

```sh
python -m django check
python -m django makemigrations nova_slider_captcha --check --dry-run
python -m django test tests.test_rate_stats tests.test_rate_limit --noinput -v 1
python -m coverage run -m django test tests --noinput -v 1
python scripts/test_rate_upgrade.py
ruff check .
python -m build --installer uv --outdir "$DIST"
python -m twine check --strict "$DIST"/*
python scripts/check_release.py --dist "$DIST"
python scripts/test_matrix.py --runtimes "$RUNTIMES" --work "$MATRIX" --wheel "$WHEEL" --workers 3
python -m django slider_captcha_rate_stats
python -m django slider_captcha_rate_stats --json
```

源码与安装包复测使用本机六组 CI 版本配对和 Django 原生主题。

| Python | Django | Pillow | 源码 | 同一 wheel |
| --- | --- | --- | ---: | ---: |
| 3.10.20 | 5.2.17 | 12.2.0 | 176/176 | 176/176 |
| 3.11.12 | 5.2.17 | 12.3.0 | 176/176 | 176/176 |
| 3.12.16 | 5.2.17 | 12.3.0 | 176/176 | 176/176 |
| 3.12.16 | 6.1.2 | 12.2.0 | 176/176 | 176/176 |
| 3.13.12 | 6.1.2 | 12.3.0 | 176/176 | 176/176 |
| 3.14.7 | 6.0.9 | 12.3.0 | 176/176 | 176/176 |

本次 wheel 的 SHA-256 为 `ce2b367a2703ecc848e9e48b54fb02666f6cd2828877c7ebb05681b7850428da`。另在独立环境安装该 wheel 后，通过 Django CLI 实际运行了文本和 JSON 两种输出。wheel 与 sdist 均通过 Twine 严格检查，30 个运行时文件与源码一致。上述结果覆盖本地 SQLite；PostgreSQL、MySQL 的执行计划、生产大表性能和远端 CI 未在本轮实测。
