# 2026-10-26 外部诊断报告逐项复核

复核基线：`main` / `f3edfee`，开始时工作区干净。对象为用户提供的 17 项诊断及其功能建议。本轮复核代码、文档和针对性回归，没有实施功能修改，也没有提交、推送、发布或部署。

结论：报告指出了真实的接入问题和图形验证能力边界，但混入过时判断、遗漏的测试与文档，以及未经实证的安全收益排序。不能直接照单实施。“行为信号反打码最值得优先投入”缺少依据；近期更适合处理演示路由隔离、国际化回退、Pillow 依赖策略与持续集成覆盖。

## 逐项裁定

下表编号对应用户报告；“成立”不表示都是安全漏洞，也不表示本轮已授权实施。

| 编号 | 裁定 | 当前证据、影响与处置 |
| --- | --- | --- |
| 1 Demo 默认暴露 | 成立，接入默认值问题；未发现由此产生业务授权绕过 | [urls.py:5](../src/nova_slider_captcha/urls.py) 同时挂载演示页、核心 API 和演示消费接口。`submit` 在 [views.py:129](../src/nova_slider_captcha/views.py) 固定消费 demo 用途，仅返回演示结果。但 [forms.py:24](../src/nova_slider_captcha/forms.py) 还用 `reverse("nova_slider_captcha:demo")` 推导 Widget endpoint，直接删 demo 路由会破坏全部 Widget。建议连同 API 根路径命名一起解耦，让演示显式挂载，补命名空间、挂载前缀与表单回归。 |
| 2 CV 自动解题 | 局限成立，行为评分的优先级缺乏依据 | [images.py:41](../src/nova_slider_captcha/images.py) 使用固定轮廓与高亮边缘。本轮本地 24 张图全部被精确定位，平均匹配 13.90 ms，不需要固定形状模板。该证据只覆盖当前生成器的小样本，不能代替线上攻击成功率；session/purpose 绑定、限流和单次消费仍有独立价值。客户端轨迹同样不可信，缺少轨迹评分不自动构成实现缺陷。 |
| 3 i18n 回退 | 成立，国际接入体验问题；不是新回归 | [slider.js:89](../src/nova_slider_captcha/static/nova_slider_captcha/slider.js) 只识别 en 系列，其余回退中文；现有测试明确固定了这一行为，README 也说明缺省中文。Django Widget 会传递当前语言，因此 fr/ja 站点可能出现英文服务端文案与中文组件混用。建议区分“未指定”与“显式但不支持”的语言，保留缺省兼容并为未知语言提供英文或可配置回退。只有 zh_Hans 翻译目录不代表没有英文：源消息本身是英文。 |
| 4 无可访问性替代 | 局限成立，应改善接入契约 | [widget.html:5](../src/nova_slider_captcha/templates/nova_slider_captcha/widget.html) 只有 noscript 提示，没有可操作的替代链接；开启 JS 的视障用户也不会因 noscript 获得帮助。建议提供始终可见、由宿主明确配置的安全替代入口及示例。替代流程的身份、限流、成本和授权取决于宿主；不能靠增加音频或自动接短信就宣称问题解决。 |
| 5 REMOTE_ADDR 不可配置 | 部署风险成立，指定一个可信头名称不足以解决 | [services.py:77](../src/nova_slider_captcha/services.py) 和 README 已说明只信可信部署链路提供的 REMOTE_ADDR。配置错误确实会让用户共用 IP 桶，但正确代理配置与真实 NAT 用户共用出口是两类问题。优先补可执行的部署示例；如增加 resolver，必须同时定义可信代理来源、头清洗、链解析及畸形值处理，不能仅凭设置了 header 名就信任请求。 |
| 6 系统检查不完整 | 部分误判 | 插件只检查自身契约是合理边界。Django 的部署检查已经报告 `security.W012` 与 `security.W016`，本轮实际调用得到两者；应指导宿主对生产设置执行 `check --deploy`，不重复实现。静态 system check 无法证明外部 cron/Celery 调度真的运行；若要检查 prune 健康度，需要额外的执行时间记录或监控契约。 |
| 7 Python 逐像素出图 | 成立，仍是可测热点 | [images.py:29](../src/nova_slider_captcha/images.py) 仍逐像素计算，但装饰噪声已经从逐像素系统随机源改为独立种子的普通 PRNG。当前本机 12 次生成中位 67.41 ms，其中两张 PNG 保存合计中位 5.88 ms。应先优化绘图计算并比较图像质量、包体和耗时；不能把主要成本归因于 `optimize=True`，也不应未经测量就为小型库新增 NumPy 强依赖。 |
| 8 全部走 DB，无水平扩展 | 前半事实成立，架构结论过度 | 数据库保存状态不意味着应用进程不能横向扩展；共享数据库会有容量与争用边界，但本报告没有生产负载证据。Redis 限流可以列为有需求时的独立方案，不能用普通 cache get/set 替代当前原子语义；双存储还需处理失败关闭、驱逐、持久性、清理及跨存储事务。暂不改后端架构。 |
| 9 errors 属性副作用 | 维护性建议成立，未复现正确性缺陷 | [forms.py:92](../src/nova_slider_captcha/forms.py) 在成功消费后复查 proof 上下文，避免 Django 缓存校验结果后仍接受已更换的 request/session/token/purpose。Django 的 errors 本身就会触发惰性校验，有副作用不是独立缺陷。可补设计注释解释两种重入防护和永久失效语义；不能简化掉保护。现有回归覆盖多次校验和多种上下文变化。 |
| 10 required=False/disabled 报错 | 开发者诊断问题成立，建议的修法不完整 | [forms.py:47](../src/nova_slider_captcha/forms.py) 对不安全用法失败关闭是必要的；本轮复现两者都给出泛化 `captcha_invalid`。可在构造时对明确不支持的配置给出开发者可理解的异常，并保留运行时保护，防止字段后来被改写。Django checks 不会自动发现所有动态创建的普通 Form，因此不能只用 system check 替换运行时拒绝。 |
| 11 策略常量全部不可配置 | 已过时 | [conf.py:27](../src/nova_slider_captcha/conf.py) 已动态读取 `NOVA_SLIDER_CHALLENGE_TTL`、`NOVA_SLIDER_MAX_ATTEMPTS`、`NOVA_SLIDER_TOLERANCE`，严格校验并保存每题策略快照；[test_policy.py](../tests/test_policy.py) 有 11 个测试方法。本轮策略相关测试通过。仍固定的是 TOKEN_TTL 和几何，这些须连同清理与协议单独设计。 |
| 12 空 templatetags 目录 | 事实成立，低优先级清理 | 目录确实只有 `__init__.py`，可以删除空壳。但不能据此推断有未完成的功能计划，也没必要为填目录而新增 template tag。 |
| 13 Pillow 精确锁定 | 接入约束成立，“必然冲突”夸大 | [pyproject.toml:10](../pyproject.toml) 固定 `Pillow==12.2.0`，会限制宿主依赖求解和升级，但只有宿主约束不包含 12.2.0 才冲突。建议测试后改为有证据的范围，将可复现环境的精确锁定放在开发/CI 约束中；不能直接放宽到未经验证的 `>=10,<13`。可先评估当前 12.x 内的范围，再决定是否支持旧大版本。 |
| 14 CI 仅 3.10/3.12 + 5.2 | 描述已过时，覆盖缺口部分成立 | [tests.yml:39](../.github/workflows/tests.yml) 已有 3.10/5.2.17、3.12/5.2.17、3.12/6.1.2、3.13/6.1.2，并分别验证源码和同一构建 wheel。当前没有持续覆盖 classifiers 中的 Python 3.11、3.14 和 Django 6.0；可补代表性配对或调整支持声明，无需构造不兼容的全笛卡尔积。本轮未检查远端运行状态。 |
| 15 表单只有两个测试 | 关键依据错误，工具缺口属实 | `test_forms.py` 两项是 Widget 路径测试；[test_integration.py:41](../tests/test_integration.py) 有 13 项 Form/ModelForm 回归，全文件 21 项，覆盖模型错误、重复消费、缓存上下文变动、多字段回滚、formset 和数据库失败。`test_images.py` 确实只有一个测试方法，含边界位置与图像结构子案例。仓库未配置 coverage/ruff/mypy，但测试数量或工具缺席不能直接证明测试质量差；优先补有价值的覆盖率基线和图像/协议不变量。 |
| 16 删除历史验证资料 | 不采纳整批删除建议 | 当前追踪的 `verification/` 有 191 个文件，合计 581,308 字节，约 568 KiB；[MANIFEST.in:7](../MANIFEST.in) 明确从 sdist 排除它。文件数量多不等于发布负担。保留可追溯的历史证据符合仓库规则；可改善索引、减少未来重复产物，需迁移时保留可访问来源与校验关系，不仅留“最新报告”抹去历史。 |
| 17 prune 无调度建议 | “无建议”错误，运维风险成立 | [README:323](../README.md) 已给每五分钟 cron 示例、环境/数据库要求及债务保留边界。忘记调度确实导致状态持续累积；可以补成功执行时间、清理量或表大小监控，但没有 Celery 片段不构成缺陷，也不宜让库默认启动后台线程。 |

## 需要单独决策的安全边界

### R-1：视觉验证不能被当作强防自动化控制

- 级别：在本库“辅助防滥用”的定位下属于已知能力限制；若宿主将其作为唯一的防机器人控制，风险会显著提高。
- 位置与证据：`images.py:41–55`，透明轮廓、公开 pieceY 与固定高亮边缘；本地探针本轮 24/24 精确匹配。
- 影响：自动化客户端可在单次正确答题中获取合法证明；降低容差或增加轮廓数量不能直接消除此匹配路径。
- 建议与缓解：保留服务端单次消费和入口限流，结合宿主账号/业务级限制；如要升级为行为风控，先定义威胁模型、数据来源、误报容忍和独立评测，再决定协议与存储变更。
- 限制：未访问公共端点，未测拟议的新渲染器或行为模型，未证明任何通用线上成功率。

“轨迹/时序评分是对抗打码平台最有效的一步”不予采纳为既定结论。客户端可构造提交的轨迹；签名或混淆前端也不能把它变成可信来源。它可以成为辅助信号，但必须考虑键盘、触摸、辅助技术、隐私和真实分布，且不能据此承诺阻止人工代答。W3C 对启发式检测也强调需要站点数据和适配变化中的自动化行为，参见 [CAPTCHA 研究说明 §2.2.3](https://www.w3.org/TR/turingtest/#heuristics)。

### R-2：可访问性替代入口尚未形成完整接入能力

- 级别：中等产品接入风险；如果宿主没有另行提供路径，非视觉用户无法独立完成视觉挑战。
- 位置与证据：`widget.html:5` 仅有 noscript 文字，README 只声明宿主责任。
- 建议与缓解：提供始终可见的替代入口配置与宿主示例，保留同等的业务授权和滥用限制；由宿主选择适合其身份和成本模型的流程。
- 限制：未检查任何宿主线上网站，不能声称所有接入站点都排除了视障用户；本轮没有真实辅助技术测试。

音频并不能覆盖所有残障情况，邮件/短信验证也不自动等价于“是真人”。增加替代能力值得推进，但不应默认植入一套外部消息服务。相关限制见 [W3C CAPTCHA 可访问性说明](https://www.w3.org/TR/turingtest/)。

## 功能建议取舍

| 建议 | 复核意见 |
| --- | --- |
| 行为轨迹、时序、加速度评分 | 暂缓作为发布前置；需要可验证的效果、误报与无障碍基线，不能默认放行低分辨率或缺失信号。 |
| 可信代理 header 配置 | 先补部署示例；若实施代码扩展，做完整可信来源/resolver 契约，默认仍使用 REMOTE_ADDR。 |
| 蜜罐、隐形零交互放行 | 蜜罐仅作辅助；未触发蜜罐不能证明合法，默认零交互放行会改变安全契约，须单独设计。 |
| DRF 字段/mixin | 有接入需求时值得做。现有 HTTP API 与 consume 并非 REST 空白；适配器须明确 session/身份绑定、最终校验和单次消费时机。 |
| allauth/LoginView helper | 需求驱动。不能直接套通用表单消费顺序而让密码验证先于 CAPTCHA；需对齐登录威胁模型。 |
| template tag | 低优先级，现有 Web Component 标签已能用于非表单场景；先证明能减少实际接入代码。 |
| 测试 helper | 有价值。优先明确作用域的 mock/context manager 或测试凭证工具；不要增加容易误开到生产的全局 bypass setting。 |
| 几何/TTL/容差/次数设置 | 后三项已实现；几何及 TOKEN_TTL 继续按独立设计评估，不重复施工。 |
| Redis/cache 存储 | 有测量出的瓶颈后再推进，保持原子性和失败关闭，避免通用 cache 抽象弱化安全保证。 |
| 自定义图像源 | 中低优先级扩展。可先考虑本地可信 provider；远程 URL、格式解码和大图资源限制会引入新边界。 |
| 更多语言与 Django 字典打通 | 先修回退策略，再按目标语言补包；当前已有客户端 messages 覆盖接口，不必为统一文案强加翻译 endpoint。 |
| 音频/邮件/短信替代 | 优先宿主替代入口和清晰契约，独立评估消息成本、限流与身份依赖。 |
| 暗色 CSS 变量 | 已实现；`slider.css:15–68` 有宿主变量、系统暗色兜底与显式主题优先级，本轮相关组件测试通过。 |
| Prometheus/statsd hook | 有运维需求时可加可选低基数事件 hook；不要强依赖指标平台，也不要把 token/IP/session 加作标签。 |
| Admin 统计面板 | 暂缓；先定义可用统计数据、保留策略和权限，现有 Challenge 状态与 prune 不能直接代表长期成功率。 |

## 建议的实施顺序

1. **近期接入与分发修正**：Demo/API 根路径解耦、未知语言回退、Pillow 支持范围验证、补足 CI 声明缺口。这些边界具体、收益明确，适合独立实施与验收。
2. **低风险维护与运维体验**：字段误配置的开发者提示、errors 缓存设计注释、部署检查入口、代理示例、清理监控指引；顺带清理空目录。
3. **有明确验收目标再实施**：出图优化、可访问性替代入口、测试 helpers 与实际需要的集成适配器。
4. **单独立项评估**：行为评分、Redis、隐形模式、图像源插件、完整统计平台。它们会扩大状态、协议或外部依赖，不适合当作本轮诊断的机械修复。

Pillow 的范围不能脱离 Python 支持矩阵：官方表列出 Pillow 12 支持 Python 3.10–3.14，Pillow 10.x 不覆盖其中所有版本，Pillow 13 又不支持 Python 3.10。因此 `>=10,<13` 不是经过验证的替换答案。可先评估 `>=12.2,<13`，测试最低版本及该范围最新版本后再决定；这仍不会满足要求 Pillow 10/11 的所有宿主。参见 [Pillow Python 支持表](https://pillow.readthedocs.io/en/stable/installation/python-support.html)。

部署 Cookie 检查应复用框架：本轮本地运行 `run_checks(tags=[Tags.security], include_deployment_checks=True)` 并将两项 Secure 设置为 False，得到 `security.W012`、`security.W016`；这是对内置能力的验证，不是对宿主生产配置的审计。参见 [Django security checks](https://docs.djangoproject.com/en/6.0/ref/checks/#security)。

## 本轮验证与限制

- Python 3.12.14、Django 6.1.2、Pillow 12.2.0；Node 24.21.0。复用已有独立测试环境，未安装或修改共享依赖。
- `DJANGO_SETTINGS_MODULE=tests.settings`、`PYTHONPATH=src:.`，`NOVA_TEST_DB` 使用 `mktemp -d` 创建的新任务目录内 SQLite 文件；未访问示例或生产数据库。
- `python -m django test tests.test_integration tests.test_policy tests.test_forms tests.test_localization tests.test_images --noinput -v 1`：40 项通过，checks 无问题。
- `npm test`：40 项通过，包括语言别名/未知语言回退、几何和主题契约。
- 路由解析探针确认 `/captcha/` 指向 demo，`/captcha/submit` 与 `/captcha/demo` 指向 submit；Widget endpoint 依赖 demo 命名路由。
- 字段探针确认 `required=False`、`disabled=True` 均以 `captcha_invalid` 拒绝；未涉及凭证或业务写入。
- 对 `make_puzzle()` 连续采样 12 次，并临时计时 `Image.Image.save` 后恢复方法：总耗时中位 67.41 ms（66.74–72.07 ms），两张 PNG 保存合计中位 5.88 ms。只用于本机热点判断，不推导生产吞吐。
- `PYTHONPATH=src:. python verification/2026-10-26-release-independent/shape_probe.py`：本轮新执行 24/24 精确匹配，平均 13.90 ms；未覆盖或改写历史输出文件。
- AST 清点得到 110 个 Python 测试方法：captcha 34、rate_limit 29、integration 21、policy 11、logging 7、localization 5、forms 2、images 1。方法数不是覆盖率，本轮也未跑全部 110 项。
- 本轮没有重新执行完整版本矩阵、wheel 安装、真实浏览器或远端 CI，也没有测试 PostgreSQL/MySQL、Redis、生产负载、真实辅助技术或线上演示。

本轮仅新增本复核文档及索引。历史报告保持原样，功能修复留待用户确定实施范围。
