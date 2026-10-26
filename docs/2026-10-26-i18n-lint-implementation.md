# 2026-10-26 i18n回退与基础Ruff实施自测

基线 main / `bfa0cadbb2203ca41a6e983def1c2d07d76448f7`，开始时工作区干净。仍为 **0.3.0待首次发布**。没有commit、push、tag、Release、PyPI上传、部署或启动服务；没有改历史报告/证据或主控独立记录。

本轮因模型容量中断后，先核对已保存代码与44组件/16 DOM/Ruff日志，再继续未完成的文档、覆盖率、包和矩阵，没有重做已通过的组件/DOM测试。运行代码、测试、Ruff配置和工作流已明确冻结；freeze-manifest.json记录身份，之后仅整理实施说明。

## 语言规则与兼容

唯一生产运行改动是 slider.js 的 normalizeLocale：

- 未指定、空白、JavaScript非字符串输入，或格式非法值仍为 zh-CN。
- 格式有效且主标记为zh的系列均为简中，包括zh-Hans / zh-Hant / zh-TW，不新增或虚构繁体字典。
- en系列为英文；显式格式有效但不支持的fr / fr-FR、ja / ja-JP、de、ar等回退en。
- 格式为trim后2–8个ASCII字母主标记，后续单个连字符或下划线分隔1–8个ASCII字母/数字子标记，不区分大小写。不查注册表，不声称完整BCP47、私用或祖父标记语义校验。
- HTML属性天然是字符串；非字符串规则适用于locale属性setter和setLocale入口。未指定locale仍不偷偷继承浏览器/document语言。Django Widget继续传当前语言，由同一个前端规则归一化。

没有新增字典、endpoint或设置，没有修改Django po/mo目录。既有renderLocale更新lang、ARIA和状态文本的路径保持；测试确认属性、locale/setLocale及customElements定义前属性均有效。动态切换没有新的challenge请求，不清proof、不改变generation，原过期timer对象/ID/回调保持，按原时刻失效。

Django-client DOM桥仅增加测试用的每次渲染translation.override上下文，验证真实Admin模板继承fr-fr / ja-jp / de / ar后组件显示英文标签、lang和ARIA；不是生产翻译endpoint。旧中文演示、消费/重放、Admin过期和错误次数流程继续通过。

## Ruff最小落地

已查 [官方配置](https://docs.astral.sh/ruff/configuration/) / [规则表](https://docs.astral.sh/ruff/rules/) 和PyPI可获取版本，独立环境实际安装 **Ruff0.17.2**；requirements-lint.txt固定版本，pyproject required-version再次约束，target-version=py310。不加入运行/optional Requires-Dist，不接mypy，不运行全仓format或--fix。

初扫E4/E7/E9/F得到21条：12条E402、F403两条、F405四条、F401两条、F402一条。最终选择 E401、E711/E712/E713/E714、E721、E722、E9和全部F；必要的bootstrap延迟导入E402及E701/E702/E731等顺序/排版规则不启用。只有tests/settings.py、tests/nova_settings.py精确豁免F403/F405，保留有意的Django设置组合；其他源码星号导入仍拒绝。没有大量noqa或全局blanket ignore。

手工修复三处：dom_bridge删除未使用RateBucket导入；test_integration删除未使用Widget导入；test_urls将遮蔽path导入的循环变量改名。没有重排文件或改迁移、安全逻辑。

明确include范围覆盖src、tests、scripts、demo、examples下Python，以及manage.py、pyproject.toml；实际48个文件（含迁移）检查通过，历史verification/文档不扫描。当前Worker示例为JS，Ruff不声称检查它。独立非特权lint CI job安装固定工具并运行ruff check .；六格source/wheel、coverage与web job保留，发布OIDC job未改。

正反验收9组：正常、紧凑格式和初始化后导入通过；F821未定义、F401未使用导入、语法错误、E711、settings以外F403均拒绝；错误required-version退出2。细节见ruff-probes.json和 [STATIC_CHECKS.md](STATIC_CHECKS.md)。

## 最终差异范围

| 文件/类别 | 内容 |
|---|---|
| slider.js | 语言输入归一化，其他状态/计时逻辑不变 |
| tests/widget.test.mjs | 更新旧fr断言，新增3项功能回归 |
| tests/test_localization.py | 新增1项Django当前未知语言继承测试 |
| scripts/dom_bridge.py、test_dom.cjs | 测试用语言上下文与4组端到端继承检查 |
| test_integration.py、test_urls.py | 未使用导入/变量遮蔽的手工清理 |
| pyproject.toml、requirements-lint.txt、Tests workflow | 最小规则、精确工具pin、独立lint job |
| MANIFEST.in、check_release.py | sdist携带并检查开发复现文件 |
| README、CHANGELOG、RELEASING、STATIC_CHECKS | 当前行为、维护与发布说明 |

TOKEN_TTL、几何、图像算法、Redis、评分、DRF/allauth均未涉及。protected-contract.json逐文件证明服务、策略、表单/日志行为、模型/迁移、图片与Django翻译目录与HEAD相同。日期历史报告不改写。

## 实际自测

六格新建的任务专用uv环境，只读复用旧任务解释器，未修改主控或共享包。每格/profile用独立NOVA_TEST_DB，不触碰demo.sqlite3。

| Python | Django | Pillow | Source完整测试 | 同一wheel完整测试 |
|---|---|---|---:|---:|
| 3.10.20 | 5.2.17 | 12.2.0 | 135通过 | 135通过 |
| 3.11.12 | 5.2.17 | 12.3.0 | 135通过 | 135通过 |
| 3.12.14 | 5.2.17 | 12.3.0 | 135通过 | 135通过 |
| 3.12.14 | 6.1.2 | 12.2.0 | 135通过 | 135通过 |
| 3.13.12 | 6.1.2 | 12.3.0 | 135通过 | 135通过 |
| 3.14.7 | 6.0.9 | 12.3.0 | 135通过 | 135通过 |

每格check、迁移漂移、uv pip check通过，零跳过。Python测试134→135；组件41→44；Django-client DOM检查12→16。

| 其他检查 | 实际结果 |
|---|---|
| 组件 Node24 / jsdom26.1.0 | 44项通过 |
| 真实Django test client + jsdom | 16项检查通过 |
| Ruff0.17.2 | 全部48文件通过；9组正反验收通过 |
| coverage7.17.0（3.12.14/5.2.17/12.3.0，含子进程） | 包语句658/669=98.36%，纯分支160/164=97.56%；forms138/138、42/42均100% |
| 覆盖率维护门槛及12种负向报告 | 通过，未修改门槛或排除分支 |
| sdist解包完整测试及Ruff配置复现 | 135项和Ruff均通过 |
| build / twine check --strict / package check | 29运行文件、依赖及开发文件检查通过 |
| 两份workflow actionlint1.7.12 | 零诊断 |
| git diff --check | 通过 |

未改Worker代码，本轮不重跑Worker测试或引用旧计数。Python覆盖率与既有基线数值相同；本轮生产逻辑改动在JS，Python覆盖率不能证明语言行为。组件/DOM回归覆盖该行为，真实浏览器由主控另行独立验证。

## 构建物、日志与复现

已测构建物位于 `/tmp/nova-slider-i18n-lint-impl-dist-20261026/`，未上传：

| 构建物 | 字节 | SHA256 |
|---|---:|---|
| nova_slider_captcha-0.3.0-py3-none-any.whl | 54,879 | e415d22d60df2d88ff3484876b8f7d54cbc8cc015ff680f535d1232850517d44 |
| nova_slider_captcha-0.3.0.tar.gz | 207,384 | 2160c1b97e749a6f82fb9bb1a7c55e89585172571c92538da2ce09276065e112 |

[证据目录](../verification/2026-10-26-i18n-lint-implementation/) 保留matrix-final.json/log和六格日志、component.log、dom.json/log、ruff-initial.json、ruff-files.txt、ruff-probes.json、ruff-freeze.log、coverage.json/gate/negative日志、build/twine/payload/actionlint、sdist-tests.log、protected-contract.json、freeze-manifest.json和artifacts.json。原始coverage数据留任务临时路径，未向仓库复制生成HTML/XML资产。初始component-initial.log是增加最后3项测试前的41项，不作最终44项结果。

```sh
python -m pip install -r requirements-lint.txt
ruff check .
ruff check --show-files
npm test
NOVA_PYTHON=/path/to/test/python NOVA_DOM_REPORT=/absolute/new-dom.json npm run test:dom

# 稳定coverage profile和独立输出路径，详见COVERAGE.md
python -m coverage run -m django test tests --noinput -v 1
python -m coverage combine --keep
python -m coverage json -o /absolute/new-coverage.json
python scripts/check_coverage.py /absolute/new-coverage.json
python scripts/test_coverage_gate.py /absolute/new-coverage.json

python -m build --installer uv --outdir /absolute/new-dist
python -m twine check --strict /absolute/new-dist/*
python scripts/check_release.py --tag v0.3.0 --dist /absolute/new-dist
python verification/2026-10-26-i18n-lint-implementation/run_matrix.py \
  --modes source,wheel --label new-run --wheel /absolute/new-dist/nova_slider_captcha-0.3.0-py3-none-any.whl
/path/to/actionlint
```

构建/覆盖率工具使用任务专用Python3.12环境，矩阵覆盖其余声明版本。Ruff不是类型检查器，也不能替代运行矩阵；轻量locale规则不验证语言注册表。当前没有验证新增语言字典、RTL布局、真机或辅助技术；没有本实施会话的真实浏览器测试、远端CI、生产数据库/压力或线上环境结果。主控独立浏览器/包/矩阵证据另行记录，不计作本实施自测。
