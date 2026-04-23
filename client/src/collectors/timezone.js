import { safe } from "../helpers.js";

export function collectTimezone() {
  return {
    offset:   new Date().getTimezoneOffset(),
    timezone: safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
    locale:   safe(() => Intl.DateTimeFormat().resolvedOptions().locale),
  };
}
