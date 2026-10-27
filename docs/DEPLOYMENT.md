# 可信代理、部署检查与清理监控

组件只使用 Django `request.META['REMOTE_ADDR']`，不会读取客户端传来的 X-Forwarded-For / X-Real-IP。加一个 HTTP 头本身不改变 WSGI environ 或 ASGI scope；必须由有明确信任边界的应用服务器负责转换。本轮未新增任意可信 header 开关或后台线程。

下面是两种可选部署，均假定 Nginx 是直接面向用户的唯一入口、同机运行应用、应用监听不向公网开放。域名、证书、用户/组、项目模块和路径必须换为宿主实际值；安装与服务管理由宿主完成，组件不捆绑这些服务器。

## ASGI：Nginx → Uvicorn → Django

```nginx
server {
    listen 443 ssl;
    server_name www.example.com;
    ssl_certificate /etc/ssl/myapp/fullchain.pem;
    ssl_certificate_key /etc/ssl/myapp/privkey.pem;

    location /static/ { alias /srv/myapp/static/; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        # 覆盖客户端输入；本例只有一个直接入口，不拼接客户端提供的链。
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```sh
# 在宿主虚拟环境、真实项目目录和生产环境变量下，由服务管理器运行。
uvicorn myproject.asgi:application --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips 127.0.0.1
```

负责转换的是 Uvicorn 的 proxy-headers 中间件：仅信任连接来源为 127.0.0.1 的代理，把已清洗的 X-Forwarded-For 写入 ASGI scope.client，把 Proto 写入 scheme；Django 再把 scope.client 地址写入 REMOTE_ADDR。本例的 X-Real-IP 只是兼容其他工具，验证码和 Django 不凭它自动取 IP。Uvicorn 参数契约见 [官方 settings](https://github.com/Kludex/uvicorn/blob/main/docs/settings.md)。

监听地址与防火墙必须阻止绕过代理直接访问后端，不能把 trusted IP 配成 `*`。容器里 Nginx 的连接地址通常不是 127.0.0.1，应改成已确认的固定代理地址/受控网络，并验证连接来源和入口头清洗。若前面还有 CDN/LB，本例 remote_addr 会是它的地址；需先按提供商公布的代理网段、头规范及防火墙设计可信解析，不能盲信任所有转发链。真实 NAT 用户仍会共用出口 IP，这与错误代理配置不同。

## WSGI：Nginx uWSGI 协议 → uWSGI → Django

HTTP 反代到任意 WSGI 服务器时，仅传 X-Real-IP 并不足够。本例改用 uWSGI 协议传 CGI 参数：

```nginx
server {
    listen 443 ssl;
    server_name www.example.com;
    ssl_certificate /etc/ssl/myapp/fullchain.pem;
    ssl_certificate_key /etc/ssl/myapp/privkey.pem;

    location /static/ { alias /srv/myapp/static/; }
    location / {
        # 检查宿主的该文件包含：uwsgi_param REMOTE_ADDR $remote_addr;
        include /etc/nginx/uwsgi_params;
        uwsgi_pass unix:/run/myapp/uwsgi.sock;
    }
}
```

```sh
uwsgi --master --processes 2 --module myproject.wsgi:application \
  --socket /run/myapp/uwsgi.sock --chmod-socket=660 --vacuum --die-on-term
```

Nginx 官方 [uwsgi_params](https://github.com/nginx/nginx/blob/master/conf/uwsgi_params) 包含 REMOTE_ADDR=$remote_addr；uWSGI 将该参数放进 WSGI environ，Django 保留它。请核对发行版实际文件，不重复声明相互冲突的参数。`/run/myapp` 及 socket 的属主/组需允许 Nginx 连接且阻止无关本地用户连接；不要暴露 uWSGI socket 到公网。完整网关说明见 [uWSGI 官方 Nginx 文档](https://uwsgi-docs.readthedocs.io/en/latest/Nginx.html)。

## Django 生产设置与验收

以下是边界示意，不能用示例开发 settings 代替生产配置：

```python
DEBUG = False
ALLOWED_HOSTS = ["www.example.com"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
# SECRET_KEY 由部署系统安全注入，保持所有实例一致。
```

上述 ASGI 示例由受信 Uvicorn 设置 scheme；上述 uWSGI 示例由 Nginx 参数传递 HTTPS。若实际栈另需 SECURE_PROXY_SSL_HEADER，必须保证代理先移除客户端伪造值并覆盖相应头，不能把它当作 REMOTE_ADDR 的配置。正确部署后，从真实入口验证 Django scheme/host 为外部 HTTPS/域名，并用两个受控客户端确认 REMOTE_ADDR 不是统一代理地址；伪造 X-Real-IP / X-Forwarded-For 不应改变判定。诊断信息只在受限的部署检查中查看，不创建公开的 IP 回显接口，不将原始 IP 写入验证码日志。

在实际生产环境变量和配置下运行：

```sh
python -m django check --settings=myproject.settings.production
python -m django check --deploy --fail-level WARNING --settings=myproject.settings.production
```

`--deploy` 启用 Django 自带的部署检查（如安全 Cookie、密钥、HSTS 等），依据 [Django 官方命令说明](https://docs.djangoproject.com/en/6.0/ref/django-admin/#check)。逐项处理适用于真实 HTTPS/代理配置的警告；例如 HSTS 的范围与预加载应由宿主评估，不能为了消除警告盲目启用。静态检查不证明代理链、调度、证书或线上业务真的正确。

## prune 调度与状态表监控

在 Django 前的可信入口按实际容量限制 `/captcha/init` 的全部流量（自定义挂载时替换路径），并保持正确客户端 IP 映射。应用内 `init_ip` 默认 40 的 GCRA 额度仅约束新绑定创建，已有有效绑定重复 init 豁免；入口限速也要覆盖这类请求。跨源、限流、配置/数据库失败的 init 不会由组件生成新绑定或 CSRF token；宿主其他中间件仍可能有自己的会话写入行为。

宿主 session 与验证码表分开维护。使用 Django 内置 db / cached_db / file 后端时，按宿主调度每天运行一次 `python -m django clearsessions`（同一生产配置），并监控执行结果和会话存储增长。验证码 prune 不清理宿主 session，过期数据库会话也不会自动删除。cache 后端依赖缓存过期，signed_cookies 不创建服务端会话表；自定义后端按其自己的清理契约执行。

从每五分钟一次开始，在宿主的服务管理器、cron 或现有任务调度中运行同一生产配置的 `python -m django prune_slider_captcha`。不增加组件后台线程，也不在请求中隐式启动调度。

可由 systemd oneshot 记录成功与失败，并用 timer 防止同一个服务重叠执行：

```ini
# /etc/systemd/system/myapp-captcha-prune.service
[Unit]
Description=Prune expired CAPTCHA state
[Service]
Type=oneshot
User=myapp
WorkingDirectory=/srv/myapp
Environment=DJANGO_SETTINGS_MODULE=myproject.settings.production
EnvironmentFile=/etc/myapp/runtime.env
ExecStart=/srv/myapp/.venv/bin/python -m django prune_slider_captcha

# /etc/systemd/system/myapp-captcha-prune.timer
[Unit]
Description=Periodic CAPTCHA cleanup
[Timer]
OnBootSec=5min
OnCalendar=*-*-* *:00/5:00
Persistent=true
[Install]
WantedBy=timers.target
```

由运维安装并启用 timer；本次没有操作宿主调度。监控 service 最近完成时间、exit code、运行时长和 stdout 的删除数量。建议连续两到三个计划周期无成功（例如 15 分钟）、持续失败或耗时接近调度间隔时告警，而不是只监控 timer 处于 active。查看 journal/调度平台执行记录，不将“本次删除 0 行”误判为未执行。

用数据库已有监控采集 Challenge、RateLimitState、旧 RateBucket 的行数/存储量及增长速率，结合入口流量、prune 成功、删除数量和查询耗时判断异常；session 数量增长可能让同一 IP 产生大量状态行。设置与容量相符的持续增长告警，不能看到表大就 TRUNCATE 或清空额度。活跃凭证、未还清债务和旧桶冷却必须按既定保留条件清理。静态 Django check 无法证明任务按时执行；部署方需维护上述成功心跳和表增长监控。
