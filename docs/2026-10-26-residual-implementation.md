# 2026-10-26 可选链接降级与覆盖率实施自测

基线 `main` / `011c0fd`，开始时工作区干净。仅完成用户授权的链接渲染降级与开发/CI覆盖率基线，版本仍 **0.3.0待发布**。没有提交、push、tag、Release、PyPI上传、部署或启动项目服务；没有修改历史证据、主控环境、主控独立报告/目录或 docs/README.md 索引。

运行文件、测试、覆盖率配置和工作流已明确冻结，精确身份见 freeze-manifest.json。之后仅整理说明和证据。TOKEN_TTL、几何、图像算法、语言和凭证校验链未改；protected-contract.json 将策略/服务、模型/迁移、图像、URL、slider.js及翻译与011c0fd逐文件比对为相同。

## 链接降级的窄边界

唯一渲染变化在 SliderCaptchaWidget.get_context：

- 显式合法链接直接使用，不读取全局配置。
- 没有显式链接时，每次渲染重新调用 configured_alternative_link，仅捕获该调用的配置 ValueError，降级为不显示替代链接。
- configured_alternative_link、E007和显式参数构造校验保持严格。其他编程异常、reverse路由异常继续抛出，不扩大catch范围。
- 验证码本身、必填/disabled约束、Form/Mixin消费时机、Admin先于密码认证、缺失凭证拒绝和全部服务安全配置不变。链接配置错误不会提供凭证或旁路认证。

固定低敏事件为 `optional_link / configuration_invalid`，WARNING，action=render，status=200（表示渲染继续可用），无URL、标签、异常文本或请求。events.py用一个时间戳和Lock，最多每300秒每进程记录一次；不按配置内容建缓存键，容量固定，不缓存验证结果。多worker/重启分别计时，不是集群日志配额。先占告警窗口再调用已有event，日志处理器失败也不会每次渲染重试或让页面500。

测试覆盖非法全局仍E007且验证器抛异常、默认/普通Form渲染、Admin GET/POST 200、没有危险链接/标签、缺失proof不访问认证backend、动态恢复、显式覆盖及构造失败、其他错误不吞、32次并发渲染与300秒边界、logger实际抛异常时页面仍可用。

## 覆盖率基线、缺口与门槛

修改运行文件前，先将011c0fd的原始源码/122项测试归档至独立临时目录执行。前后配置相同：coverage.py **7.17.0**，Python **3.12.14**，Django **5.2.17**，Pillow **12.3.0**；branch=true、整个src包、relative_files=true、patch=subprocess，无omit/exclude/pragma排除。包括升级测试启动的Python子进程。

主控独立profile使用Pillow12.2.0，不混称同一环境。只采主进程的旧测量会少计迁移/服务执行，不能与以下含子进程基线直接比较。本轮coverage的PyPI元数据与精确版本在 coverage-availability.json；7.17.0工具要求Python≥3.11，不改变运行包Python3.10兼容范围。

| 范围 | 修改前语句 | 修改前纯分支 | 修改后语句 | 修改后纯分支 |
|---|---|---|---|---|
| 包整体 | 634/651，97.39% | 153/160，95.62% | 658/669，98.36% | 160/164，97.56% |
| forms.py | 125/131，95.42% | 37/40，92.50% | 138/138，100% | 42/42，100% |

组合覆盖率分别为：包97.04%→98.20%，forms94.74%→100%。这些组合值不称纯分支率。

原forms缺失语句52、58–59、135、154–155；缺失分支51→52、134→135、153→154（011c0fd行号）。只补关键边界：无效Widget构造、无效purpose配置、unbound表单不消费、定制清洗器返回非字符串不消费，以及第二个凭证数据库异常回滚第一个真实消费。原有缓存/重入/多凭证失效与重复凭证回滚/首个数据库失败测试保留，不复制镜像测试，也不改Mixin业务逻辑抬覆盖率。

当前forms没有缺失。整个包仍缺11条语句、4个分支：checks.py 12→13、services.py 114→115、views.py 68→69和101→102；另有日志级别/HTTP参数/限流配置异常处理语句未测，详见current.json，不隐去缺口。

维护门槛：包整体纯语句≥97%、纯分支≥95%；forms纯语句≥99%、纯分支≥97%。包门槛低于原有实测，forms在补齐关键边界后建立，留有限维护余量，不意味着所有异常路径或复合条件已穷尽。check_coverage.py按原始覆盖数/总数比较，不用coverage report --fail-under冒充纯分支门槛。

校验器拒绝错版本、未开启branch、文件集合不等于当前整个源包、排除行、明细/合计不一致、空包/forms、零分支，以及低于任一门槛。CI检查实际导入src，并用新临时数据目录。12项负向检查对真实报告做变换，分别验证四项门槛的正确拒绝原因；纯分支不足的样本即使组合百分比较高也不能通过。它不是对恶意伪造所有数据的密码学证明。

## CI、包与文件清单

保留六组source/wheel、单次构建和同一python-distributions artifact发布。新增单独的非特权coverage job，稳定Python3.12/Django5.2.17/Pillow12.3.0 profile；测试失败后always尝试生成HTML/JSON/XML/文本，再上传独立coverage artifact（含原始数据、无Django数据库）。测试失败不会被报告步骤覆盖。OIDC发布job未修改，仍只有下载构建物和官方上传action。

开发依赖仅 requirements-coverage.txt 的 coverage==7.17.0，无运行/optional Requires-Dist变化。MANIFEST及check_release补开发文件在sdist中的完整性要求；sdist已实际复现完整测试、coverage门槛和负向检查。

冻结文件清单（不含证据产物）：

| 文件 | 变化 |
|---|---|
| src/nova_slider_captcha/forms.py | 可选全局链接读取的窄catch |
| src/nova_slider_captcha/events.py | 固定容量、按进程节制的低敏告警 |
| tests/test_alternative.py | 更新合法降级契约、错误Widget构造测试 |
| tests/test_optional_link_fallback.py | 链接/日志/Admin与缺失表单边界回归 |
| .coveragerc、requirements-coverage.txt | 分支/子进程配置、固定开发工具版本 |
| scripts/check_coverage.py、scripts/test_coverage_gate.py | 范围/纯覆盖门槛及真实报告负向检查 |
| .github/workflows/tests.yml | 独立coverage job及失败可读artifact |
| MANIFEST.in、scripts/check_release.py | sdist开发复现文件完整性 |
| README.md、docs/CHANGELOG.md、docs/COVERAGE.md | 行为、统计口径、命令与门槛说明 |
| 本实施记录 | 实施证据与边界 |

## 自测结果

六个本轮新建的uv环境，旧任务/主控环境只读复用基础解释器；每个triple/profile有独立NOVA_TEST_DB，未接触示例数据库。

| Python | Django | Pillow | Source完整测试 | 同一wheel完整测试 |
|---|---|---|---:|---:|
| 3.10.20 | 5.2.17 | 12.2.0 | 134通过 | 134通过 |
| 3.11.12 | 5.2.17 | 12.3.0 | 134通过 | 134通过 |
| 3.12.14 | 5.2.17 | 12.3.0 | 134通过 | 134通过 |
| 3.12.14 | 6.1.2 | 12.2.0 | 134通过 | 134通过 |
| 3.13.12 | 6.1.2 | 12.3.0 | 134通过 | 134通过 |
| 3.14.7 | 6.0.9 | 12.3.0 | 134通过 | 134通过 |

每格check、迁移漂移、uv pip check通过，零跳过；新增12项测试，总数122→134。相关回归首跑39项通过；完整覆盖率采集134项通过。

| 其他验证 | 实际结果 |
|---|---|
| sdist解包：完整测试+覆盖率+门槛+负向检查 | 134项通过，门槛通过 |
| 组件 | 41项通过 |
| Django test client + jsdom DOM | 12项检查通过 |
| build / twine check --strict / check_release | 29运行文件、依赖、开发复现文件通过 |
| actionlint1.7.12 | 两份工作流零诊断 |
| 真实报告负向检查 | 12种非法报告全部拒绝 |
| 故意失败的本地测试 | 退出1；报告仍生成，gate退出1，无假成功 |
| git diff --check | 通过 |

没有改Worker代码，本轮未重跑Worker测试，不引用历史结果作本轮证据。主控另做真实浏览器和独立覆盖率/包矩阵，不纳入本实施测试数量。

## 证据与命令

[verification/2026-10-26-residual-implementation/](../verification/2026-10-26-residual-implementation/)：

- baseline-run.log / baseline.json / baseline.coveragerc：原122项的真实基线。baseline-tests.log仅是最初准备路径错误导致的配置读取失败，不用于基线结论。
- current-tests.log、current.json、coverage-report.log、coverage-gate.json、coverage-negative-final.log：当前134项与统计。HTML/XML和原始coverage数据移至本轮临时artifact，定位/哈希见coverage-artifacts-location.json，避免重复生成资产进入仓库。
- matrix-final.json/log及六格profile日志；sdist-coverage.log / sdist-coverage.json。
- failure-reports/result.json、run.log和coverage.json：合成失败后的可读性，不并入基线/当前覆盖率；其HTML/XML及原始数据也保留在本轮临时artifact。
- component.log、dom.json/log、actionlint.log、build.log、twine.log、payload.log。
- protected-contract.json、versions.json、artifacts.json、freeze-manifest.json：范围、版本、已测包与冻结身份。

已测包在 `/tmp/nova-slider-residual-impl-dist-20261026/`；没有上传。源码完整说明和命令见 [COVERAGE.md](COVERAGE.md)。核心复现命令：

```sh
# 独立Python3.12环境，先安装项目、Django5.2.17/Pillow12.3.0和requirements-coverage.txt。
# COVERAGE_FILE、NOVA_TEST_DB使用新临时路径，source导入路径为src:.
python -m coverage run -m django test tests --noinput -v 1
python -m coverage combine --keep
python -m coverage json -o /absolute/new-coverage.json
python -m coverage report
python scripts/check_coverage.py /absolute/new-coverage.json
python scripts/test_coverage_gate.py /absolute/new-coverage.json

python -m build --installer uv --outdir /absolute/new-dist
python -m twine check --strict /absolute/new-dist/*
python scripts/check_release.py --tag v0.3.0 --dist /absolute/new-dist
python verification/2026-10-26-residual-implementation/run_matrix.py \
  --modes source,wheel --label new-run --wheel /absolute/new-dist/nova_slider_captcha-0.3.0-py3-none-any.whl
npm test
NOVA_PYTHON=/path/to/python NOVA_DOM_REPORT=/absolute/new-dom.json npm run test:dom
/path/to/actionlint
```

CI的always/report/upload契约已本地检查，合成失败后本地确实产生报告，但**远端workflow及artifact下载尚未运行验证**。如果依赖安装/采集本身失败，HTML可能无法生成，job和上传步骤仍保持失败，不把空输出当通过。

未进行本实施真实浏览器、生产负载、PostgreSQL/MySQL、真机或辅助技术验证；未操作生产、外部账号或线上Worker。覆盖率只证明上述工具/profile记录的执行机会，不代表全部输入、错误组合或安全能力。
