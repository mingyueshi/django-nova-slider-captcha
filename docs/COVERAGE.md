# 分支覆盖率基线与维护

覆盖率用于观察回归缺口，不能证明验证码安全、所有输入正确、生产性能或浏览器可访问性。当前版本仍为0.3.0待发布。

## 统计口径与版本

开发/CI工具单独安装，不进入运行 dependencies 或 optional Requires-Dist：

```sh
python -m pip install -r requirements-coverage.txt
```

coverage.py7.17.0要求Python≥3.11；这不改变验证码运行支持Python3.10的声明，覆盖率只在下面的稳定开发profile采集。

本轮精确使用 **coverage.py 7.17.0、Python3.12.14、Django5.2.17、Pillow12.3.0**。CI的专门coverage job选择Python3.12，同样锁定Django/Pillow和coverage版本；六格source/wheel验证继续独立运行，不把覆盖率工具加进运行依赖。

`.coveragerc` 开启branch，source限定整个 `src/nova_slider_captcha`，relative_files开启；`patch=subprocess` 同时采集现有升级测试启动的Python子进程。没有omit、exclude或pragma排除，迁移、management、空__init__都在范围内。分支和子进程选项依据 [coverage官方配置](https://coverage.readthedocs.io/en/latest/config.html)。

只采主进程的报告会少计升级脚本执行的迁移/服务行，不能与本基线直接比较。本轮主控另用Pillow12.2.0独立验证，不称为同一环境；此页前后两次实施测量均为上方12.3.0 profile和相同子进程口径。

## 修改前后实测

修改前从Git `011c0fd` 归档到临时目录，以原始122项测试执行；修改后134项，均完整运行且零跳过。配置、解释器和依赖保持一致。

| 范围 | 语句 | 纯分支 | 组合百分比 |
|---|---|---|---|
| 011c0fd 包整体 | 634/651 = 97.39% | 153/160 = 95.62% | 97.04% |
| 011c0fd forms.py | 125/131 = 95.42% | 37/40 = 92.50% | 94.74% |
| 本轮包整体 | 658/669 = 98.36% | 160/164 = 97.56% | 98.20% |
| 本轮 forms.py | 138/138 = 100% | 42/42 = 100% | 100% |

原forms缺失语句52、58–59、135、154–155；缺失分支51→52、134→135、153→154（行号按011c0fd）。补充了无效Widget的构造诊断、无效purpose配置、未绑定表单、清洗器返回非字符串、第二个凭证出现数据库异常时回滚第一个真实消费，以及链接降级/恢复/日志故障路径。原有缓存失效、重入、多凭证失效/重复凭证回滚和数据库首个失败用例不重复创建。

当前forms没有缺失语句/分支。包整体仍有11条未覆盖语句、4个缺失分支，详见本轮current.json和报告；缺失分支为 checks.py 12→13（必要中间件缺失）、services.py 114→115（直接签发不支持用途）、views.py 68→69（请求体实长超限）和101→102（init跨源拒绝）。未覆盖语句还包括无效日志级别降级、非法Content-Length及限流配置异常处理。没有为追求100%扩大业务逻辑或排除代码。源代码后续变化会移动行号，应以新JSON/HTML为准。

## 维护门槛

`scripts/check_coverage.py` 分别验证：

| 范围 | 纯语句最低值 | 纯分支最低值 |
|---|---:|---:|
| 整个包 | 97% | 95% |
| forms.py | 99% | 97% |

包整体门槛低于修改前已测值；forms门槛是在补齐关键边界后建立，不表示旧基线也达到它。当前forms全覆盖，但保留少量维护余量，不把任意新防御分支缺口都转成仓促的镜像测试。新增关键路径仍须评审实际行为和缺失明细。

门槛用覆盖数/总数的原始整数比较，不按显示四舍五入结果判定。`coverage report` 在branch开启时显示的是语句与分支机会的**组合**值；`--fail-under`也不是纯分支门槛。本项目不使用它冒充纯分支检查，公式及展示依据 [官方report说明](https://coverage.readthedocs.io/en/latest/commands/cmd_report.html)。

校验器还要求固定coverage版本、明确branch模式、与当前整个源包完全相同的文件集合、零排除、非空包/forms、每文件明细与汇总计数一致。因此漏掉文件、装错包、空报告、未开启branch、只有零分支数据或不一致报告不能假通过。CI另检查实际导入路径在当前src下，并使用全新临时数据路径；这不构成对恶意伪造所有报告内容的密码学证明。

## 可复现命令

在仓库根目录、安装了项目依赖和requirements-coverage的独立环境中执行。输出目录选新名称；数据库在报告目录之外，避免失败时将业务/测试数据库打进报告artifact。

```sh
NOVA_COVERAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/nova-slider-coverage.XXXXXX")"
export COVERAGE_FILE="$NOVA_COVERAGE_DIR/.coverage"
export NOVA_TEST_DB="$NOVA_COVERAGE_DIR-test.sqlite3"
export DJANGO_SETTINGS_MODULE=tests.settings
export PYTHONPATH=src:.

python -c "import pathlib,nova_slider_captcha; assert pathlib.Path(nova_slider_captcha.__file__).resolve().is_relative_to(pathlib.Path('src').resolve())"
python -m coverage run -m django test tests --noinput -v 1
# 即使上一条测试失败，也单独继续生成报告；不要把测试失败的退出码覆盖成成功。
python -m coverage combine --keep
python -m coverage json --pretty-print -o "$NOVA_COVERAGE_DIR/coverage.json"
python -m coverage html -d "$NOVA_COVERAGE_DIR/html"
python -m coverage xml -o "$NOVA_COVERAGE_DIR/coverage.xml"
python -m coverage report
python scripts/check_coverage.py "$NOVA_COVERAGE_DIR/coverage.json"
python scripts/test_coverage_gate.py "$NOVA_COVERAGE_DIR/coverage.json"
```

最后的负向检查基于一份真实且已通过的报告，拒绝空数据、无branch、错包、缺forms、错版本、错误合计、零分支、排除行，以及四个包/forms语句/分支低于门槛的内部一致报告，并检查拒绝原因。纯分支不足的样本即使组合百分比较高也必须失败。JSON字段来源见 [coverage JSON说明](https://coverage.readthedocs.io/en/latest/commands/cmd_json.html)。

sdist包含 `.coveragerc`、requirements-coverage.txt及两个检查脚本，可解包后按相同目录结构执行；wheel运行安装不附带这些开发工具，也没有新增运行依赖。

## CI与报告读取

coverage job在非特权环境运行完整测试。测试步骤失败后仍尝试combine并生成HTML、JSON、XML和文本；gate步骤不会掩盖前面的失败。`always()`上传独立的 `python-coverage-3.12-django-5.2.17` artifact，含原始覆盖率数据（包括隐藏文件），不会上传Django测试数据库。正常测试失败仍可下载报告分析；如果依赖安装/采集本身失败，报告可能无法生成，原始文件与job日志仍用于诊断，job保持失败。

发布工作流只调用Tests并等待全部job通过；持有OIDC的publish job仍只有下载已测构建物和官方发布action，不执行覆盖率或项目脚本。本地通过不代表远端CI已运行。
