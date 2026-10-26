# 2026-10-26 策略配置与发布准备独立验收

结论：本轮代码与本地发布准备通过独立验收。版本统一为 **0.3.0（待发布）**。用户明确选择“本轮完成发布准备，暂不上传”；没有配置 PyPI 账号、上传、推送、打 tag 或创建 Release。本轮修改尚未提交。

基线为 `main` / `2aca457`。原实施会话 `01a17598-dca2-7783-ad1e-27713d10800a` 继续使用 GPT-6.1 SOL；本会话负责范围、独立代码复核、迁移探针、浏览器与安装包验证。实施自测见 [实施记录](2026-10-26-release-implementation.md)，未来发布操作见 [RELEASING](RELEASING.md)。

## 完成范围

- 新增 `NOVA_SLIDER_CHALLENGE_TTL`（30–600 秒）、`NOVA_SLIDER_MAX_ATTEMPTS`（1–20）、`NOVA_SLIDER_TOLERANCE`（0–10 原图像素），默认保持 120/5/4。严格拒绝 bool、字符串、非整数和越界配置；系统检查为 E006，运行时拒绝放行。
- 迁移 0003 为每个 Challenge 保存尝试次数与容差快照，旧行固定为 5/4，保持原有已尝试次数、过期时间和凭证状态。TTL 继续由 expires_at 保存。修改配置只影响新挑战；无效当前配置会暂停验证与消费，不放宽旧策略。
- 补独立嵌入的暗色兜底，保持 Django/Nova 明确指定的主题优先于系统偏好；修复状态文字和遮罩对比度、窄容器文案留白。没有装饰动画，因此未添加无效果的 reduced-motion 规则。
- CI 使用四组明确的 Python/Django 组合，源码与构建 wheel 均运行完整检查。发布流程只由正式 Release 触发，版本检查及完整测试通过后，独立 pypi job 上传同一构建物；只有该 job 持有 OIDC 发布权限。
- 同步版本、公开项目链接、PyPI 可导航 README、CHANGELOG、包内容检查和首次 Trusted Publishing 说明。TOKEN_TTL 仍为 60 秒，后端几何和单一 mask 保持原设计。

## 主控发现并推动修复

1. **旧 CI 无法启动。** 查到基线提交的 [远端失败记录](https://github.com/mingyueshi/django-nova-slider-captcha/actions/runs/40251422456)，jobs 和 check runs 均为空。独立 actionlint 对旧 HEAD 稳定报告三处 job.env 不允许使用 runner 上下文；实施改为合法的 step.env。最终 tests.yml 与 publish.yml 均通过 actionlint 1.7.12。此处是本地语义验证，不代表新提交已经在 GitHub 成功运行。
2. **暗色错误遮罩的对比度依赖底图。** Django 暗色错误文字在 93% 不透明遮罩上，遇到较亮底图会降至约 4.22:1。实施改为不透明面板后重新浏览器验证，最低遮罩文字对比度为 4.65:1；成功遮罩也保持不透明。

## 独立实测

| Python | Django | 源码完整测试 | 安装 wheel 完整测试 |
|---|---|---|---|
| 3.10.20 | 5.2.17 | 110 通过 | 110 通过 |
| 3.12.14 | 5.2.17 | 110 通过 | 110 通过 |
| 3.12.14 | 6.1.2 | 110 通过 | 110 通过 |
| 3.13.12 | 6.1.2 | 110 通过 | 110 通过 |

每格另外执行 Django check、迁移漂移检查和依赖兼容检查，均通过。wheel 检查确认从 site-packages 导入，PYTHONPATH 仅包含测试目录所在仓库根，不含 src。每次使用独立临时 SQLite 数据库；没有迁移示例数据库或更改其他会话的共享依赖。

其他检查：

- 组件 **40** 项、真实 Django test client + jsdom **12** 项、本地 Worker **25** 项通过。
- 独立策略探针 **5** 组通过：真实 0002 升级保留旧值；变更配置不能扩大旧容差/旧次数；新挑战快照；类型与范围边界；精确过期时刻。同时确认凭证仍为 60 秒、只能消费一次。
- wheel/sdist 构建、`twine check --strict`、版本检查通过；**29 个运行文件**与源码逐字节一致，覆盖静态、模板、翻译和 0003 迁移。运行文件在四组源码测试结束后仍保持一致。
- 发布负向探针 **5** 组通过：拒绝错误版本 tag、rc tag、缺少 v 前缀的 tag，以及缺少策略迁移的 wheel；核对四组矩阵、release-only 触发、发布权限和相同 artifact 名称。
- 真实 Chrome **11 组**系统偏好/宿主主题/容器尺寸检查通过：320px 视口，240px 与 160px 容器，长错误文案和刷新按钮均无横向溢出；显式亮色覆盖系统暗色，显式暗色覆盖系统亮色；减少动画模式下无装饰动画。状态文字最低对比度 **5.41:1**，遮罩文字最低 **4.65:1**。宿主 CSS 为 Django 5.2.17 与本地 Nova theme.css/tokens.css。

浏览器使用真实组件脚本、CSS 和 PNG，但 HTTP 与状态由本地验收页面模拟；这不替代真实 Admin 登录、触屏或辅助技术验证。临时浏览器偏好已恢复，页面和本地验收服务器已关闭。截图见 [暗色窄容器](../verification/2026-10-26-release-independent/django-dark-narrow.png)。宿主自定义配色仍需单独检查。

## 形状建议的本地基线

另生成 24 张本地拼图，使用响应中的透明轮廓、公开 pieceY 和当前渲染器的高亮边缘做匹配，24 张均精确定位，平均匹配约 10.6ms（不含生成图像）。脚本没有固定形状模板，也没有请求公共演示。这支持“仅增加形状库不能解决当前通用匹配路径”的判断；没有实测某个新形状库，也不把小样本结果当作所有攻击方法的成功率。保留“辅助防滥用”定位，不将形状库作为本次发布准备的前置条件。

## 证据与边界

原始证据、独立脚本与机器摘要见 [verification/2026-10-26-release-independent/](../verification/2026-10-26-release-independent/)。`summary.json` 汇总矩阵；`package-identity.json` 记录本次构建物及运行文件 SHA-256；`release-probe.json` 绑定已检查的工作流和检查脚本；`actionlint-baseline.log` 与 `actionlint.log` 保留修复前后差异。源码和 wheel 的每格结果分别保存，没有覆盖旧记录。

可在仓库根目录使用安装依赖的 Python 复现独立探针：

```sh
PYTHONPATH=src:. DJANGO_SETTINGS_MODULE=tests.settings \
  python verification/2026-10-26-release-independent/policy_probe.py
PYTHONPATH=src:. \
  python verification/2026-10-26-release-independent/shape_probe.py
```

发布构建及检查命令见 RELEASING。其他验收脚本中的临时目录记录本次执行位置，复用时应选择新的输出目录；浏览器 fixture 的 `NOVA_ADMIN_CSS` 可指定本地 Nova 静态目录。

本轮未运行新代码的远端 GitHub Actions、PyPI OIDC 交换或上传；也未做 PostgreSQL/MySQL、生产并发负载、真机触控、屏幕阅读器或线上 Worker/D1 验证。未来实际发布仍需维护者配置 pending publisher/environment，推送后确认 CI，通过正式 Release 启动发布，再核对 PyPI 文件及安装结果。
