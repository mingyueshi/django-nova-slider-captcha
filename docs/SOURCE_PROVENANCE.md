# 源码范围与版本记录

本仓库是 Nova Slider CAPTCHA 的独立开发仓库。0.1.0 的清洁源码导入已完成；0.2.0 在该公开历史上实现文档中文化、前端国际化和 GCRA 限流，不再宣称所有运行文件与 0.1.0 相同。当前 0.3.0 为待首次 PyPI 发布的源码准备，增加通用表单、动态用途、挑战策略快照与发布流程；未上传、未部署。

## 包含的内容

- `src/nova_slider_captcha/`：可安装的 Django app、数据库迁移、模板、Admin 集成、原生前端与翻译目录
- `demo/`、`manage.py`：仅供本地开发的 Django 示例
- `tests/`、`scripts/`：后端、前端、真实 Django-client DOM 集成检查和精确矩阵脚本
- `examples/worker-api/`：可选的 Worker/D1 API、schema、升级迁移、最小入口和测试
- `docs/`：项目说明、诊断报告和验证文档
- `verification/`：验证原始记录、运行文件哈希与明确分开的历史结果

`verification/source-runtime-sha256.json` 是此前版本的运行文件身份记录，后续改动不覆盖它。0.3.0 本轮实际构建与验证见 [发布准备实施自测](2026-10-26-release-implementation.md) 及其独立证据目录。`verification/history-0.1.0/` 保留历史版本结果，不能用于宣称 0.2.0 未经重测的部分已经通过。旧执行日志中的机器根路径已用占位符替换，保留实际版本与测试结果。

## 不包含的内容

在线演示的 React 展示壳、Sites 专用脚手架、项目/数据库绑定、线上运行数据及原托管仓库私密历史不在本仓库。未纳入真实 `.env` 值、用户 session、数据库、Node/Python 环境、缓存、打包归档或托管写入凭据。

仓库发布不会自动把代码部署到第三方账户。公开交互演示由单独的托管项目维护，其后端使用 Worker/D1；Django 是本仓库的主要集成实现。不要把演示站的浏览器测试说成 Django 页面真实浏览器测试。

Nova Admin Theme 0.6.0 的对应公开基线为 [mingyueshi/nova-admin · b0fd37e](https://github.com/mingyueshi/nova-admin/commit/b0fd37e528a6ad76bec646a68d02f017cde3c4b9)。本仓库不内置该主题；运行 Nova 集成矩阵时需明确提供它的源码。

测试覆盖、迁移要求和未验证范围见 [VERIFICATION.md](VERIFICATION.md) 及 [README.md](../README.md)。仓库现已包含 Tests 和仅正式 Release 触发的 Publish workflow；本地 YAML/actionlint 通过不代表远端 CI 已启动或通过。实际上传步骤见 [RELEASING.md](RELEASING.md)，当前仍为待发布。
