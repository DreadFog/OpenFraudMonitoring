const COOKIE_NAME = "ofm_notice_acknowledged";
const NOTICE_ID = "ofm-privacy-notice";

export default {
  name: "privacy_notice",

  init() {
    try {
      if (document.cookie.split(";").some(cookie => cookie.trim() === `${COOKIE_NAME}=1`)) return;
    } catch (_) {}
    if (document.getElementById(NOTICE_ID)) return;

    const host = document.createElement("div");
    host.id = NOTICE_ID;
    host.style.setProperty("all", "initial", "important");
    host.style.setProperty("position", "fixed", "important");
    host.style.setProperty("inset", "auto 0 0 0", "important");
    host.style.setProperty("z-index", "2147483647", "important");
    const root = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      :host { color-scheme: light; }
      * { box-sizing: border-box; }
      section {
        display: flex; align-items: center; gap: 24px;
        margin: 0; padding: 18px 24px;
        padding-bottom: max(18px, env(safe-area-inset-bottom));
        border-top: 3px solid #167568; background: #fff; color: #242424;
        box-shadow: 0 -4px 18px #00000014;
        font: 14px/1.6 Verdana, sans-serif; letter-spacing: 0;
        max-height: 60vh; overflow: auto;
      }
      p { flex: 1; min-width: 0; margin: 0; overflow-wrap: anywhere; }
      a { color: #11695e; text-decoration: underline; text-underline-offset: 3px; }
      button {
        flex: none; min-width: 72px; min-height: 44px; padding: 10px 20px;
        border: 1px solid #11695e; border-radius: 4px;
        background: #11695e; color: #fff; cursor: pointer;
        font: bold 14px/1.4 Verdana, sans-serif; letter-spacing: 0;
      }
      button:hover { background: #0c5148; }
      a:focus-visible, button:focus-visible { outline: 3px solid #b85b12; outline-offset: 3px; }
      @media (max-width: 600px) {
        section { flex-wrap: wrap; gap: 12px; padding: 14px 16px;
          padding-bottom: max(14px, env(safe-area-inset-bottom)); }
        p { flex-basis: 100%; }
        button { margin-left: auto; }
      }
    `;
    const banner = document.createElement("section");
    banner.setAttribute("aria-label", "Fraud monitoring notice");
    banner.setAttribute("role", "region");
    const message = document.createElement("p");
    const link = document.createElement("a");
    link.href = "https://github.com/DreadFog/OpenFraudMonitoring";
    link.textContent = "OpenFraudMonitoring";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    message.append(
      "This website protects itself against fraud attempts using ", link,
      ". For this purpose, data about your web browser and activity on this site will be collected.",
    );
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "OK";
    button.addEventListener("click", () => {
      try {
        const secure = location.protocol === "https:" ? "; Secure" : "";
        document.cookie = `${COOKIE_NAME}=1; Max-Age=31536000; Path=/; SameSite=Lax${secure}`;
      } catch (_) {}
      host.remove();
    });
    host.addEventListener("click", event => event.stopPropagation());
    host.addEventListener("keydown", event => event.stopPropagation());
    banner.append(message, button);
    root.append(style, banner);
    document.body.append(host);
  },
};