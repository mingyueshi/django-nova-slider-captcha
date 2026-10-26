# 第一阶段基础静态检查

开发工具固定 **Ruff0.17.2**，PyPI元数据和独立环境已验证可获取；配置 required-version 同时拒绝不匹配工具。target-version 为 **py310**，对应运行包最低Python版本。没有加入运行依赖或optional Requires-Dist，没有接入mypy。

```sh
python -m pip install -r requirements-lint.txt
ruff --version
ruff check .
ruff check --show-files
```

可用任务专用uv环境安装，避免修改运行环境。配置位于pyproject.toml，打包sdist包含它和requirements-lint.txt。Ruff配置/版本约束依据 [官方配置说明](https://docs.astral.sh/ruff/configuration/)，规则定义见 [官方规则表](https://docs.astral.sh/ruff/rules/)。Ruff是静态检查器；本轮不执行 `ruff format` 或全仓 `--fix`。

## 规则与范围

启用 E401、E711/E712/E713/E714、E721、E722、E9 与全部Pyflakes F。重点捕捉导入、比较、裸except、语法和未定义/未使用名字等问题。不是启用所有E或Ruff默认大规则集；显式选择避免上游默认变化扩大范围。

不启用E402：脚本有先调整sys.path、设置Django环境或django.setup再导入模型的必要顺序，搬动它们会改变启动行为。也不启用E701/E702、E731及格式化/纯排版规则，不为紧凑风格重排数百行。

只有两个精确文件豁免F403/F405：tests/settings.py、tests/nova_settings.py。它们明确组合Django测试设置，完整集成测试验证该行为；其他源码的星号导入仍按F403报告。没有全局blanket ignore、大量noqa、目录级排除或迁移文件豁免。

正向include范围：src/**/*.py、tests/**/*.py、scripts/**/*.py、demo/**/*.py、examples/**/*.py、manage.py和pyproject.toml。迁移在src内照常检查，但不修改历史迁移。历史verification、文档、构建产物及外部环境不扫描；当前Worker示例是JavaScript，由Node测试处理，Ruff不会声称检查其JS。新增Python示例会自动进入范围。`ruff check --show-files` 可确认实际清单。

首次扫描的有效修复只有两处未使用导入及一处测试循环变量遮蔽导入名，均手工改正。12条E402及测试settings的星号组合按上述明确策略处理，而非更改启动/安全逻辑来通过检查。

## 验收与CI

独立非特权lint job在Python3.12安装固定开发工具并执行 `ruff check .`；六格source/wheel、覆盖率和前端检查继续运行。发布job仍只有下载已测构建物和官方上传action，不持有lint执行逻辑。

本轮本地正反验收包括：正常代码、紧凑风格与合法初始化后导入可通过；未定义名字F821、未使用导入F401、语法错误、None比较E711和settings以外的星号导入F403必须拒绝；错误required-version退出2。没有通过临时关闭规则或排除关键文件造通过结果。

运行语言版本兼容仍依靠实际六格测试，target-version不等于完整类型检查或所有Python语法/运行行为证明。新增规则应单独测量现有告警、解释必要豁免、修复真实问题后再启用，不将格式风格变更混入安全修复。当前仍0.3.0待发布；本地通过不代表远端CI运行或发布完成。
