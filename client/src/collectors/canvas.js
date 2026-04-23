import { safe } from "../helpers.js";

export function collectCanvas() {
  const c = document.createElement("canvas");
  c.width = 400; c.height = 100;
  const ctx = c.getContext("2d");
  if (!ctx) return null;

  ctx.textBaseline = "top";
  ctx.fillStyle    = "#f60";
  ctx.fillRect(125, 1, 62, 20);
  ctx.fillStyle    = "#069";
  ctx.font         = "11pt Arial";
  ctx.fillText("BrowserFP \u2764 \u0041\u0062\u0063", 2, 15);
  ctx.fillStyle    = "rgba(102,204,0,0.7)";
  ctx.font         = "18pt Georgia";
  ctx.fillText("BrowserFP \u2764 \u0041\u0062\u0063", 4, 45);

  ctx.rect(0, 0, 10, 10);
  ctx.rect(2, 2, 6, 6);
  const windingSupport = safe(() => ctx.isPointInPath(5, 5, "evenodd"));

  return {
    dataURL: safe(() => c.toDataURL()),
    windingSupport,
  };
}
