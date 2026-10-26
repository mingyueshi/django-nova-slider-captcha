/* NOVA Slider. Vanilla Web Component; no runtime framework dependency. */
(() => {
  const inits = new Map();
  const dictionaries = {
    "zh-CN": {
      widget_label: "安全验证",
      background_alt: "带有一处拼图缺口的山水图案",
      piece_alt: "可移动拼图块",
      track: "向右拖动滑块",
      slider_label: "移动拼图块",
      refresh_label: "换一张拼图",
      refresh: "换一张",
      keyboard: "可用方向键微调，Enter 提交；也支持触屏拖动。",
      value: "{percent}%，按 Enter 校验",
      connecting: "正在连接验证服务…",
      generating: "正在生成拼图…",
      loading: "正在生成新拼图…",
      ready: "拖动拼图，对齐图中的缺口",
      checking: "正在由服务端校验…",
      success: "验证通过，有效期 {seconds} 秒",
      success_overlay: "✓ 验证通过",
      incorrect: "没有对齐，再试一次 · 剩余 {remaining} 次",
      rate_limited: "操作有些频繁，请在 {seconds} 秒后重试。",
      rate_limited_unknown: "操作有些频繁，请稍后重试。",
      session_expired: "会话已过期，请刷新验证。",
      csrf_failed: "安全校验失败，请刷新页面重试。",
      unavailable: "验证服务暂不可用，请稍后重试。",
      challenge_unavailable: "这张拼图已过期或已使用，请换一张。",
      init_required: "会话已更新，请换一张拼图。",
      expired: "拼图已过期，请换一张。",
      token_expired: "凭证已过期，请重新验证。",
      already_verified: "这张拼图已使用，请换一张。",
      attempts_exhausted: "尝试次数已用完，请换一张。",
      init_failed: "初始化失败，请重试。",
      generation_failed: "生成失败，请重试。",
      verification_failed: "验证失败，请换一张。",
      network_error: "网络连接中断，请换一张重试。",
      endpoint_invalid: "验证码接口地址无效。",
      endpoint_origin: "验证码接口必须与当前页面同源。",
      demo_accepted: "请求已接受，验证凭证已使用。",
      demo_rejected: "请求被拒绝，请重新完成验证。",
      demo_network_error: "网络连接中断，请重新完成验证。",
    },
    en: {
      widget_label: "Security verification",
      background_alt: "Landscape with a missing puzzle piece",
      piece_alt: "Movable puzzle piece",
      track: "Drag the slider to the right",
      slider_label: "Move the puzzle piece",
      refresh_label: "Get a new puzzle",
      refresh: "New puzzle",
      keyboard: "Use the arrow keys to adjust and Enter to submit, or drag on a touchscreen.",
      value: "{percent}%, press Enter to verify",
      connecting: "Connecting to verification service…",
      generating: "Generating a puzzle…",
      loading: "Generating a new puzzle…",
      ready: "Slide the piece to fit the gap",
      checking: "Checking with the server…",
      success: "Verified. Valid for {seconds} seconds",
      success_overlay: "✓ Verified",
      incorrect: "Not aligned. Try again · {remaining} attempts remaining",
      rate_limited: "Too many requests. Try again in {seconds} seconds.",
      rate_limited_unknown: "Too many requests. Please try again later.",
      session_expired: "Your session expired. Please refresh the challenge.",
      csrf_failed: "Security check failed. Please reload the page.",
      unavailable: "Verification is temporarily unavailable. Please try again later.",
      challenge_unavailable: "This puzzle expired or was used. Please get a new puzzle.",
      init_required: "Your session changed. Please get a new puzzle.",
      expired: "This puzzle expired. Please get a new puzzle.",
      token_expired: "Your verification expired. Please verify again.",
      already_verified: "This puzzle was used. Please get a new puzzle.",
      attempts_exhausted: "No attempts remain. Please get a new puzzle.",
      init_failed: "Initialization failed. Please try again.",
      generation_failed: "Could not generate a puzzle. Please try again.",
      verification_failed: "Verification failed. Please get a new puzzle.",
      network_error: "Connection interrupted. Please get a new puzzle and try again.",
      endpoint_invalid: "The CAPTCHA endpoint is invalid.",
      endpoint_origin: "The CAPTCHA endpoint must use the same origin as this page.",
      demo_accepted: "Request accepted. The verification token has been used.",
      demo_rejected: "Request rejected. Please complete a new challenge.",
      demo_network_error: "Network error. Please try a new challenge.",
    },
  };
  const errorKeys = new Set([
    "rate_limited", "session_expired", "csrf_failed", "unavailable",
    "challenge_unavailable", "init_required", "expired", "already_verified",
    "attempts_exhausted",
  ]);
  const normalizeLocale = (value) => {
    if (typeof value !== "string") return "zh-CN";
    const tag = value.trim();
    // A small locale-tag grammar, not a BCP47 registry/semantic validator.
    // Missing/malformed input retains the historical Chinese default; explicit
    // well-formed unsupported languages use the available English dictionary.
    if (!/^[a-z]{2,8}(?:[-_][a-z0-9]{1,8})*$/i.test(tag)) return "zh-CN";
    return /^zh(?:[-_]|$)/i.test(tag) ? "zh-CN" : "en";
  };
  const bounded = (value, max) =>
    typeof value === "number" && Number.isFinite(value)
      ? Math.min(max, Math.max(0, Math.ceil(value))) : 0;
  const localError = (key, values = {}) => Object.assign(new Error(key), { key, values });
  function loadImage(image, source, signal) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const decode = typeof image.decode === "function";
      const finish = (error) => {
        if (settled) return;
        settled = true;
        image.removeEventListener("load", loaded);
        image.removeEventListener("error", failed);
        signal.removeEventListener("abort", aborted);
        if (error) reject(error); else resolve();
      };
      const loaded = () => { if (!decode) finish(); };
      const failed = () => finish(new Error("Image loading failed"));
      const aborted = () => finish(new DOMException("Image loading aborted", "AbortError"));
      // Register before src, including cached/synchronously delivered load events.
      image.addEventListener("load", loaded);
      image.addEventListener("error", failed);
      signal.addEventListener("abort", aborted, { once: true });
      if (signal.aborted) { aborted(); return; }
      try {
        image.src = source;
        if (decode) image.decode().then(() => finish(), finish);
        else if (image.complete) {
          if (image.naturalWidth > 0) finish(); else failed();
        }
      } catch (error) { finish(error); }
    });
  }
  const errorText = (data, fallback) => {
    if (data?.code === "rate_limit_unavailable") return { key: "unavailable", values: {} };
    if (!errorKeys.has(data?.code)) return { key: fallback, values: {} };
    if (data.code === "rate_limited") {
      const seconds = bounded(data.retryAfter, 86400);
      return { key: seconds ? "rate_limited" : "rate_limited_unknown", values: { seconds } };
    }
    return { key: data.code, values: {} };
  };
  async function init(endpoint) {
    if (!inits.has(endpoint))
      inits.set(endpoint, fetch(endpoint + "init", {
        credentials: "same-origin", cache: "no-store",
      }).then(async (r) => {
        let data;
        try { data = await r.json(); } catch (_) { throw localError("init_failed"); }
        if (!r.ok) {
          const message = errorText(data, "init_failed");
          throw localError(message.key, message.values);
        }
        if (typeof data?.csrfToken !== "string" || !data.csrfToken)
          throw localError("init_failed");
        return data.csrfToken;
      }).catch((e) => { inits.delete(endpoint); throw e; }));
    return inits.get(endpoint);
  }
  class NovaSlider extends HTMLElement {
    static get observedAttributes() { return ["locale", "aria-describedby", "aria-invalid"]; }
    get locale() { return normalizeLocale(this.getAttribute("locale")); }
    set locale(value) { this.setLocale(value); }
    setLocale(value) {
      this.setAttribute("locale", normalizeLocale(value));
      return this.locale;
    }
    attributeChangedCallback(name) {
      if (name === "locale") this.renderLocale();
      else this.syncFormAria();
    }
    syncFormAria() {
      if (!this.range) return;
      const descriptions = (this.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
      descriptions.push(this.querySelector(".nsc-keyboard").id);
      this.range.setAttribute("aria-describedby", [...new Set(descriptions)].join(" "));
      const invalid = this.getAttribute("aria-invalid");
      if (invalid === null) this.range.removeAttribute("aria-invalid");
      else this.range.setAttribute("aria-invalid", invalid);
    }
    get messages() { return { ...dictionaries[this.locale], ...this._messages }; }
    set messages(overrides) {
      if (overrides === null) this._messages = {};
      else if (overrides && typeof overrides === "object" && !Array.isArray(overrides)) {
        this._messages ||= {};
        for (const key of Object.keys(dictionaries.en)) {
          if (Object.hasOwn(overrides, key) && typeof overrides[key] === "string")
            this._messages[key] = overrides[key].slice(0, 2000);
        }
      }
      this.renderLocale();
    }
    getText(key, values = {}) {
      if (!Object.hasOwn(dictionaries.en, key)) return "";
      const template = this._messages?.[key] ?? dictionaries[this.locale][key];
      return template.replace(/\{(remaining|seconds|percent)\}/g, (_, name) =>
        String(bounded(values[name], name === "percent" ? 100 : 86400)));
    }
    renderLocale() {
      if (!this.range) return;
      this.lang = this.locale;
      this.setAttribute("aria-label", this.getText("widget_label"));
      this.querySelector(".nsc").lang = this.locale;
      for (const [selector, key, attribute] of [
        [".nsc-background", "background_alt", "alt"],
        [".nsc-piece", "piece_alt", "alt"],
        [".nsc-range", "slider_label", "aria-label"],
        [".nsc-refresh", "refresh_label", "aria-label"],
        [".nsc-track-text", "track"],
        [".nsc-refresh-text", "refresh"],
        [".nsc-keyboard", "keyboard"],
      ]) {
        const element = this.querySelector(selector);
        if (attribute) element.setAttribute(attribute, this.getText(key));
        else element.textContent = this.getText(key);
      }
      this.range.setAttribute("aria-valuetext", this.getText("value", { percent: Math.round((this.x / this.maxX) * 100) }));
      this.renderStatus();
      this.emit("captcha-locale", { locale: this.locale });
    }
    connectedCallback() {
      if (this.live) return;
      this.live = true;
      this.seq = (this.seq || 0) + 1;
      this.x = 0;
      this.maxX = 1;
      this.imageWidth = 1;
      this.resetPointer();
      this.abortEvents = new AbortController();
      // Upgrade property values assigned before customElements.define().
      for (const name of ["locale", "messages"]) {
        if (Object.hasOwn(this, name)) {
          const value = this[name];
          delete this[name];
          this[name] = value;
        }
      }
      // Only fixed markup is inserted here. All translated/custom text uses textContent.
      this.innerHTML = `<div class="nsc"><div class="nsc-image"><img class="nsc-background" alt="" draggable="false"><img class="nsc-piece" alt="" draggable="false"><div class="nsc-overlay"></div></div><div class="nsc-track"><div class="nsc-fill"></div><span class="nsc-track-text" aria-hidden="true"></span><input class="nsc-range" type="range" min="0" max="1" step="1" value="0" aria-describedby="nsc-instructions-${NovaSlider.id++}"><span class="nsc-handle" aria-hidden="true">→</span></div><div class="nsc-meta"><span class="nsc-status" role="status" aria-live="polite"></span><button class="nsc-refresh" type="button"><span aria-hidden="true">↻</span> <span class="nsc-refresh-text"></span></button></div><p class="nsc-keyboard"></p><input type="hidden" name="nova_slider_token" value=""></div>`;
      this.range = this.querySelector(".nsc-range");
      this.querySelector(".nsc-keyboard").id = this.range.getAttribute("aria-describedby");
      this.syncFormAria();
      this.status = this.querySelector(".nsc-status");
      this.overlay = this.querySelector(".nsc-overlay");
      this.field = this.querySelector("input[type=hidden]");
      this.field.name = this.getAttribute("field-name") || "nova_slider_token";
      this.state = "loading";
      this.stateText = { key: "connecting", values: {} };
      this.renderLocale();
      this.endpoint = null;
      let url;
      try { url = new URL(this.getAttribute("endpoint") || "/captcha/", location.href); }
      catch (_) { this.setState("error", "endpoint_invalid"); return; }
      if (url.origin !== location.origin) {
        this.setState("error", "endpoint_origin");
        return;
      }
      this.endpoint = url.pathname.replace(/\/?$/, "/");
      this.purpose = this.getAttribute("purpose") || "demo";
      const on = (element, event, cb) => element.addEventListener(event, cb, { signal: this.abortEvents.signal });
      on(this.range, "input", () => this.move(Number(this.range.value)));
      on(this.range, "pointerdown", (e) => {
        if (this.state !== "ready" || this.activePointerId !== null || !Number.isInteger(e.pointerId)) return;
        this.activePointerId = e.pointerId;
        this.dragging = true;
        try { this.range.setPointerCapture?.(e.pointerId); } catch (_) { /* Pointer may already be inactive. */ }
      });
      on(this.range, "pointerup", (e) => {
        if (this.activePointerId !== null && e.pointerId === this.activePointerId) {
          this.resetPointer();
          this.verify();
        }
      });
      const cancelPointer = (e) => {
        if (e.pointerId === this.activePointerId) this.resetPointer();
      };
      on(this.range, "pointercancel", cancelPointer);
      on(this.range, "lostpointercapture", cancelPointer);
      on(this.range, "keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); this.verify(); }
      });
      on(this.querySelector(".nsc-refresh"), "click", () => this.refresh());
      this.refresh();
    }
    resetPointer() {
      const pointerId = this.activePointerId;
      // Clear identity before release, since release can dispatch lostpointercapture.
      this.activePointerId = null;
      this.dragging = false;
      if (Number.isInteger(pointerId)) {
        try { this.range?.releasePointerCapture?.(pointerId); } catch (_) { /* Capture may already be released. */ }
      }
    }
    disconnectedCallback() {
      this.resetPointer();
      this.live = false;
      this.seq++;
      clearTimeout(this.timer);
      this.request?.abort();
      this.abortEvents?.abort();
    }
    emit(name, detail = {}) {
      this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true }));
    }
    renderStatus() {
      if (!this.stateText) return;
      const { key, values } = this.stateText;
      this.status.textContent = this.getText(key, values);
      this.overlay.hidden = ["ready", "checking"].includes(this.state);
      this.overlay.textContent = this.getText(
        this.state === "success" ? "success_overlay" : this.state === "loading" ? "generating" : key, values,
      );
    }
    setState(state, key, values = {}) {
      if (state !== "ready") this.resetPointer();
      this.state = state;
      this.stateText = { key, values };
      this.querySelector(".nsc").dataset.state = state;
      this.range.disabled = state !== "ready";
      this.renderStatus();
      this.emit("captcha-state", { state, message: this.status.textContent });
    }
    move(x) {
      this.x = Number.isFinite(x) ? Math.min(this.maxX, Math.max(0, x)) : 0;
      this.range.value = this.x;
      this.querySelector(".nsc-piece").style.left = (this.x / this.imageWidth) * 100 + "%";
      this.querySelector(".nsc-handle").style.left = `calc(${(this.x / this.maxX) * 100}% - var(--nsc-handle-size) * ${this.x / this.maxX})`;
      this.querySelector(".nsc-fill").style.width = `calc(${(this.x / this.maxX) * 100}% + var(--nsc-handle-size) * ${1 - this.x / this.maxX})`;
      this.range.setAttribute("aria-valuetext", this.getText("value", { percent: Math.round((this.x / this.maxX) * 100) }));
    }
    async post(action, body, signal) {
      const csrfToken = await init(this.endpoint);
      const r = await fetch(this.endpoint + action, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify(body), signal,
      });
      if (r.status === 403) inits.delete(this.endpoint);
      if (!r.headers.get("content-type")?.includes("application/json"))
        return { ok: false, code: r.status === 403 ? "csrf_failed" : "unavailable" };
      const data = await r.json();
      if (data?.code === "init_required" || data?.code === "session_expired") inits.delete(this.endpoint);
      return data;
    }
    async refresh() {
      if (!this.endpoint || !this.live) return;
      const started = Date.now(), seq = ++this.seq;
      clearTimeout(this.timer);
      this.resetPointer();
      this.request?.abort();
      this.request = new AbortController();
      this.field.value = "";
      this.emit("captcha-reset");
      this.move(0);
      this.setState("loading", "loading");
      try {
        const data = await this.post("challenge", { purpose: this.purpose }, this.request.signal);
        if (seq !== this.seq) return;
        if (!data?.challengeId) {
          const message = errorText(data, "generation_failed");
          throw localError(message.key, message.values);
        }
        // Geometry is public protocol data, but must be valid before arithmetic
        // or enabling input. Dimensions are bounded independently of CSS pixels.
        const dimension = (v) => Number.isInteger(v) && v > 0 && v <= 8192;
        if (!dimension(data.width) || !dimension(data.height) || !dimension(data.pieceWidth)
            || data.pieceWidth >= data.width || data.pieceWidth > data.height
            || !Number.isInteger(data.pieceY) || data.pieceY < 0
            || data.pieceY > data.height - data.pieceWidth)
          throw localError("generation_failed");
        this.challenge = data;
        this.imageWidth = data.width;
        this.maxX = data.width - data.pieceWidth;
        this.range.max = String(this.maxX);
        this.querySelector(".nsc-image").style.aspectRatio = `${data.width} / ${data.height}`;
        this.move(0);
        // New nodes isolate each generation from old image load/error events.
        const bg = new Image(), piece = new Image();
        for (const [image, className, alt] of [[bg, "nsc-background", "background_alt"], [piece, "nsc-piece", "piece_alt"]]) {
          image.className = className;
          image.alt = this.getText(alt);
          image.draggable = false;
          this.querySelector("." + className).replaceWith(image);
        }
        piece.style.width = (data.pieceWidth / data.width) * 100 + "%";
        piece.style.top = (data.pieceY / data.height) * 100 + "%";
        await Promise.all([loadImage(bg, data.background, this.request.signal), loadImage(piece, data.piece, this.request.signal)]);
        if (seq !== this.seq) return;
        this.setState("ready", "ready");
        this.timer = setTimeout(() => {
          if (seq !== this.seq) return;
          this.seq++;
          this.request?.abort();
          this.field.value = "";
          this.emit("captcha-reset");
          this.setState("expired", "expired");
        }, Math.max(0, data.expiresIn * 1000 - (Date.now() - started)));
      } catch (e) {
        if (seq !== this.seq || e.name === "AbortError") return;
        this.request.abort(); // Also clean up a sibling image still loading.
        this.setState("error", Object.hasOwn(dictionaries.en, e.key) ? e.key : "network_error", e.values);
      }
    }
    async verify() {
      if (this.state !== "ready") return;
      const started = Date.now(), seq = this.seq;
      this.setState("checking", "checking");
      try {
        const data = await this.post("verify", { challengeId: this.challenge.challengeId, x: this.x }, this.request.signal);
        if (seq !== this.seq) return;
        if (data?.ok) {
          clearTimeout(this.timer);
          const remaining = Math.max(0, data.expiresIn * 1000 - (Date.now() - started));
          if (!remaining) {
            this.field.value = "";
            this.emit("captcha-reset");
            this.setState("expired", "token_expired");
            return;
          }
          this.field.value = data.token;
          this.setState("success", "success", { seconds: Math.floor(remaining / 1000) });
          this.emit("verified", { token: data.token, expiresIn: Math.floor(remaining / 1000) });
          this.timer = setTimeout(() => {
            if (seq !== this.seq) return;
            this.seq++;
            this.request?.abort();
            this.field.value = "";
            this.emit("captcha-reset");
            this.setState("expired", "token_expired");
          }, Math.max(0, data.expiresIn * 1000 - (Date.now() - started)));
        } else if (data?.code === "incorrect" && data.attemptsRemaining > 0) {
          this.move(0);
          this.setState("ready", "incorrect", { remaining: data.attemptsRemaining });
        } else {
          clearTimeout(this.timer);
          this.field.value = "";
          const message = errorText(data, "verification_failed");
          this.setState("error", data?.code === "incorrect" ? "attempts_exhausted" : message.key, message.values);
        }
      } catch (e) {
        if (seq !== this.seq || e.name === "AbortError") return;
        this.move(0);
        this.setState("error", Object.hasOwn(dictionaries.en, e.key) ? e.key : "network_error", e.values);
      }
    }
    getToken() { return this.field?.value || ""; }
  }
  NovaSlider.id = 1;
  if (!customElements.get("nova-slider")) customElements.define("nova-slider", NovaSlider);
})();
