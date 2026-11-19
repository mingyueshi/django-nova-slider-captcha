# 宿主本地背景图池独立验收

2026-11-19 验收通过。原 GPT-6.2 SOL 实施会话负责修改和自测，主控在独立源码副本、虚拟环境和 SQLite 数据库中复测。同一张宿主素材可以生成不同题目，每题的拼块均取自该题缺口所在的区域。移走素材后，现有前端仍可完成下一题并提交凭证。

基线为 `d375777d75ae303583b66dcfc10d3ea29f59e5d0`。最终验收对象为相对基线的八个文件，涵盖配置与系统检查、出图、组件默认替代文本、两份测试、README 和 CHANGELOG。其 `git diff --binary` 的 SHA-256 为 `d561fbb46aa5aa72b06af85920faab0ef0a597520f8844435a4d77c852cc1bac`，不含本报告。

## 逐题出图

主控生成一张 320×160 的坐标色块 PNG，保留原图并记录其文件摘要。然后在独立测试进程内固定装饰随机种子，预设两个互不重叠的位置，通过实际 Django 发题接口连续取题。检查以预先给定的位置和原图为依据。

| 检查项 | 实测结果 |
| --- | --- |
| 缺口位置 | 对两题分别比较背景全部 51,200 个像素。与原图有差异的位置集合，均精确等于该题拼块透明度轮廓平移到预设位置后的集合。 |
| 拼块来源 | 除描边外，两个拼块所有不透明内部像素的颜色都等于原图对应位置。两题的 ID、缺口图和拼块各不相同，原素材文件摘要一致。 |
| 默认行为 | 在基线与候选版本使用相同坐标和种子，且都不配置图池。解码后背景、拼块与透明度通道的摘要逐项相同。 |
| 生成过程 | 复核 `make_puzzle()`，每次调用先用 `secrets` 独立抽取横纵位置，再选择背景，在同一张画布上裁出拼块、绘制缺口。复用素材时仍走这条路径。 |

## 本地素材与回退

- 在 PNG、索引色 PNG 和宽幅 JPEG 上完成发题、验证和凭证消费。JPEG 居中裁切，全透明和半透明 PNG 样本合成到了预期 RGB 值。输出图像均重新编码，测试素材的私有元数据与文件路径未出现在返回内容中。
- 两张有效图片在不同预设装饰种子下均被选中。混合池中的两张无效图未妨碍第三张有效图出题。八个相同失效路径只读取一次。
- 空池、文件缺失、损坏文件、目录以及 URL 配置均进入程序背景路径。Django 检查对非法配置返回 `nova_slider_captcha.E010`。回归另覆盖符号链接、超限文件及像素数、动画 PNG、读取失败和 Pillow 告警被宿主提升为异常。
- 宿主最多配置 8 个本地绝对路径。每题随机尝试至多 3 个不同路径，这 3 个均失效时即回退，池中其他图片留待后续题目抽取。文件上限为 4 MiB，单边上限为 4096 像素，总像素上限为 400 万。EXIF 方向由宿主在部署素材前校正。

## 前端协议与实际浏览器

对基线、候选源码和安装的 wheel 分别检查公开接口。发题返回相同的九个字段，即 `challengeId`、`background`、`piece`、`width`、`height`、`pieceWidth`、`pieceY`、`expiresIn` 和 `maxAttempts`。两张图片均使用 PNG data URI，背景为 320×160 RGB，拼块为 44×44 RGBA。使用测试题预设坐标完成验证后，凭证字段和有效期与基线一致。受保护的演示提交首次返回 200，再次使用同一凭证返回 403。

主控通过 Playwright 驱动本机 Chrome 158.0.8127.36，连接隔离的 Django 演示服务。先用基线版本的滑块组件连接新后端，再用最终组件重复以下流程。仅测试服务使用预设题位。

1. 通过浏览器解码本地色块背景和拼块，核对原始尺寸、渲染比例和已知样本像素。使用键盘完成滑块验证，再点击演示提交。
2. 移走测试服务配置的图片，将窗口收窄至 375 像素，点击刷新。浏览器收到程序背景，滑块仍按比例渲染。再次通过键盘验证并提交，数据库中两题均已验证且凭证均已消费。

复核时发现原组件的替代文本把任意素材都称为“山水图案”。最终版本的中英文描述改为通用的拼图背景，沿用 `background_alt` 翻译键和宿主覆盖方式。仓库回归也使用两个颜色不同的取样区域，能检出跨题复用旧拼块。

## 回归与安装包

主环境为 macOS arm64、Python 3.12.16、Django 5.2.17、Pillow 12.3.0、SQLite 3.54.0、Node 24.21.0。图像及验证码定向测试 42 项、全量后端测试 181 项、组件测试 49 项、Django-client DOM 联调 20 项均通过。Django 系统检查、迁移漂移、Ruff 和覆盖率门槛通过，包语句覆盖率为 98.68%，分支覆盖率为 98.21%。

在以下本地 CI 版本配对中，每组均先核对模块实际导入位置，再分别运行源码与安装包的检查和完整后端测试。

| Python | Django | Pillow | 源码 | 同一 wheel |
| --- | --- | --- | ---: | ---: |
| 3.10.20 | 5.2.17 | 12.2.0 | 181/181 | 181/181 |
| 3.11.12 | 5.2.17 | 12.3.0 | 181/181 | 181/181 |
| 3.12.16 | 5.2.17 | 12.3.0 | 181/181 | 181/181 |
| 3.12.16 | 6.1.2 | 12.2.0 | 181/181 | 181/181 |
| 3.13.12 | 6.1.2 | 12.3.0 | 181/181 | 181/181 |
| 3.14.7 | 6.0.9 | 12.3.0 | 181/181 | 181/181 |

最终 wheel 的 SHA-256 为 `8e89cd831b7f164da88c56b0c8dda6ce896dde8eae4f341f857cd147393dc24c`。wheel 与 sdist 均通过 Twine 严格检查和 30 个运行时文件校验。另在只安装该 wheel 的环境中重跑逐像素和接口对照。

主要命令如下。源码验证使用 `DJANGO_SETTINGS_MODULE=tests.settings`、`PYTHONPATH=src:.` 和任务专用的 `NOVA_TEST_DB`。安装包验证使用 `PYTHONPATH=.`。命令中的环境变量指向独立的解释器、运行时和输出目录。

```sh
python -m django check
python -m django makemigrations nova_slider_captcha --check --dry-run
python -m django test tests.test_images tests.test_captcha --noinput -v 1
python -m coverage run -m django test tests --noinput -v 1
ruff check .
npm ci --ignore-scripts
npm test
NOVA_PYTHON="$PYTHON" NOVA_DOM_REPORT="$DOM_REPORT" npm run test:dom
python -m build --installer uv --outdir "$DIST"
python -m twine check --strict "$DIST"/*
python scripts/check_release.py --dist "$DIST"
python scripts/test_matrix.py --runtimes "$RUNTIMES" --work "$MATRIX" --wheel "$WHEEL" --workers 3
```

本次实测覆盖 macOS 本地文件系统、SQLite、Django 原生主题和桌面 Chrome。其他文件系统、浏览器及生产环境未在本轮实测。
