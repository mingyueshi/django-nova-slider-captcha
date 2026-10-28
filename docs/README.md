# 项目文档

接入和开发入门见仓库根目录的 [README](../README.md)。项目说明、诊断和验证报告集中存放于本目录。

| 文档 | 内容 |
|---|---|
| [会话引擎补充复核](2026-10-29-session-engine-followup.md) | 非法 SESSION_ENGINE 的 E008/503 兜底、无副作用回归及本轮验证 |
| [人工复核修复](2026-10-29-review-fixes.md) | 焦点与 ARIA、子进程、会话子类、Worker、CI/矩阵与本轮证据 |
| [验证索引与历史结果](VERIFICATION.md) | 0.3.0 日期证据入口；保留 0.2.0 原始验证记录 |
| [初始化与验证边界独立验收](2026-10-27-boundary-independent.md) | 主控行为探针、会话后端新进程、六格 source/wheel、覆盖率与冻结文件复核 |
| [初始化与验证边界实施自测](2026-10-27-boundary-implementation.md) | init 创建额度/CSRF 响应、Admin 字段错误、写库一致性、会话能力与六格同 wheel |
| [基础静态检查](STATIC_CHECKS.md) | Ruff精确版本、最小规则、范围与窄豁免 |
| [i18n与Ruff实施自测](2026-10-26-i18n-lint-implementation.md) | 语言回退、动态状态、六格source/wheel、覆盖率及构建物身份 |
| [i18n与Ruff独立验收](2026-10-26-i18n-lint-independent.md) | 主控语言探针、真实浏览器、Ruff反例、同一wheel六格与差异复核 |
| [可选链接与覆盖率独立验收](2026-10-26-residual-independent.md) | 主控降级/日志/覆盖率反例、六格源码与wheel及浏览器检查 |
| [可选链接与覆盖率实施自测](2026-10-26-residual-implementation.md) | 渲染降级、告警节制、覆盖率门槛与实施验证 |
| [分支覆盖率维护](COVERAGE.md) | 统计范围、实测基线、纯语句/分支门槛与CI报告 |
| [后续接入与出图独立验收](2026-10-26-followup-independent.md) | 主控六组源码/wheel、真实浏览器、负向包检查与性能复测 |
| [后续接入与出图实施自测](2026-10-26-followup-implementation.md) | 核心/演示拆分、依赖矩阵、宿主替代入口与图像优化 |
| [可信代理、部署检查与清理监控](DEPLOYMENT.md) | ASGI/WSGI 的 REMOTE_ADDR 映射、生产 checks 和 prune 成功监控 |
| [外部诊断逐项复核](2026-10-26-diagnostic-recheck.md) | 当前提交下的 17 项裁定、针对性实测、功能建议取舍与优先级 |
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

原始日志、机器摘要、测试脚本和历史归档保留在仓库根目录的 [verification/](../verification/)，避免改变已有脚本的输出路径。历史记录中的仓库路径按记录时的布局理解。

Worker/D1 示例的使用说明保留在 [examples/worker-api/README.md](../examples/worker-api/README.md)，便于与示例代码一起阅读。
