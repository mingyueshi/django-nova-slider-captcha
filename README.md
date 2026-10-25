# Nova Slider CAPTCHA 0.2.0

可自行部署、方便接入 Django 的拼图滑块验证码。提供可安装的 Django app、原生 JavaScript Web Component、模板与 Django Admin 示例，以及可选的 Worker/D1 API 示例。适配 Nova Admin Theme 0.6.0，不修改 Django 或 Nova 的全局行为。

[公开交互演示](https://nova-slider-captcha.mingyueshi.chatgpt.site)使用 Worker + D1 服务端；本仓库根目录是 Django 组件。`examples/worker-api/` 保留演示的 API 逻辑、数据库 schema 和最小入口，托管演示的 React 展示页面、Sites 脚手架、部署绑定和运行数据不在仓库中。克隆代码不会复制线上服务。详见 [源码范围](docs/SOURCE_PROVENANCE.md)。

## 0.2.0 的变化

- 主要说明、安装、接入、安全与兼容文档改为中文
- 前端文案集中到 `zh-CN`、`en` 字典，支持显式语言、动态切换和自定义文案；原有默认中文保持不变
- 固定窗口计数改为数据库原子 GCRA 令牌桶：连续补充额度，不再于整分钟同时恢复全部额度
- `429` 返回计算出的 `Retry-After` 与 `retryAfter`；新增迁移保守保留旧限流状态的冷却期

升级前请先阅读下方“从 0.1.0 升级”，不要直接让新旧限流代码同时运行。

## 安装与本地试用

建议使用已验证的 Python / Django 组合。进入克隆的仓库：

```sh
python -m venv .venv
# Linux / macOS；Windows 请使用 .venv\Scripts\activate
. .venv/bin/activate
python -m pip install .
```

使用随附的开发示例：

```sh
python -m pip install -e .
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

打开 `/captcha/` 体验验证码，或 `/admin/login/` 测试 Admin 登录。示例默认 `LANGUAGE_CODE='zh-hans'`，只绑定本机主机名，含明确标记的开发用密钥，不能直接用作生产配置。生产环境需要自己的密钥、允许的主机、HTTPS、Cookie、安全代理设置和静态资源部署。

## 接入已有 Django 项目

1. 在 `INSTALLED_APPS` 加入 `nova_slider_captcha`，保留 Django 的 session、认证与 CSRF 中间件。
2. 在项目 URL 中挂载接口：

```python
from django.urls import include, path

urlpatterns = [
    path("captcha/", include("nova_slider_captcha.urls")),
    # 项目原有路由……
]
```

3. 执行 `python manage.py migrate`，生产环境按自身流程执行 `collectstatic`。
4. 在需要保护的业务接口中验证并消费凭证。前端的“验证成功”事件不能代替服务端检查。

## 模板与独立前端

加载同源静态资源，再放置组件：

```html
<link rel="stylesheet" href="/static/nova_slider_captcha/slider.css">
<script defer src="/static/nova_slider_captcha/slider.js"></script>
<nova-slider endpoint="/captcha/" purpose="demo"></nova-slider>
```

使用 Django 模板时，静态路径应通过 `{% static %}` 生成。组件会调用 `GET /captcha/init` 初始化 session 与 CSRF，然后使用同源 JSON POST 请求。跨域 CORS 接入未提供；前后端分开开发时，通过同源反向代理接入。

例如页面位于 `https://www.example.com/` 时，将浏览器可见的 `https://www.example.com/captcha/` 反代到 Django，并让组件使用 `endpoint="/captcha/"`。前端和验证码接口需要相同的 scheme、Host 和端口；`api.example.com` 仍是不同 origin。`same-site` 请求也被拒绝，增加 `CSRF_TRUSTED_ORIGINS` 不会放开这项约束。

代理应保留外部 Host，向 Django 准确传递外部 HTTPS scheme，并正确配置 `ALLOWED_HOSTS`；仅在入口代理会移除客户端伪造头并重新设置时，才配置 `SECURE_PROXY_SSL_HEADER` / `USE_X_FORWARDED_HOST`。保证 session/CSRF Cookie 的域、路径覆盖页面与验证码接口，并在生产启用 Secure；代理不得缓存验证码响应或丢弃 `Set-Cookie`。可信代理还需正确提供客户端 `REMOTE_ADDR`，本组件不会直接读取 `X-Forwarded-For`。不要通过关闭 CSRF 或宽泛信任客户端转发头解决代理错误。

组件内部自带一个名为 `nova_slider_token` 的隐藏表单字段。不要在外面重复渲染同名字段。成功事件 `verified` 的 `event.detail` 为 `{token, expiresIn}`；凭证失效或刷新时发出 `captcha-reset`，状态变化发出 `captcha-state`。只在相关表单内临时保留凭证，不放入 URL、日志或持久浏览器存储。

业务接口示意：

```python
from django.http import HttpResponseForbidden
from nova_slider_captcha.services import consume

# purpose 必须由可信业务代码固定，不能直接相信客户端传来的值。
if not consume(request.POST.get("nova_slider_token"), request, purpose="login"):
    return HttpResponseForbidden("Verification required")
# 在这里继续已经获授权的业务操作。
```

消费是单次的。后续操作失败时可能需要重新验证；如果把消费放进更大的数据库事务，事务回滚也会撤销消费。请明确事务边界，对支付等重要业务另设幂等控制。验证码不替代认证或授权。

`X-CSRFToken` 可使用模板中的 `{% csrf_token %}` 或 `/captcha/init` 返回的值；不必读取 Cookie，因此兼容 `CSRF_COOKIE_HTTPONLY=True`。使用 `CSRF_USE_SESSIONS=True` 时仍须保持正常的中间件顺序。

## 前端国际化与自定义文案

不指定 `locale` 时仍使用中文。显式指定英语：

```html
<nova-slider endpoint="/captcha/" purpose="demo" locale="en"></nova-slider>
```

支持 `zh-CN` 和 `en` 两个实际字典。`en-US`、`en_GB` 等英语地区标记回退为 `en`；中文地区标记、未知或无效语言回退为简体中文。没有繁体中文专用字典，也不声明 RTL 语言支持。组件不会根据浏览器语言悄悄改变旧版的默认中文行为。

```javascript
const slider = document.querySelector('nova-slider');
await customElements.whenDefined('nova-slider');
slider.setLocale('en');      // 也可 slider.locale = 'en'
slider.messages = {
  ready: '请将拼图拖到缺口位置',
  incorrect: '还未对齐，剩余 {remaining} 次机会',
  success: '已通过，本次凭证有效期约 {seconds} 秒'
};
// slider.messages = null;  // 清除自定义文案，恢复当前语言的默认字典
```

修改 HTML `locale` 属性、JavaScript `locale` 属性值或调用 `setLocale()` 都会更新可见状态和 ARIA 文本，不重新出题、不延长有效期、不清除已获得的凭证。语言变化发出 `captcha-locale`，其 `detail.locale` 为解析后的语言。

覆盖对象只接受已知键、纯字符串，每条最多 2000 字符。文案通过文本节点渲染，不解释 HTML。支持的数值占位符是 `{remaining}`、`{seconds}`、`{percent}`，不会把任意服务端字符串插入界面。`getText(key, values)` 可供集成页面复用组件的本地化提示。

主要键：

- 说明与无障碍：`widget_label`、`background_alt`、`piece_alt`、`track`、`slider_label`、`refresh_label`、`refresh`、`keyboard`、`value`
- 正常状态：`connecting`、`generating`、`loading`、`ready`、`checking`、`success`、`success_overlay`
- 错误与恢复：`incorrect`、`rate_limited`、`rate_limited_unknown`、`session_expired`、`csrf_failed`、`unavailable`、`challenge_unavailable`、`init_required`、`expired`、`token_expired`、`already_verified`、`attempts_exhausted`、`init_failed`、`generation_failed`、`verification_failed`、`network_error`、`endpoint_invalid`、`endpoint_origin`
- 随附示例提交结果：`demo_accepted`、`demo_rejected`、`demo_network_error`

Django 表单与模板使用 Django `gettext`/`gettext_lazy`，随包提供 `zh_Hans` 翻译目录；由宿主项目的语言配置或翻译上下文选择语言。后端返回稳定的机器 `code`，客户端据此本地化，不能直接展示未经处理的后端 `message`。未知错误使用本地安全回退提示。

## Django Admin 与 Nova Admin

新建明确启用验证码的 AdminSite：

```python
from nova_slider_captcha.admin import SliderCaptchaAdminSite
admin_site = SliderCaptchaAdminSite(name="admin")
# 在该 site 注册项目实际使用的模型与 ModelAdmin。
```

已有 AdminSite 必须同时配置表单和模板：

```python
from nova_slider_captcha.forms import SliderAdminAuthenticationForm
admin_site.login_form = SliderAdminAuthenticationForm
admin_site.login_template = "nova_slider_captcha/admin_login.html"
```

表单负责服务端强制验证，模板负责渲染组件与静态资源，两者缺一不可。原生 Django 登录模板不会自动展示任意新增字段。随附模板扩展当前选中的 `admin/login.html`；启用 Nova 0.6.0 时保留其品牌面板和额外字段布局。请把 `nova_admin` 放在 `django.contrib.admin` 之前，并保留 Nova 文档要求的 context processor。

每个单独挂载的 AdminSite 都要配置，保护一个入口不会自动保护其他入口。已有自定义认证表单时，应先审查验证逻辑和 MRO，再组合验证码校验，不要悄悄替换它。缺失、过期、跨用途或已消费的凭证会在密码认证前被拒绝；密码错误也会消费本次凭证，需要重新拼图。

## HTTP 协议

所有验证码响应禁止缓存，所有状态变更接口要求 JSON、同源请求和 CSRF。先初始化会话：

- `GET /captcha/init` → `{csrfToken}`
- `POST /captcha/challenge`，请求 `{purpose:"demo"|"login"}`，返回 `{challengeId,background,piece,width:320,height:160,pieceWidth:44,pieceY,expiresIn:120,maxAttempts:5}`
- `POST /captcha/verify`，请求 `{challengeId,x}`，成功返回 `{ok:true,token,expiresIn:60}`；失败返回 `{ok:false,code,...}`
- `POST /captcha/submit`，请求 `{token,purpose:"demo"}`，只演示消费凭证；`/captcha/demo` 是 Django 的别名

图片为扁平 PNG data URL，不包含数字答案、图片种子或可直接读取缺口位置的向量结构。人和程序仍可以从图像像素推断位置，因此不声称答案能对视觉分析保密。

`x` 是拼图块在原始 320×160 图像中的左边坐标，范围 0–276，容差 ±4 像素。缩放显示时应换算到原始坐标；`pieceY` 是公开值。挑战有效 120 秒，最多 5 次错误猜测；验证成功后凭证从服务端签发时起有效 60 秒。格式错误不扣拼图尝试次数，但计入验证码校验限流。

常见错误代码包括 `init_required`、`rate_limited`、`invalid_position`、`invalid_challenge`、`expired`、`already_verified`、`incorrect`、`attempts_exhausted`、`invalid_token`、`rate_limit_unavailable`。具体后端还可能返回通用 `unavailable`。Django 中间件的 CSRF 拒绝可以是 HTML 403，客户端已做非 JSON 失败处理。

## GCRA 限流语义

Django 默认每分钟补充速率与突发容量：

| 配额 | 容量与速率 N |
|---|---:|
| `issue_session` | 20 |
| `issue_ip` | 60 |
| `verify_session` | 60 |
| `verify_ip` | 120 |

通过 `NOVA_SLIDER_RATE_LIMITS` 覆盖上述键，值必须是 1–60000 的整数。桶键由动作、范围和哈希后的主体组成，不包含分钟编号。`demo` 与 `login` 共享相同动作的额度，切换用途或新建 session 不能绕过既定的 IP 配额；验证凭证本身仍单独绑定 session 和用途。

算法每次使用整数微秒与 `ceil(60,000,000/N)` 的补充间隔，原子条件更新数据库中的理论到达时间。以 N=20 为例，满桶允许一次性最多 20 次，此后约每 3 秒补充一次；不会在 59.999 秒和 60.001 秒之间同时恢复两个满桶。

这是“突发容量 + 持续速率”的令牌桶语义，**不是任意滑动 60 秒内绝对最多 N 次**。拒绝不会把已有债务不断延后。配额检查先扣 IP，再扣 session；后者拒绝时前者不退款，属于保守计费。`Retry-After` 与 JSON `retryAfter` 是当时状态下向上取整的等待秒数，其他并发请求仍可能先用掉新额度。

Django 使用可信部署链路提供的 `REMOTE_ADDR`，不会直接相信 `X-Forwarded-For`。IP 用服务端 HMAC 处理。Worker 示例沿用其原有阈值（出题 15/session、120/IP，校验 60/session、240/IP，初始化 40/IP），使用 Cloudflare 提供的边缘 IP，并在缺少该值时共用保守的 unknown 桶，不会跳过 IP 限流。代理配置错误可能让所有用户共用同一桶。

数据库条件更新是原子性边界，不使用进程内锁或依赖本地 cache。时钟回退不会清除未来债务；明显向前跳时或多主机时钟偏差会影响补充速度。部署方须保持可靠时钟；此实现不承诺跨独立数据库或任意分布式时钟的全局额度。数据库故障时拒绝放行并返回 503。

## 从 0.1.0 升级与回退边界

1. 备份数据库，先停止旧版验证码写入，避免新旧限流器并行提供额度。
2. 升级代码并执行 `python manage.py migrate`。新增 GCRA 状态表，保留原固定窗口表和挑战/凭证表。
3. 仍有效的旧桶会继承到新桶的 `blocked_until_us`，直到原冷却期结束；按原默认实现与正常时钟，可能短暂保守限流约 120 秒，不会因升级立即赠送一套新额度。
4. 再恢复服务，确认 429/503、日志与业务表单行为符合预期。

Django 迁移明确拒绝自动逆转，避免悄悄删除仍有效的限流债务。要回退旧代码，需要运维安排停写、等待至少原最长状态有效期并确认当前债务/冷却已清空，再采用经审查的人工数据库与代码回退流程。不要用 `--fake` 或直接删表冒充安全回滚。

Worker 示例先应用原 `schema.sql`（仅新建库）及 `migrations-0002-gcra.sql`（旧库只加新迁移）。它在首次访问稳定桶时惰性继承旧桶冷却期，schema 迁移中不塞入业务数据；同样要求停止旧写入、保留旧表，不声明无停机混合版本升级。

定期执行 `python manage.py prune_slider_captcha` 清理安全过期的挑战、旧桶和完全补充的 GCRA 状态。未清偿债务与未结束冷却期不能提前删除。清理和限流会并发运行，竞争失败必须保守拒绝，不能作为无状态放行依据。

可从每五分钟执行一次开始，例如在部署用户的 crontab 中配置（替换路径，并使用与服务一致的生产环境变量和数据库配置）：

```cron
*/5 * * * * cd /srv/myapp && /srv/myapp/.venv/bin/python manage.py prune_slider_captcha >> /var/log/myapp/captcha-prune.log 2>&1
```

按访问量、状态表增长和数据库清理耗时调整频率；避免调度重叠，确保日志可写并纳入监控。状态数量由 IP、session 和动作共同决定，一个 IP 可以产生大量 session，不能仅按 IP 数估计。清理频率不改变债务和冷却记录的保留条件。

`SECRET_KEY` 轮换会使已有挑战与未消费凭证失效，也会改变 IP/session 限流身份，可能产生新额度。本组件的自定义 `salted_hmac` 不尝试 `SECRET_KEY_FALLBACKS`。应协调所有实例的密钥切换、提示用户重新完成验证码，并在轮换窗口保留独立的入口/账号限流；旧状态仍按上述安全条件清理，不能为轮换直接清空限流表。

## 安全与无障碍边界

- 生产必须设置 HTTPS、安全的 session/CSRF Cookie、强密钥、可信 Host/代理和独立登录/账号限流，必要时配合 MFA。
- CSP 需允许同源脚本、样式和连接，以及 `img-src 'self' data:`；不能关闭 CSRF 或相信客户端的成功布尔值。
- 不记录原始凭证、session 绑定秘密、答案位置或鼠标轨迹；不要把挑战表暴露在普通管理后台。
- 拼图仅提供辅助防滥用成本，可能被图像匹配、视觉模型或人工解题绕过，不保证商业风控或生产抗滥用能力。
- 键盘可以调节和提交，但视觉拼图不等于盲人可独立使用。接入方须提供同等安全的非视觉替代流程并做用户测试，不能按屏幕阅读器检测、URL 参数或“无障碍跳过”按钮免验证。
- PostgreSQL/MySQL、生产压力、多主机代理部署、真机触控和辅助技术，仅在对应版本的验证报告确有记录时才视为已测。

## 验证与兼容

项目说明、诊断与验证报告集中存放在 [docs/ 文档目录](docs/README.md)。

安装声明仍与 Nova 一致：Python ≥3.10、Django ≥5.2.17 且 <6.2，图片依赖固定 Pillow 12.2.0。2026-10-26 增补 Python 3.10.20 / Django 5.2.17 本地实测，详情及本轮改进结果见 [本地自测记录](docs/2026-10-26-implementation.md)。此前精确七格 Python/Django 与三格 Node 结果见 [历史验证说明](docs/VERIFICATION.md)；历史 0.1.0 记录已移入 `verification/history-0.1.0/`，不能当作本轮重跑结果。

```sh
python manage.py check
python manage.py test tests --settings=tests.settings --noinput
python manage.py makemigrations --check --dry-run
npm ci --ignore-scripts
npm test
NOVA_PYTHON=python npm run test:dom
npm run test:worker
```

Node 只用于开发测试，Django 服务和原生前端不需要 Node 运行时。完整矩阵脚本要求显式提供精确运行时、Nova 源码路径及已构建 wheel；它不是适用于所有平台的一键 CI。

需要自行构建安装包时再执行 `python -m pip install build` 和 `python -m build`。[GitHub Actions 配置](.github/workflows/tests.yml) 在 push、pull request 和手动触发时检查 Django、迁移漂移、完整测试及组件/DOM/Worker 测试；本地新增配置不代表远端 CI 已运行或通过。DOM 测试默认只输出结果；如需保存新记录，设置 `NOVA_DOM_REPORT=/absolute/path/new-results.json`，避免覆盖历史日志。

代码使用 MIT 许可证，原始法律文本保留在 [LICENSE](LICENSE)，不翻译其法律条款。
