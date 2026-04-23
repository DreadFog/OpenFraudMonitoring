import { safe } from "../helpers.js";

export function collectBotSignals() {
  const nav = navigator;
  const win = window;

  const cdcProps = safe(() =>
    Object.keys(win).filter(k => /^cdc_\w+/.test(k) || /^[a-zA-Z0-9]{3}_[a-zA-Z0-9]{22}/.test(k))
  , []);

  const noPlugins = safe(() =>
    typeof nav.plugins !== "undefined" && nav.plugins.length === 0 &&
    typeof nav.languages !== "undefined" && nav.languages.length === 0
  );

  let nativeCheckPassed = null;
  safe(() => {
    nativeCheckPassed = Function.prototype.toString.call(Function.prototype.toString).includes("[native code]");
  });

  return {
    webdriver:        !!nav.webdriver,
    languages_empty:  Array.isArray(nav.languages) && nav.languages.length === 0,
    phantom:          !!win._phantom || !!win.callPhantom,
    nightmare:        !!win.__nightmare,
    puppeteer:        !!win.__puppeteer_evaluation_script__,
    selenium:         !!safe(() => win.$chrome_asyncScriptInfo),
    cdcProps,
    noPlugins,
    nativeCheckPassed,
  };
}
