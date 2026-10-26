# 项目文档

接入和开发入门见仓库根目录的 [README](../README.md)。项目说明、诊断和验证报告集中存放于本目录。

| 文档 | 内容 |
|---|---|
| [发布准备与维护](RELEASING.md) | 0.3.0 待发布、版本检查、构建与首次 Trusted Publishing 步骤 |
| [发布准备实施自测](2026-10-26-release-implementation.md) | 策略快照、主题修复、配对矩阵及安装包本地验证 |
| [发布准备独立验收](2026-10-26-release-independent.md) | 主控独立矩阵、工作流/发布负向检查和真实浏览器验证 |
| [更新记录](CHANGELOG.md) | Unreleased 0.3.0 与 0.2.0 / 0.1.0 变更，发布边界 |
| [通用接入实施自测](2026-10-26-integration-implementation.md) | 自定义 purpose、Form/ModelForm、几何、业务日志的本地验证 |
| [通用接入独立验收](2026-10-26-integration-independent.md) | 主控复核、跨版本测试、安装包及真实浏览器验证 |
| [源码范围与版本记录](SOURCE_PROVENANCE.md) | 仓库内容、来源和发布边界 |
| [诊断报告](DIAGNOSTIC_REPORT.md) | 问题分析、复核结论和独立验收结论 |
| [2026-10-26 实施自测](2026-10-26-implementation.md) | 本轮改动、实际自测命令、性能和查询数 |
| [2026-10-26 主控独立验收](2026-10-26-independent.md) | 独立复测、浏览器检查和验证边界 |
| [0.2.0 历史验证说明](VERIFICATION.md) | 2026-10-05 验证矩阵与历史结果 |

原始日志、机器摘要、测试脚本和历史归档保留在仓库根目录的 [verification/](../verification/)，避免改变已有脚本的输出路径。历史记录中的仓库路径按记录时的布局理解。

Worker/D1 示例的使用说明保留在 [examples/worker-api/README.md](../examples/worker-api/README.md)，便于与示例代码一起阅读。
