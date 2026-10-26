# Changelog

## Unreleased — 0.3.0（待首次 PyPI 发布）

Python 包与前端开发包版本同步为 **0.3.0**。以下变化尚未发布到 PyPI；源码已修改或本地测试通过不等于远端 CI 通过、线上部署或已上传。

### 显式未知语言回退与基础Ruff（2026-10-26，待发布）

- 保留未指定/空白、非字符串及格式非法输入的简中默认；zh系列仍简中、en系列英文，显式格式有效但未支持的fr/ja/de/ar等语言回退英文。使用轻量标记形态，不宣称完整BCP47校验；没有新增字典、翻译endpoint或配置项。
- 覆盖HTML属性、locale/setLocale、定义前属性、Django当前语言继承、lang/ARIA/状态与动态切换；切换不重新签发、不清proof、不延长计时。未改Django翻译目录。
- 开发工具精确锁定Ruff0.17.2，target py310，非特权独立CI job；仅E401、E711–E714、E721、E722、E9和F。延迟初始化导入与紧凑风格规则不启用，仅两个测试settings对F403/F405窄豁免。
- 手工删除两处未使用导入、改一处遮蔽导入名的测试循环变量；不一键格式化、不改历史迁移或安全校验逻辑。sdist携带复现开发检查所需文件，运行依赖不变。

### 可选链接降级与覆盖率基线（2026-10-26，待发布）

- Widget 只在读取全局可选替代链接的窄边界捕获配置 ValueError，错误时不显示链接，普通表单/Admin 页面仍可用；E007 与直接配置验证保持严格，显式非法参数仍构造失败，验证码服务/字段验证不变。
- 增加固定低敏可选链接 WARNING；按进程一个时间戳/锁、300秒最多一次，不记录配置内容，日志失败不破坏页面，不缓存动态配置结果。
- 用011c0fd原122项测试建立含子进程的 coverage.py7.17.0 分支基线；仅补缺失的表单边界和新行为回归，校验逻辑不因覆盖率调整。原有缓存/重入/事务用例保留。
- 新增仅开发/CI的覆盖率配置/依赖与纯语句/分支门槛；完整包文件范围、版本、branch模式和计数一致性检查，拒绝空报告、错包和失真的数据。CI保留六格source/wheel同构建物检查，另有稳定profile coverage job及失败时可下载报告；发布OIDC job保持无新执行代码。

### 接入默认值与出图改进（2026-10-26，待发布）

- 核心 urls 只提供 api-root / init / challenge / verify；演示页和 demo 消费迁至显式 demo_urls。Widget 使用 api-root，支持完整命名空间配置，演示 submit 从 form.action 读取；旧接入迁移见 README。
- Pillow 改为 >=12.2,<13，测试 12.2.0 和实际最新 12.x 12.3.0。CI 六格覆盖 Python 3.10–3.14、Django 5.2/6.0/6.1 和 Pillow 两端；各格 source / 同一 wheel 检查，仍只构建一次。
- required=False / disabled=True 在字段构造时明确抛配置异常，保留字段后改写的运行时拒绝；补 errors/full_clean 两种重入保护与永久失效的设计注释。删除空 templatetags 壳，包检查拒绝多余/缺失运行文件及依赖元数据漂移。
- 把逐像素 Python 循环改为 Pillow C 层渐变、纹理与混合，保留安全坐标、独立新鲜种子、PNG、尺寸和透明轮廓；新增局部图像不变量与交错耗时/PNG 大小基准，不宣称增强抗自动化。
- Widget 新增由宿主明确提供、JS 开关均可见的本地安全替代链接，严格 URL/标签校验与转义、显式主题兜底。链接只导航，不自动提供或绕过验证；未配置时不虚构服务。
- 新增可信 Nginx/Uvicorn 与 Nginx/uWSGI 部署示例，明确 REMOTE_ADDR 映射责任、check --deploy 和 prune 成功/表增长监控。未新增可信 header 开关、后台线程或外部验证服务。
- 保持版本 0.3.0 待首次发布；本轮不改语言字典、语言继承/回退或翻译策略。

### 发布准备与策略快照（2026-10-26）

- CI 改为明确配对：3.10/5.2.17、3.12/5.2.17、3.12/6.1.2、3.13/6.1.2，实际安装 matrix.django。修复 job.env 非法引用 runner.temp 的解析问题，临时数据库/DOM 输出使用 step.env，source/wheel 数据库区分两维。
- 构建 wheel/sdist、twine check、逐文件检查模板/静态/翻译/迁移完整性；每格 source 与同一 wheel 完整测试，保留 DOM/Worker。
- 新增 NOVA_SLIDER_CHALLENGE_TTL（30–600）、MAX_ATTEMPTS（1–20）、TOLERANCE（0–10），默认 120/5/4，动态严格整数检查与失败关闭。Challenge 持久化每题 max_attempts/tolerance，迁移 0003 旧行固定为 5/4；TTL 沿用 expires_at。TOKEN_TTL 固定 60，图片尺寸固定。
- 独立嵌入提供暗色兜底，Django/Nova 显式主题优先于 OS；语义 link/error 优先于装饰色，成功采用独立高对比色与不透明背景，缩窄容器文案留白。
- 更新 0.3.0 元数据、真实 repository URLs 与 PyPI 可导航 README 链接；新增最小 Trusted Publishing 工作流，仅正式 Release 触发，版本/tag 一致，测试后上传同一构建物，只有 pypi job 获得 OIDC 权限。补首次 pending publisher 配置说明，本轮不配置账号、不上传、不推送、不打 tag。
- 保留单一 mask，说明随机形状收益边界，不承诺提升抗自动解题能力。

### 通用接入与排障（2026-10-26）

- Django 新增动态读取的 `NOVA_SLIDER_PURPOSES`，配置替换默认 `demo` / `login` 集合；严格校验集合类型、名称语法和 32 字符长度。系统检查、服务与 HTTP 拒绝非法配置，所有用途仍共享动作/IP/session 限流。
- 新增 `SliderCaptchaField` + request-aware `SliderCaptchaFormMixin`，适用于 Form / ModelForm。全部字段、表单及模型验证通过后才消费；多验证码字段同库事务消费，重复验证不重复消费，变更成功实例的凭证上下文会被拒绝。保留 Admin 先消费、再验证密码的行为。
- Widget 支持自定义 purpose，隐藏字段名使用 Django 的完整字段名；原生组件支持 `field-name`，涵盖 prefix / formset / 多组件。空白 formset extra 表单沿用 Django 的忽略语义，整体 formset 不承诺原子消费。
- challenge 协议尺寸由后端 WIDTH / HEIGHT / PIECE_SIZE 常量产生。前端根据有效响应推导范围、比例、ARIA 和宽高比；拒绝异常几何，48px 交互手柄统一为独立 CSS 变量。未开放后端尺寸配置或重写图形遮罩。
- 新增 `nova_slider_captcha` 业务 logger，提供固定事件、机器原因码、HTTP 状态与低敏上下文。503 使用 ERROR；429 默认 DEBUG，可配置级别或关闭；成功默认安静。禁止输出 token、session 秘密、答案、原始请求或异常文本，日志处理失败不改变判定。
- README 补可运行的普通 Form / ModelForm 示例、事务与 formset 边界、日志配置；标明 RateBucket 仅供旧版升级和清理，未来删除须独立迁移，本轮不删表。

### 此前尚未发布的修复（2026-10-26）

- 背景装饰使用独立随机种子的本地 PRNG，缺口坐标与凭证仍用安全随机源；降低出图耗时。
- GCRA 已有桶优先执行条件 UPDATE，减少接受路径 SELECT；保留竞争创建、IP 先扣、拒绝不延债、冷却与失败关闭语义。
- 图片加载在设置 src 前注册事件，兼容缺少 decode、缓存完成及同步 load；清理取消监听，隔离刷新后旧图片事件。
- 统一凭证随机字节数与编码长度，保留严格位置数值检查；Widget 从已有根路由反解 endpoint，支持挂载与脚本前缀。
- 补同源反代、可信 Host / HTTPS、Cookie、prune 调度与密钥轮换说明。
- 增加 GitHub Actions 配置与 Python 3.10 本地验证；测试数据库隔离，DOM 报告须显式指定输出路径，历史记录不被覆盖。
- 文档归并到 docs/ 并保留历史验证范围。

## 0.2.0

- 主要安装、接入、兼容与安全文档中文化。
- 前端提供 `zh-CN` / `en` 字典、动态切换和受限自定义文案，默认中文不变。
- 固定窗口限流改为原子 GCRA 令牌桶；429 返回计算的 Retry-After / retryAfter。
- 新增迁移，保守继承旧桶冷却期；保留原挑战/凭证表和旧限流表。

历史验证与源码范围见 [VERIFICATION.md](VERIFICATION.md) 和 [SOURCE_PROVENANCE.md](SOURCE_PROVENANCE.md)。以上版本条目不推断包索引的上传日期或线上版本。

## 0.1.0

- 导入可安装的 Django app、Admin / 模板 / Web Component、数据库凭证消费，以及 Worker/D1 示例与历史验证记录。
