# Changelog

## Unreleased

以下内容尚未单独发布；Python 包与前端开发包版本号仍为 **0.2.0**。源码已修改或本地测试通过不等于已发布、远端 CI 通过或线上部署完成。

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
