# Nova Slider CAPTCHA 0.3.0（待发布）

可自行部署、方便接入 Django 的拼图滑块验证码。提供可安装的 Django app、原生 JavaScript Web Component、模板与 Django Admin 示例，以及可选的 Worker/D1 API 示例。适配 Nova Admin Theme 0.6.0，不修改 Django 或 Nova 的全局行为。

[公开交互演示](https://nova-slider-captcha.mingyueshi.chatgpt.site)使用 Worker + D1 服务端；本仓库根目录是 Django 组件。`examples/worker-api/` 保留演示的 API 逻辑、数据库 schema 和最小入口，托管演示的 React 展示页面、Sites 脚手架、部署绑定和运行数据不在仓库中。克隆代码不会复制线上服务。详见 [源码范围](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/SOURCE_PROVENANCE.md)。

## 0.3.0 的变化（待发布）

当前源码为首次 PyPI 发布准备，**尚未上传 PyPI**。新增公开配置/API 与迁移，因此从 0.2.0 进入 0.3.0；本地构建和验证不代表远端 CI 或线上发布完成。

- 自定义 purpose、request-aware Form/ModelForm、前缀与 formset 字段、结构化业务日志
- 有界的挑战 TTL / 尝试次数 / 容差设置；每个挑战持久化签发时策略，旧挑战保留原 5/4
- 响应几何驱动；独立嵌入的暗色兜底、显式主题优先级与状态文字对比度修复
- 明确的 Python/Django 配对 CI，构建 wheel/sdist 并运行安装包测试
- 首次 Trusted Publishing 发布流程准备，版本/tag 检查后复用同一已验证构建物

完整变化见 [CHANGELOG](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/CHANGELOG.md)，发布维护步骤见 [发布准备说明](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/RELEASING.md)。从 0.2.0 升级时执行迁移 0003；从 0.1.0 升级还需阅读下方的限流升级边界，不能并行运行新旧限流代码。

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

打开 `/captcha-demo/` 体验显式启用的演示，或 `/admin/login/` 测试 Admin 登录。示例默认 `LANGUAGE_CODE='zh-hans'`，只绑定本机主机名，含明确标记的开发用密钥，不能直接用作生产配置。生产环境需要自己的密钥、允许的主机、HTTPS、Cookie、安全代理设置和静态资源部署。

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

默认 URLConf 只有核心 API，`/captcha/` 返回简短 JSON 服务信息，不再提供演示页或消费接口。仅在开发/明确需要演示时显式挂载：

```python
path("captcha-demo/", include("nova_slider_captcha.demo_urls")),
```

演示页位于 `/captcha-demo/`，消费位于 `/captcha-demo/submit`（另保留该可选挂载下的 `demo` 别名）。本仓库开发示例已经显式启用。生产只挂核心 API 即可；demo 消费始终固定 purpose="demo"，不会保护任何真实业务操作。

**接入迁移**：原 `nova_slider_captcha:demo` 改为 `nova_slider_captcha:api-root`，原 `/captcha/submit` 和 `/captcha/demo` 不再由核心 URLConf 提供。引用旧演示名称/路径的模板和脚本须改为上述显式演示挂载；演示脚本从 form.action 获取消费地址，与核心 endpoint 分离。init / challenge / verify 的 URL、JSON、CSRF 和会话协议保持不变，独立 `<nova-slider endpoint="/captcha/">` 继续调用核心 API。

Widget 默认反解 `nova_slider_captcha:api-root`；URL 的挂载路径和 Django script prefix 会保留。多实例或嵌套 namespace 时显式选择完整根名称，避免依赖 Django 对同名实例的默认选择：

```python
from nova_slider_captcha.forms import SliderCaptchaWidget

# urlpatterns：path("public-proof/", include("nova_slider_captcha.urls", namespace="public_captcha"))
proof_widget = SliderCaptchaWidget(api_root="public_captcha:api-root", purpose="contact")
# 如果外层还有 portal namespace：api_root="portal:public_captcha:api-root"
```

可选演示挂在另一个 namespace 时，其 submit 自动反解当前演示 namespace；若同时使用自定义 API namespace，可自行组合演示路由并为 views.demo 传可信的 api_root URL kwarg（见下面的维护文档）。

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

具体的 Nginx→Uvicorn ASGI、Nginx→uWSGI WSGI、生产检查和清理监控示例见 [可信代理部署说明](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/DEPLOYMENT.md)。代理传入 `X-Real-IP` 本身不会自动改变 REMOTE_ADDR；须由受信的应用服务器/协议参数完成映射。

例如页面位于 `https://www.example.com/` 时，将浏览器可见的 `https://www.example.com/captcha/` 反代到 Django，并让组件使用 `endpoint="/captcha/"`。前端和验证码接口需要相同的 scheme、Host 和端口；`api.example.com` 仍是不同 origin。`same-site` 请求也被拒绝，增加 `CSRF_TRUSTED_ORIGINS` 不会放开这项约束。

代理应保留外部 Host，向 Django 准确传递外部 HTTPS scheme，并正确配置 `ALLOWED_HOSTS`；仅在入口代理会移除客户端伪造头并重新设置时，才配置 `SECURE_PROXY_SSL_HEADER` / `USE_X_FORWARDED_HOST`。保证 session/CSRF Cookie 的域、路径覆盖页面与验证码接口，并在生产启用 Secure；代理不得缓存验证码响应或丢弃 `Set-Cookie`。可信代理还需正确提供客户端 `REMOTE_ADDR`，本组件不会直接读取 `X-Forwarded-For`。不要通过关闭 CSRF 或宽泛信任客户端转发头解决代理错误。

组件内部自带一个默认名为 `nova_slider_token` 的隐藏表单字段；可用 `field-name="proof"` 修改。Django Widget 会使用对应字段的完整名字（含 Form prefix / formset 前缀），多个组件应各用一个字段名。不要在外面重复渲染同名字段。成功事件 `verified` 的 `event.detail` 为 `{token, expiresIn}`；凭证失效或刷新时发出 `captcha-reset`，状态变化发出 `captcha-state`。只在相关表单内临时保留凭证，不放入 URL、日志或持久浏览器存储。

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

## 自定义 purpose

Django 默认允许 `demo`、`login`。宿主设置 `NOVA_SLIDER_PURPOSES` 后会**替换整个集合**；要保留默认用途，请在配置中显式列出：

```python
# settings.py（Django app；Worker 示例仍使用其独立协议）
NOVA_SLIDER_PURPOSES = ["demo", "login", "contact", "profile_update"]
```

仅接受非空的 list、tuple、set 或 frozenset，不能用字符串或字典代替。名称遵循 `[a-z][a-z0-9_:-]{0,31}`，首位为小写英文字母，后续可用小写字母、数字、下划线、冒号和连字符，总长不超过数据库的 32 字符。非法配置会产生系统检查 `E004`，HTTP 接口返回 `503 configuration_invalid`，出题服务抛出 `ValueError`，消费拒绝放行。每次调用读取当前配置，支持 `override_settings`；移除某个用途后，其未完成挑战和未消费凭证也会被拒绝。

前端 `purpose="contact"` 只选择题目绑定用途。业务服务端必须固定 `purpose="contact"`，不能直接使用 POST 中的 purpose 决定受保护操作。可选演示的 `/captcha-demo/submit` 始终只消费 `demo`，不能用它消费自定义用途。所有用途共享对应 action 的 IP/session 额度，增加或切换 purpose 不会获得新额度。

## 挑战策略配置

默认行为仍为 120 秒、最多 5 次尝试、±4 原图像素容差。可在宿主 settings.py 中配置：

```python
NOVA_SLIDER_CHALLENGE_TTL = 120  # 30–600 秒
NOVA_SLIDER_MAX_ATTEMPTS = 5     # 1–20 次（成功验证也计一次）
NOVA_SLIDER_TOLERANCE = 4        # 0–10 原图像素，0 为精确匹配
```

仅接受范围内的整数，拒绝 bool、字符串、浮点数、负值和超限值。系统检查错误 `E006` 会阻止正常启动检查；运行时 HTTP API 返回 `503 configuration_invalid`，直接 issue/verify 抛 ValueError，consume 拒绝放行。配置每次动态读取，支持 `override_settings`；错误配置修复前不会重新解释或扩大已有挑战策略。

签发时，TTL 写入 `expires_at`，尝试上限和容差写入 Challenge 的 `max_attempts` / `tolerance` 快照。之后更改配置只影响新挑战，旧挑战继续按原策略校验，既不扩大也不缩小额度。迁移 `0003_challenge_policy` 将所有已有行填为原 5/4，不重置 attempts、过期时间或凭证状态。不要通过旧代码与新代码混跑来绕过快照；升级前停止旧写入，再迁移和恢复。回退删除快照字段会丢失在途策略，应先停写并排空在途挑战/凭证，再采用经审查的回退流程。

配置能力不代表更强安全性。更长 TTL、更大次数或容差可能改善完成率，也增加猜测或自动解题的机会；按实际用户、入口限流与风险要求选择。TOKEN_TTL 仍固定 60 秒，不提供设置；图片固定 320×160 / 44，本轮不开放尺寸设置。prune 按已持久化 expires_at 清理，并保留足够覆盖固定 60 秒凭证的时间。

## 通用 Form 与 ModelForm

使用 `SliderCaptchaField` 和放在最左边的 `SliderCaptchaFormMixin`，在初始化时传入 `request=`。字段名可自由选择；Widget 的 `purpose`、完整隐藏字段名和资源由字段提供。只使用 Field 而遗漏 Mixin 会拒绝验证。字段必须保持 `required=True`、`disabled=False`；不支持的值在构造时抛出明确 ValueError，字段实例之后被改写仍会在运行时拒绝。

Widget 将 Django 提供的 `aria-describedby` 和 `aria-invalid` 同步到可聚焦滑块，帮助文字、字段错误与组件键盘说明共同关联；动态更新或移除这两个属性也会同步。自定义表单模板仍须渲染被引用的帮助/错误元素。这不改变视觉拼图需要安全非视觉替代流程的边界。

普通 Form 示例（放进已有 Django app）：

```python
# forms.py
from django import forms
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin

class ContactForm(SliderCaptchaFormMixin, forms.Form):
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea)
    proof = SliderCaptchaField(purpose="contact")

# views.py
from django.http import HttpResponse
from django.shortcuts import render
from .forms import ContactForm

def contact(request):
    form = ContactForm(request.POST if request.method == "POST" else None,
                       request=request, prefix="contact")
    if request.method == "POST" and form.is_valid():
        # 凭证已消费；在这里执行业务操作，不能再调用 consume()。
        return HttpResponse("Accepted")
    return render(request, "protected_form.html", {"form": form})

# urls.py（项目仍需挂载 nova_slider_captcha.urls）
from django.urls import path
from .views import contact
urlpatterns = [path("contact/", contact, name="contact")]
```

ModelForm 示例复用 Django 用户模型，不需要新模型迁移；认证与授权仍由业务视图负责：

```python
# forms.py
from django import forms
from django.contrib.auth import get_user_model
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin

class ProfileForm(SliderCaptchaFormMixin, forms.ModelForm):
    proof = SliderCaptchaField(purpose="profile_update")

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]

# views.py
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from .forms import ProfileForm

@login_required
def profile(request):
    form = ProfileForm(request.POST if request.method == "POST" else None,
                       instance=request.user, request=request)
    if request.method == "POST" and form.is_valid():
        form.save()
        return HttpResponse("Saved")
    return render(request, "protected_form.html", {"form": form})

# urls.py
from django.urls import path
from .views import profile
urlpatterns = [path("profile/", profile, name="profile")]
```

两个示例均使用以下模板，并使用上方包含 `contact`、`profile_update` 的用途配置。自定义用户模型若没有所列字段，按模型实际字段修改 ProfileForm。

```django
{# templates/protected_form.html #}
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Protected form</title>{{ form.media }}</head>
<body>
<form method="post">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Submit</button>
</form>
</body>
</html>
```

消费发生在 Django 的字段校验、`Form.clean()`、ModelForm 的模型校验（含唯一性与约束）全部通过之后。其他字段/模型失败时，凭证仍可用于新建表单重试；缺 request 或会话绑定则拒绝。一个有效表单中的多个验证码字段会在 Challenge 写数据库的同一事务内消费，任一凭证失败全部回滚；每个字段需要独立匹配的凭证。不要在 `clean()` 或模型校验中执行受保护业务写入，因为它们先于消费。

同一实例重复调用 `is_valid()`、读取 `errors` 或 `full_clean()`，只消费一次。成功实例绑定原 token、request 对象、会话绑定和各字段 purpose；更换其中任一项或禁用该 purpose 会使其失效，请新建表单实例。表单通过后仅执行一次业务操作；表单不是业务幂等锁。`save()` 或后续业务失败时默认凭证已用，需要重新验证；若外层事务回滚了消费，必须丢弃该表单实例，不能跨回滚复用缓存成功结果。跨数据库业务写入也不受此局部事务保护。

Formset 可通过 `FormSet(..., form_kwargs={"request": request})` 传 request，并正常渲染 `management_form` 和每个子表单；隐藏字段会使用 `form-0-proof` 等完整名字，未填写的 extra 表单不会消费或产生验证码错误。**消费边界是单个子表单**：已有效子表单可能先消费，而另一个子表单或 formset 的 `clean()` 随后失败；本组件不提供整个 formset 的延后消费/事务保证。可按业务需求选择外层同库事务并在失败后回滚、丢弃所有表单实例，或为 formset 设计独立的可信提交流程。独立表单不要设置 `empty_permitted=True` 来绕过必填校验。

Admin 继续使用下文的 `SliderAdminAuthenticationForm`，不组合这个 Mixin：Admin 必须先消费验证码，再进入密码认证，密码错误也会消费。

## 前端国际化与自定义文案

不指定 `locale` 时仍使用中文。显式指定英语：

```html
<nova-slider endpoint="/captcha/" purpose="demo" locale="en"></nova-slider>
```

仅有 `zh-CN` 和 `en` 两个实际字典。未指定、空白、非字符串属性输入及格式非法值仍使用简中默认；组件不会自动读取浏览器或 document.lang 来更换默认语言。主标记为 `zh` 的系列（包括 zh-Hans、zh-Hant、zh-TW）统一简中，`en` 系列统一英文。显式、格式有效但不支持的语言（如 fr/fr-FR、ja/ja-JP、de、ar）现在回退英文，避免法语/日语站点因缺字典显示中文。没有新增繁体或其他语言包，也不声明 RTL 布局支持。

接受的轻量标记格式为：trim 后主标记2–8个ASCII字母，后续可用单个 `-` 或 `_` 分隔1–8个ASCII字母/数字的子标记；不区分大小写。不查询语言注册表，也不承诺完整BCP47、私用或祖父标记校验。HTML属性本身是字符串；非字符串兼容规则针对 JavaScript locale / setLocale 输入。Django Widget 继续传当前Django语言或显式attrs.locale，由同一个前端规则归一化，不另建Python语言映射。

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
- `POST /captcha/challenge`，请求 `{purpose:"demo"}`（或配置允许的其他用途），返回 `{challengeId,background,piece,width:320,height:160,pieceWidth:44,pieceY,expiresIn:120,maxAttempts:5}`
- `POST /captcha/verify`，请求 `{challengeId,x}`，成功返回 `{ok:true,token,expiresIn:60}`；失败返回 `{ok:false,code,...}`
- 核心 `GET /captcha/` 是命名 `api-root` 的 JSON 根路径，无演示消费
- 仅显式启用 demo_urls 后：`GET /captcha-demo/` 为演示页；`POST /captcha-demo/submit` 请求 `{token,purpose:"demo"}`，只消费 demo 凭证，`/captcha-demo/demo` 为别名

图片为扁平 PNG data URL，不包含数字答案、图片种子或可直接读取缺口位置的向量结构。人和程序仍可以从图像像素推断位置，因此不声称答案能对视觉分析保密。

`x` 是拼图块在原始图像中的左边坐标；默认 320×160、拼图块 44，范围 0–276，容差 ±4 像素。组件根据响应的 `width`、`height`、`pieceWidth` 计算范围、移动比例、ARIA 和图片宽高比，拒绝非数、零值或越界几何。交互手柄的 48px 由 CSS `--nsc-handle-size` 统一控制，与拼图尺寸独立。本轮未开放后端图片尺寸配置。缩放显示时应换算到原始坐标；`pieceY` 是公开值。挑战有效 120 秒，最多 5 次错误猜测；验证成功后凭证从服务端签发时起有效 60 秒。前述挑战 TTL、次数及容差为默认值，可在上方范围内配置，签发后按快照执行。格式错误不扣拼图尝试次数，但计入验证码校验限流。

常见错误代码包括 `init_required`、`rate_limited`、`invalid_position`、`invalid_challenge`、`expired`、`already_verified`、`incorrect`、`attempts_exhausted`、`invalid_token`、`rate_limit_unavailable`。具体后端还可能返回通用 `unavailable`。Django 中间件的 CSRF 拒绝可以是 HTML 403，客户端已做非 JSON 失败处理。

## GCRA 限流语义

Django 默认每分钟补充速率与突发容量：

| 配额 | 容量与速率 N |
|---|---:|
| `issue_session` | 20 |
| `issue_ip` | 60 |
| `verify_session` | 60 |
| `verify_ip` | 120 |

通过 `NOVA_SLIDER_RATE_LIMITS` 覆盖上述键，值必须是 1–60000 的整数。桶键由动作、范围和哈希后的主体组成，不包含分钟编号。所有允许的 purpose（包括 `demo` 与 `login`）共享相同动作的额度，切换用途或新建 session 不能绕过既定的 IP 配额；验证凭证本身仍单独绑定 session 和用途。

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

`RateBucket` 仅用于旧版升级与安全清理，不再承载当前限流请求；未来删除必须另做迁移，本轮保留表且不承诺删除日期。

定期执行 `python manage.py prune_slider_captcha` 清理安全过期的挑战、旧桶和完全补充的 GCRA 状态。未清偿债务与未结束冷却期不能提前删除。清理和限流会并发运行，竞争失败必须保守拒绝，不能作为无状态放行依据。

可从每五分钟执行一次开始，例如在部署用户的 crontab 中配置（替换路径，并使用与服务一致的生产环境变量和数据库配置）：

```cron
*/5 * * * * cd /srv/myapp && /srv/myapp/.venv/bin/python manage.py prune_slider_captcha >> /var/log/myapp/captcha-prune.log 2>&1
```

按访问量、状态表增长和数据库清理耗时调整频率；避免调度重叠，确保日志可写并纳入监控。状态数量由 IP、session 和动作共同决定，一个 IP 可以产生大量 session，不能仅按 IP 数估计。清理频率不改变债务和冷却记录的保留条件。

`SECRET_KEY` 轮换会使已有挑战与未消费凭证失效，也会改变 IP/session 限流身份，可能产生新额度。本组件的自定义 `salted_hmac` 不尝试 `SECRET_KEY_FALLBACKS`。应协调所有实例的密钥切换、提示用户重新完成验证码，并在轮换窗口保留独立的入口/账号限流；旧状态仍按上述安全条件清理，不能为轮换直接清空限流表。

## 宿主安全替代入口

视觉拼图不是非视觉验证。宿主有独立、受保护的替代流程时，可为所有 Django Widget（含 Admin）配置始终可见的导航链接：

```python
# settings.py：仅在宿主确实已实现该路由后设置。
NOVA_SLIDER_ALTERNATIVE_URL = "/security/verification-options/"
NOVA_SLIDER_ALTERNATIVE_LABEL = "使用其他安全验证方式"
```

不配置时不会显示链接，也不宣称已经存在替代服务。现有 noscript 提示保留；配置的链接放在组件之外，JS 开启、刷新重绘或关闭时都可见。

普通表单可按 Widget 单独设置，覆盖全局入口：

```python
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaWidget

proof = SliderCaptchaField(
    purpose="contact",
    widget=SliderCaptchaWidget(
        purpose="contact", api_root="nova_slider_captcha:api-root",
        alternative_url="/contact/secure-alternative/",
        alternative_label="联系表单的其他安全验证方式",
    ),
)
```

Admin 通常使用上方 settings 配置即可；需要只对某个 AdminSite 定制时，沿用原认证顺序并仅换 Widget：

```python
from nova_slider_captcha.forms import SliderAdminAuthenticationForm, SliderCaptchaWidget

class SiteLoginForm(SliderAdminAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nova_slider_token"].widget = SliderCaptchaWidget(
            purpose="login", alternative_url="/security/admin-verification/",
            alternative_label="管理员的其他安全验证方式",
        )

admin_site.login_form = SiteLoginForm
```

URL 与标签均由可信宿主代码提供，不读取客户端参数或 HTML attrs。只允许原始值以单个 `/` 开头的本地绝对路径，不接受 scheme、外站、协议相对地址、编码的双斜杠/反斜杠、空白或控制字符；同时校验解码值。URL 最长 2048，标签必须为 1–200 个可打印字符，并始终转义（即使传 SafeString）。非法全局配置仍产生 E007，直接调用配置验证器仍抛 ValueError；Widget 渲染仅对这个可选全局链接降级为不显示，不让普通表单/Admin 页面因此500。合法配置动态恢复立即生效；显式合法 Widget 链接不读非法全局设置，显式非法参数仍在构造时抛 ValueError。标签和 URL 必须同时配置。验证码字段/服务的安全配置校验与拒绝行为不变。

全局可选链接降级会记录固定 WARNING 事件 `optional_link / configuration_invalid`；不记录 URL、标签或异常文本。每个进程只保留一个时间戳，最多每300秒一次（多worker/重启各自计时），不会缓存链接验证结果；日志处理器失败不影响页面。E007 仍用于部署检查，降级并非把错误设置当作正确配置。

这个链接只导航，不生成凭证、不跳过原验证，也不内置短信、邮件或音频服务。宿主替代页面及其提交接口仍须自行实施身份核验、授权、CSRF、限流、一次性证明与同等保护；不能把目的 URL 直接指向已免验证的业务操作。现有语言字典、默认语言和回退没有改动，链接标签由宿主明确选择。

## 主题与窄容器

组件优先使用宿主语义变量（如 `--link-fg`、`--body-quiet-color`、`--error-fg`）及已有面板变量；没有宿主变量时提供独立明/暗色兜底。`html[data-theme="light"|"dark"]` 和 Nova 显式 mode 类优先于操作系统偏好；未指定或 auto 时跟随 `prefers-color-scheme`。宿主仍可在组件上覆盖 `--nsc-*`，例如 `--nsc-accent`、`--nsc-success`、`--nsc-error`、`--nsc-panel` 和 `--nsc-handle-size`。组件外的替代链接可通过 `--nsc-alternative-fg` 覆盖颜色。

成功文案采用独立语义色及不透明深色背景，避免装饰 mint 色或透明图像背景导致低对比度。自定义颜色需要重新检查文字与实际背景的对比度。布局继续使用换行与流式尺寸；窄容器减少轨道文案横向留白，长文案允许换行。组件没有装饰性动画，不为无效果的 reduced-motion 查询增加额外规则。

## 基础业务日志

Django app 使用命名 logger `nova_slider_captcha`；不添加第三方依赖。所有记录的消息固定为 `CAPTCHA business event`，排障数据位于 `extra` 字段 `captcha_event`、`captcha_reason`、`captcha_status`、`captcha_purpose`、`captcha_action`。purpose 只记录已配置允许的名字，其他情况为 `unknown`。机器原因码包括 `database_unavailable`、`configuration_invalid`、`invalid_proof`、`binding_missing`、`proof_rejected`、`rate_limited`；`proof_rejected` 不区分过期、重放、用途或会话不匹配，避免泄露凭证状态。

503/数据库消费错误使用 ERROR，消费拒绝使用 WARNING，429 默认 DEBUG。用 `NOVA_SLIDER_RATE_LOG_LEVEL = "WARNING"` 可提升 429 级别，或设 `"OFF"` 关闭该事件；允许 DEBUG、INFO、WARNING、ERROR、CRITICAL、OFF（非法值产生检查 `E005`）。成功事件默认不输出。示例宿主设置：

```python
NOVA_SLIDER_RATE_LOG_LEVEL = "DEBUG"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "captcha": {
            "format": "%(levelname)s %(name)s event=%(captcha_event)s reason=%(captcha_reason)s status=%(captcha_status)s purpose=%(captcha_purpose)s action=%(captcha_action)s",
        },
    },
    "handlers": {
        "captcha_console": {
            "class": "logging.StreamHandler",
            "level": "WARNING",
            "formatter": "captcha",
        },
    },
    "loggers": {
        "nova_slider_captcha": {
            "handlers": ["captcha_console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
```

此 formatter 只绑定验证码 logger，其他 Django 日志不一定带这些 extra 字段。日志不包含 token、session 秘密、答案、原始请求体、异常文本、IP 或任意客户端字符串；宿主自行配置的中间件/APM 也应避免采集这些内容。日志处理器异常不会改变限流或单次消费的判定。429 级别仅控制本组件业务事件，Django 自身的 HTTP 请求日志仍由宿主另行配置。该日志功能仅针对 Django app，未改线上 Worker。

## 安全与无障碍边界

- 生产必须设置 HTTPS、安全的 session/CSRF Cookie、强密钥、可信 Host/代理和独立登录/账号限流，必要时配合 MFA。
- CSP 需允许同源脚本、样式和连接，以及 `img-src 'self' data:`；不能关闭 CSRF 或相信客户端的成功布尔值。
- 不记录原始凭证、session 绑定秘密、答案位置或鼠标轨迹；不要把挑战表暴露在普通管理后台。
- 拼图仅提供辅助防滥用成本，可能被图像匹配、视觉模型或人工解题绕过，不保证商业风控或生产抗滥用能力。当前保留单一 mask；随机形状最多提高对固定模板的适配成本，不能阻止通用像素匹配或视觉识别，不作为发布前置条件。
- 键盘可以调节和提交，但视觉拼图不等于盲人可独立使用。接入方须提供同等安全的非视觉替代流程并做用户测试，不能按屏幕阅读器检测、URL 参数或“无障碍跳过”按钮免验证。
- PostgreSQL/MySQL、生产压力、多主机代理部署、真机触控和辅助技术，仅在对应版本的验证报告确有记录时才视为已测。

## 验证与兼容

项目说明、诊断与验证报告集中存放在 [docs/ 文档目录](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/README.md)。

安装声明仍与 Nova 一致：Python ≥3.10、Django ≥5.2.17 且 <6.2，图片依赖为经边界验证的 Pillow >=12.2,<13（本轮实测 12.2.0 与当前 12.x 最新 12.3.0，未开放 10/11/13）。2026-10-26 增补 Python 3.10.20 / Django 5.2.17 本地实测，此前改进结果见 [本地自测记录](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/2026-10-26-implementation.md)，通用接入本轮见 [接入实施自测](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/2026-10-26-integration-implementation.md)。此前精确七格 Python/Django 与三格 Node 结果见 [历史验证说明](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/VERIFICATION.md)；历史 0.1.0 记录已移入 `verification/history-0.1.0/`，不能当作本轮重跑结果。

```sh
python manage.py check
python manage.py test tests --settings=tests.settings --noinput
python manage.py makemigrations --check --dry-run
npm ci --ignore-scripts
npm test
NOVA_PYTHON=python npm run test:dom
npm run test:worker
```

基础静态检查使用独立的 `requirements-lint.txt`（Ruff 0.17.2，target Python3.10）。仅检查选定错误规则，不自动格式化，不接入mypy；源码、测试、脚本、Python示例和项目配置均在明确范围内，历史verification不扫描。规则、两处测试settings窄豁免、命令和正反验收见 [静态检查说明](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/STATIC_CHECKS.md)。

开发/CI 分支覆盖率使用独立的 `requirements-coverage.txt`（coverage.py 7.17.0），不增加运行依赖。稳定 coverage profile 为 Python 3.12 / Django 5.2.17 / Pillow 12.3.0，包含升级脚本子进程，不排除包内文件。门槛分别检查纯语句/纯分支：包整体97%/95%，forms.py 99%/97%；不把 coverage report 的组合百分比当成纯分支。CI 无论测试成功或失败都尝试生成并上传 HTML/JSON/XML 和原始覆盖率数据，测试失败不会被报告步骤掩盖。基线、命令、缺失分支和负向检查见 [覆盖率维护说明](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/COVERAGE.md)。

Node 只用于开发测试，Django 服务和原生前端不需要 Node 运行时。完整矩阵脚本要求显式提供精确运行时、Nova 源码路径及已构建 wheel；它不是适用于所有平台的一键 CI。

需要自行构建安装包时再执行 `python -m pip install build` 和 `python -m build`。[GitHub Actions 配置](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/.github/workflows/tests.yml) 使用 Python/Django/Pillow 六格代表性矩阵：3.10/5.2.17/12.2.0、3.11/5.2.17/12.3.0、3.12/5.2.17/12.3.0、3.12/6.1.2/12.2.0、3.13/6.1.2/12.3.0、3.14/6.0.9/12.3.0，分别验证 source 与同一构建 wheel，并检查 sdist、元数据、迁移漂移、完整测试及组件/DOM/Worker。runner 临时路径放在合法的 step.env 上下文。新增配置与本地通过不代表远端 CI 通过；此前发布准备见 [发布准备自测](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/2026-10-26-release-implementation.md)。当前接入改进见 [后续实施自测](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/docs/2026-10-26-followup-implementation.md)。DOM 测试默认只输出结果；如需保存新记录，设置 `NOVA_DOM_REPORT=/absolute/path/new-results.json`，避免覆盖历史日志。

代码使用 MIT 许可证，原始法律文本保留在 [LICENSE](https://github.com/mingyueshi/django-nova-slider-captcha/blob/main/LICENSE)，不翻译其法律条款。
