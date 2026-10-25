# Nova Slider CAPTCHA 诊断报告

> 2026-10-26 已完成源码与运行复核。下文第 1–5 节保留原分析；其中严重程度、错误示例和实施建议以第 6 节复核结论为准。实施后的独立验收记录见第 7 节。

- **项目版本**：0.2.0
- **分析日期**：2026-10-25
- **分析范围**：仓库源码（`src/`、`demo/`、`tests/`、`examples/worker-api/`）、文档与测试记录
- **性质**：只读分析，未修改任何代码

---

## 1. 总体评价

项目工程完成度很高，核心设计以 **条件 SQL UPDATE 作为原子性边界**，不依赖进程内锁或本地缓存。测试覆盖了并发竞争、精确微秒级限流、迁移回滚防护；文档对"未验证范围"（PostgreSQL/MySQL、生产负载、真机触控、辅助技术）做了诚实披露。

主要短板集中在三处：

1. **出图热路径的性能**（最突出，见缺陷 H-1）；
2. **前端对旧浏览器的兼容性降级**（M-1、M-2）；
3. **若干脆弱实现与死代码**（L 级）。

真正的代码层缺陷不多，大量"边界"是项目有意设计并已在文档声明，本文将其单列为第 4 节，避免与缺陷混淆。

---

## 2. 缺陷清单（按严重程度分级）

### H（High，建议优先处理）

#### H-1 出图热路径：逐像素 Python 循环 + 每像素调用 `SystemRandom`

`src/nova_slider_captcha/images.py` 的 `make_puzzle()` 在每次 `challenge` 请求时执行，是并发瓶颈：

- 320×160 = 51,200 次逐像素 Python 循环，每像素还含 `math.sin`、`zip` 解包、`max/min` 夹取。
- `rng = secrets.SystemRandom()`（`images.py:19`）的每次 `randrange` 都走 `os.urandom`，全图约 5 万+ 次系统随机数调用，开销远大于图像计算本身。

**建议**：

- 用 `random.Random(secrets.randbits(128))` 做一次性种子化的本地 PRNG（需求是"每张图不同"，而非密码学不可预测，安全性足够）。
- 或预生成一批背景纹理缓存复用（缺口坐标、拼图块仍每次随机）。
- 追求吞吐时可改用 numpy 向量化像素场。

#### H-2 限流每次请求多次往返数据库

`src/nova_slider_captcha/services.py` 的 `allow_request()`（`services.py:85-88`）对每个 scope 先 `get_or_create` 再 `filter().update()`，每次 challenge/verify 实际产生 2×(2~3) 次 SQL。

功能正确（依赖 Django `get_or_create` 的 IntegrityError 回退），但高 QPS 下开销可观。

**建议**：在 PostgreSQL/MySQL 上改用 `INSERT ... ON CONFLICT DO NOTHING` 后再执行条件 update，或将创建+扣减合并为单条原子 upsert，减少往返。SQLite 当前实现可保留。

---

### M（Medium，健壮性与兼容性）

#### M-1 前端 `Image.decode()` 无降级路径

`src/nova_slider_captcha/static/nova_slider_captcha/slider.js:315`

```js
await Promise.all([bg.decode(), piece.decode()]);
```

`HTMLImageElement.decode()` 在旧版 Safari / 部分 WebView 中不可用，一旦缺失会抛异常，整题直接进入 `error` 状态，而非回退到 `onload`。

**建议**：封装 `img.decode ? img.decode() : new Promise(res => { img.onload = res; img.onerror = res; })`。

#### M-2 严格同源拒绝了 `same-site`

`src/nova_slider_captcha/views.py:39`

```python
return request.headers.get("Sec-Fetch-Site") not in ("cross-site", "same-site")
```

跨子域同站（如 `www.example.com` 前端 + `api.example.com`）也会被 403 拒绝。这是有意设计（README 声明"跨域 CORS 未提供"），但对前后端分域部署的团队是硬约束，只能同源反代。

**建议**：在接入文档中更醒目地提示该约束，并说明同源反代配置要点。

#### M-3 `RateLimitState` 随 IP/session 累积，清理依赖外部调度

`prune_slider_captcha` 只删"完全补充且未阻塞"的行，需运维手动配 cron。高流量下 state 行数 ≈ 访问者 IP 数 × 4（issue/verify × ip/session），调度缺失会持续膨胀。

**建议**：文档给出推荐的 cron 示例与频率；确认清理频率与流量匹配。

---

### L（Low，可维护性与死代码）

#### L-1 `math.isfinite(x)` 是无效防御代码

`src/nova_slider_captcha/views.py:109`

```python
if type(x) not in (int, float) or not 0 <= x <= WIDTH - PIECE_SIZE or not math.isfinite(x):
```

`0 <= x <= 276` 已天然排除 `NaN`/`inf`（比较恒为 False），`not math.isfinite(x)` 永远为 False，属死代码。

**建议**：删除，或将 `isfinite` 提到范围判断之前才有实际意义。

#### L-2 token 长度硬编码 `43`

`src/nova_slider_captcha/services.py:137`

```python
if purpose not in PURPOSES or not isinstance(token, str) or len(token) != 43:
```

`43` 是 `secrets.token_urlsafe(32)` 的隐式产物。若调整 token 生成长度，此处极易被遗漏导致全线 token 失效。

**建议**：定义常量或改正则（如 `^[A-Za-z0-9_-]{43}$`）并集中管理。

#### L-3 Widget endpoint 用字符串切片反推

`src/nova_slider_captcha/forms.py:15`

```python
context["widget"]["endpoint"] = reverse("nova_slider_captcha:challenge").rsplit("challenge", 1)[0]
```

依赖路由名以 `"challenge"` 结尾。若重命名路由或路径前缀中意外包含 `challenge`，会切错。

**建议**：在 `urls.py` 显式定义一个指向根路径的 name（如 `name="root"`）供 `reverse` 使用，替代字符串裁剪。

#### L-4 依赖 `SECRET_KEY` 的派生哈希未提示轮换影响

`session_hash`、`token_hash` 都经 `salted_hmac`（`services.py:23-24`）派生，密钥轮换会让所有在途挑战/凭证瞬间失效（返回 `invalid_challenge`/`invalid_token`）。安全默认正确，但 README 未提示密钥轮换的可用性代价。

**建议**：在文档中补充一句密钥轮换对进行中验证码的影响说明。

---

## 3. 流程与工程化建议

1. **补充 CI workflow**：README 已声明"仓库没有 GitHub Actions workflow"。对测试矩阵如此完备的项目，补一个最小 CI（`manage.py test` + `npm test`）成本低、收益高，可消除"本地通过 ≠ 远端 CI 通过"的割裂。
2. **`prune` 调度文档化**：给出 cron 示例与推荐频率（结合 H-2/M-3 的数据生命周期）。
3. **补充 Python 3.10 实测**：`pyproject.toml` 声明 `>=3.10`，但验证矩阵从 3.11 起，3.10 仅作为安装边界、未实测（文档已诚实说明）。

---

## 4. 已声明的设计边界（非缺陷，仅作接入提醒）

项目在 README / VERIFICATION 中已主动披露以下边界，接入前需评估是否满足自身要求：

- **抗自动化能力有限**：缺口在背景图上被主动加深 + 高亮描边（`images.py:48-50`），模板匹配 / 计算机视觉可低成本定位。这是滑块验证码的固有定位，不应作为唯一风控手段。
- **未实测组合**：PostgreSQL/MySQL、生产负载、多主机代理部署、真机触控、屏幕阅读器/RTL 语言均未验证。
- **同源约束**：不提供跨域 CORS 接入，前后端分域需同源反向代理（对应 M-2）。
- **无障碍边界**：视觉拼图不等同于盲人可独立使用，接入方须提供同等安全的非视觉替代流程。

---

## 5. 附：本次分析涉及的主要文件

| 文件 | 关注点 |
|---|---|
| `src/nova_slider_captcha/images.py` | 出图热路径性能（H-1） |
| `src/nova_slider_captcha/services.py` | GCRA 限流、单次消费、token 长度（H-2、L-2、L-4） |
| `src/nova_slider_captcha/views.py` | 同源校验、位置校验死代码（M-2、L-1） |
| `src/nova_slider_captcha/forms.py` | endpoint 反推（L-3） |
| `src/nova_slider_captcha/static/nova_slider_captcha/slider.js` | 前端 Web Component、decode 降级（M-1） |
| `src/nova_slider_captcha/management/commands/prune_slider_captcha.py` | 清理策略（M-3） |
| `src/nova_slider_captcha/models.py` | 数据模型与索引 |
| `tests/*` | 测试覆盖评估 |
| `examples/worker-api/*` | Worker/D1 示例实现 |

---

*本报告由只读代码分析生成，未对仓库做任何修改。*

## 6. 主控复核结论（2026-10-26）

复核基线为 `main` / `33b92ec`，开始时仅本报告为未跟踪文件。原报告属于静态诊断，不能将其性能判断或旧验证文档作为本轮实际验证结果。本会话负责报告、主控与独立验收，新建 GPT 6.1 sol 会话负责具体实施。

### 实施前基线

在 macOS、Python 3.12.14 / Django 5.2.17 / Pillow 12.2.0、Node 24.21.0 上重新执行：

| 检查 | 结果 |
|---|---|
| Django 完整测试 | 61 项通过 |
| Web Component 测试 | 28 项通过 |
| Worker SQL 测试 | 25 项通过 |
| 缺失 Image.decode 的组件复现 | 进入 error，显示网络中断提示 |
| make_puzzle 预热后 15 次 | 中位数 129.02 ms，最小 123.48 ms，最大 256.41 ms |
| allow_request 首次创建两种 scope | 10 条 SQL，含两组 BEGIN/COMMIT |
| allow_request 已有两种 scope | 4 条 SQL，SELECT/UPDATE 各两次 |

SQL 计数使用隔离内存 SQLite；完整测试使用独立临时文件数据库。出图微基准不代表生产吞吐或并发容量。原版出图源码及原始测量保存在本机临时验收目录，最终记录应提供可重跑方法。

### 对原条目的修正与处置

| 编号 | 复核结论与实施要求 |
|---|---|
| H-1 | 确认出图热路径成本，优先优化；尚无证据证明是实际生产首要瓶颈。SystemRandom 的拒绝采样可能多次取随机位，“五万次系统调用”不是精确计数。仅背景装饰可使用每图独立安全种子的本地 PRNG；缺口位置、session 与凭证保留安全随机源。保持图像尺寸、遮罩与协议，不增加 numpy 或缓存体系。 |
| H-2 | 下调为性能改进。已有桶四条 SQL，首次十条（含事务），原计数不精确。可用 ORM 条件 UPDATE 作为已有桶快路径，未更新时再走创建/拒绝逻辑；保留 IP 先扣、拒绝不延债、冷却、清理竞争安全及失败关闭。缺少实测的 PostgreSQL/MySQL 专用 upsert 不纳入本轮，原报告将 ON CONFLICT 同时用于二者也不准确。 |
| M-1 | 确认功能问题。load/error 降级须在赋值 src 前安装监听，覆盖缓存图片、刷新、断开和迟到事件，并清理监听器。原示例 onerror=res 会把坏图当成功，禁止照搬；decode 拒绝与图片错误均保持失败。修复此点不等于支持所有旧浏览器，组件还有其他现代 JS API。 |
| M-2 | 既定安全边界，不放开 same-site。不同子域仍是不同 origin，组件也拒绝跨源 endpoint。补同源反代、Host/外部 HTTPS scheme、Cookie 与可信代理说明；CSRF_TRUSTED_ORIGINS 不会取消此约束。 |
| M-3 | 运维接入要求，补如每五分钟执行一次的清理调度示例，频率按流量和数据库耗时调整。状态规模取决于 IP、session 与动作，不能写成 IP 数×4；单 IP 可有大量 session。不得提前删除未清偿债务或冷却记录。 |
| L-1 | 确认冗余，可删除 isfinite 与 import。不要直接前移：巨大 Python 整数转浮点可能抛 OverflowError。保留严格类型和范围校验及异常输入测试。 |
| L-2 | 确认维护风险。随机字节数与编码长度集中定义，生成/消费共同使用；仍硬编码 43 的正则没有解决耦合。保持既有凭证长度和消费语义。 |
| L-3 | 维护耦合成立，原触发描述不正确。rsplit 使用最后一个匹配，前缀含 challenge 不会单独引发错误；依赖的是解析后的路径而非 URL name。根路径已有 name=demo，可复用 reverse，无需新增 HTTP 入口；覆盖挂载前缀与脚本前缀。 |
| L-4 | 文档缺口成立。自定义 salted_hmac 不尝试 SECRET_KEY_FALLBACKS；轮换既使在途挑战/凭证失效，也改变 IP/session 限流身份，可能产生新配额。补协调轮换和外部限流说明，旧记录继续遵循现有安全清理条件。 |

### 工程改进与验收范围

1. 增加最小 GitHub Actions：Django 检查、迁移漂移、完整测试，以及组件、DOM、Worker 测试。安装声明依赖并隔离各作业数据库；新增 workflow 不代表远端已执行。
2. 增补 Python 3.10 / Django 5.2 实测；本机有 Python 3.10.20。如依赖不兼容或安装失败，记录实际原因，不能把历史矩阵改成通过。
3. 新测试重点覆盖图片降级及竞争、路由根路径、token 常量、限流查询减少与失败/并发行为；复用已有安全测试。
4. 主控会话独立检查差异、复跑相关测试、前后微基准和 SQL 计数；实施会话自测不能替代验收。
5. 仅做本地改进，不提交、不推送、不发布、不部署，不操作线上 Worker 或业务数据。旧验证日志保留；新记录注明日期、平台、精确版本与未验证范围。

原有同源、CSRF、session/用途绑定、原子消费和数据库失败关闭约束保留。PostgreSQL/MySQL、生产压力、真机触控、屏幕阅读器与 RTL 不因本轮通过而成为已验证项。

## 7. 独立验收结果

2026-10-26：复核确定的本地改进已完成并通过主控独立验收，未发现遗留阻断项。具体实施由 GPT 6.1 sol 会话完成；本会话保留主控与独立验证职责。

- 出图中位耗时：129.14 → 68.57 ms，降低约 46.9%（同机交错 25 次微基准）。
- 已有桶接受请求：4 → 2 条 SQL；首次创建仍为 10 条，含事务控制。
- Python 3.10.20 与 3.12.14 源码测试各 71 项、隔离安装 wheel 后 71 项、组件 35 项、DOM 12 项、Worker 25 项均通过。
- 原版/新版 500 步 GCRA 独立轨迹的允许结果、Retry-After 和完整状态一致；既有并发测试通过。
- 真实 Chromium 验证了正常/缺失 decode、损坏图片、刷新后的旧图片事件及 390 像素布局。HTTP 使用本地模拟响应，不冒充 Django 页面完整浏览器测试或旧浏览器实机验证。
- 系统检查、迁移漂移、依赖检查与构建通过；wheel 的 27 个运行文件与最终源码一致。
- 已补 CI 配置、运维说明、Python 3.10 覆盖与回归测试；未提交、推送、发布或部署，远端 CI 尚未执行。

详细证据、重跑命令和未验证范围见[主控独立验收记录](2026-10-26-independent.md)；实施方记录另见[本地自测](2026-10-26-implementation.md)。旧验证日志未被覆盖。
