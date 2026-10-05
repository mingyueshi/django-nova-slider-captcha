/* NOVA Slider 0.1.0. Vanilla Web Component; no runtime framework dependency. */
(() => {
  const inits = new Map();
  const messages = {
    rate_limited: "操作有些频繁，请等一分钟再试。",
    session_expired: "会话已过期，请刷新验证。",
    csrf_failed: "安全校验失败，请刷新页面重试。",
    unavailable: "验证服务暂不可用，请稍后重试。",
    challenge_unavailable: "这张拼图已过期或已使用，请换一张。",
    init_required: "会话已更新，请换一张拼图。",
    expired: "拼图已过期，请换一张。",
    already_verified: "这张拼图已使用，请换一张。",
    attempts_exhausted: "尝试次数已用完，请换一张。",
  };
  async function init(endpoint) {
    if (!inits.has(endpoint))
      inits.set(
        endpoint,
        fetch(endpoint + "init", {
          credentials: "same-origin",
          cache: "no-store",
        })
          .then(async (r) => {
            if (!r.ok) throw Error("初始化失败");
            return (await r.json()).csrfToken;
          })
          .catch((e) => {
            inits.delete(endpoint);
            throw e;
          }),
      );
    return inits.get(endpoint);
  }
  class NovaSlider extends HTMLElement {
    connectedCallback() {
      if (this.live) return;
      this.live = true;
      this.seq = (this.seq || 0) + 1;
      this.x = 0;
      this.abortEvents = new AbortController();
      const url = new URL(
        this.getAttribute("endpoint") || "/captcha/",
        location.href,
      );
      if (url.origin !== location.origin) {
        this.textContent = "验证码接口必须与当前页面同源。";
        return;
      }
      this.endpoint = url.pathname.replace(/\/?$/, "/");
      this.purpose = this.getAttribute("purpose") || "demo";
      this.innerHTML = `<div class="nsc"><div class="nsc-image"><img class="nsc-background" alt="带有一处拼图缺口的山水图案" draggable="false"><img class="nsc-piece" alt="可移动拼图块" draggable="false"><div class="nsc-overlay">正在生成拼图…</div></div><div class="nsc-track"><div class="nsc-fill"></div><span class="nsc-track-text" aria-hidden="true">向右拖动滑块</span><input class="nsc-range" type="range" min="0" max="276" step="1" value="0" aria-label="移动拼图块" aria-describedby="nsc-instructions-${NovaSlider.id++}"><span class="nsc-handle" aria-hidden="true">→</span></div><div class="nsc-meta"><span class="nsc-status" role="status" aria-live="polite">正在连接验证服务…</span><button class="nsc-refresh" type="button" aria-label="换一张拼图"><span aria-hidden="true">↻</span> 换一张</button></div><p class="nsc-keyboard">可用方向键微调，Enter 提交；也支持触屏拖动。</p><input type="hidden" name="nova_slider_token" value=""></div>`;
      this.range = this.querySelector(".nsc-range");
      this.querySelector(".nsc-keyboard").id =
        this.range.getAttribute("aria-describedby");
      this.status = this.querySelector(".nsc-status");
      this.overlay = this.querySelector(".nsc-overlay");
      this.field = this.querySelector("input[type=hidden]");
      const on = (element, event, cb) =>
        element.addEventListener(event, cb, {
          signal: this.abortEvents.signal,
        });
      on(this.range, "input", () => this.move(Number(this.range.value)));
      on(this.range, "pointerdown", (e) => {
        this.dragging = true;
        this.range.setPointerCapture?.(e.pointerId);
      });
      on(this.range, "pointerup", () => {
        if (this.dragging) {
          this.dragging = false;
          this.verify();
        }
      });
      on(this.range, "pointercancel", () => {
        this.dragging = false;
      });
      on(this.range, "keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          this.verify();
        }
      });
      on(this.querySelector(".nsc-refresh"), "click", () => this.refresh());
      this.refresh();
    }
    disconnectedCallback() {
      this.live = false;
      this.seq++;
      clearTimeout(this.timer);
      this.request?.abort();
      this.abortEvents?.abort();
    }
    emit(name, detail = {}) {
      this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true }));
    }
    setState(state, message) {
      this.state = state;
      this.querySelector(".nsc").dataset.state = state;
      this.range.disabled = state !== "ready";
      this.status.textContent = message;
      this.overlay.hidden = ["ready", "checking"].includes(state);
      this.overlay.textContent =
        state === "success"
          ? "✓ 验证通过"
          : state === "loading"
            ? "正在生成拼图…"
            : message;
      this.emit("captcha-state", { state, message });
    }
    move(x) {
      this.x = Math.min(276, Math.max(0, x));
      this.range.value = this.x;
      const ratio = (this.x / 320) * 100;
      this.querySelector(".nsc-piece").style.left = ratio + "%";
      this.querySelector(".nsc-handle").style.left =
        `calc(${(this.x / 276) * 100}% - ${(this.x / 276) * 48}px)`;
      this.querySelector(".nsc-fill").style.width =
        `calc(${(this.x / 276) * 100}% + ${48 - (this.x / 276) * 48}px)`;
      this.range.setAttribute(
        "aria-valuetext",
        `${Math.round((this.x / 276) * 100)}%，按 Enter 校验`,
      );
    }
    async post(action, body, signal) {
      const csrfToken = await init(this.endpoint);
      const r = await fetch(this.endpoint + action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(body),
        signal,
      });
      if (r.status === 403) inits.delete(this.endpoint);
      const isJson = r.headers
        .get("content-type")
        ?.includes("application/json");
      if (!isJson)
        return {
          ok: false,
          code: r.status === 403 ? "csrf_failed" : "unavailable",
        };
      const data = await r.json();
      if (data.code === "init_required" || data.code === "session_expired")
        inits.delete(this.endpoint);
      return data;
    }
    async refresh() {
      const started = Date.now(),
        seq = ++this.seq;
      clearTimeout(this.timer);
      this.request?.abort();
      this.request = new AbortController();
      this.field.value = "";
      this.emit("captcha-reset");
      this.move(0);
      this.setState("loading", "正在生成新拼图…");
      try {
        const data = await this.post(
          "challenge",
          { purpose: this.purpose },
          this.request.signal,
        );
        if (seq !== this.seq) return;
        if (!data.challengeId)
          throw Error(messages[data.code] || "生成失败，请重试。");
        this.challenge = data;
        const bg = this.querySelector(".nsc-background"),
          piece = this.querySelector(".nsc-piece");
        bg.src = data.background;
        piece.src = data.piece;
        piece.style.width = (data.pieceWidth / data.width) * 100 + "%";
        piece.style.top = (data.pieceY / data.height) * 100 + "%";
        await Promise.all([bg.decode(), piece.decode()]);
        if (seq !== this.seq) return;
        this.setState("ready", "拖动拼图，对齐图中的缺口");
        this.timer = setTimeout(
          () => {
            if (seq !== this.seq) return;
            this.seq++;
            this.request?.abort();
            this.field.value = "";
            this.emit("captcha-reset");
            this.setState("expired", "拼图已过期，请换一张。");
          },
          Math.max(0, data.expiresIn * 1000 - (Date.now() - started)),
        );
      } catch (e) {
        if (seq !== this.seq || e.name === "AbortError") return;
        this.setState("error", e.message || "连接失败，请重试。");
      }
    }
    async verify() {
      if (this.state !== "ready") return;
      const started = Date.now(),
        seq = this.seq;
      this.setState("checking", "正在由服务端校验…");
      try {
        const data = await this.post(
          "verify",
          { challengeId: this.challenge.challengeId, x: this.x },
          this.request.signal,
        );
        if (seq !== this.seq) return;
        if (data.ok) {
          clearTimeout(this.timer);
          const remaining = Math.max(
            0,
            data.expiresIn * 1000 - (Date.now() - started),
          );
          if (!remaining) {
            this.field.value = "";
            this.emit("captcha-reset");
            this.setState("expired", "凭证已过期，请重新验证。");
            return;
          }
          this.field.value = data.token;
          this.setState("success", "验证通过，有效期 60 秒");
          this.emit("verified", {
            token: data.token,
            expiresIn: Math.floor(remaining / 1000),
          });
          this.timer = setTimeout(
            () => {
              if (seq !== this.seq) return;
              this.seq++;
              this.request?.abort();
              this.field.value = "";
              this.emit("captcha-reset");
              this.setState("expired", "凭证已过期，请重新验证。");
            },
            Math.max(0, data.expiresIn * 1000 - (Date.now() - started)),
          );
        } else if (data.code === "incorrect" && data.attemptsRemaining > 0) {
          this.move(0);
          this.setState(
            "ready",
            `没有对齐，再试一次 · 剩余 ${data.attemptsRemaining} 次`,
          );
        } else {
          clearTimeout(this.timer);
          this.field.value = "";
          this.setState(
            "error",
            data.code === "incorrect"
              ? "尝试次数已用完，请换一张。"
              : messages[data.code] || "验证失败，请换一张。",
          );
        }
      } catch (e) {
        if (seq !== this.seq || e.name === "AbortError") return;
        this.move(0);
        this.setState("error", "网络连接中断，请换一张重试。");
      }
    }
    getToken() {
      return this.field?.value || "";
    }
  }
  NovaSlider.id = 1;
  if (!customElements.get("nova-slider"))
    customElements.define("nova-slider", NovaSlider);
})();
