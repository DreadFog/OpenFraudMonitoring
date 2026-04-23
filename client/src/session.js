import { CFG } from "./config.js";
import { rnd } from "./helpers.js";

export function getSession() {
  let sid = sessionStorage.getItem(CFG.sessionKey);
  if (!sid) { sid = rnd() + rnd(); sessionStorage.setItem(CFG.sessionKey, sid); }
  return sid;
}
