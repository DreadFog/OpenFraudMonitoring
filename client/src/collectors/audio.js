import { safe } from "../helpers.js";

export function collectAudio() {
  return new Promise(resolve => {
    const done = safe(() => {
      const ctx = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(1, 44100, 44100);
      const osc = ctx.createOscillator();
      const cmp = ctx.createDynamicsCompressor();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(10000, ctx.currentTime);
      [["threshold", -50], ["knee", 40], ["ratio", 12], ["attack", 0], ["release", 0.25]].forEach(([k, v]) => {
        if (cmp[k]) cmp[k].setValueAtTime(v, ctx.currentTime);
      });
      osc.connect(cmp); cmp.connect(ctx.destination);
      osc.start(0); ctx.startRendering();
      ctx.oncomplete = e => {
        const buf = e.renderedBuffer.getChannelData(0);
        let sum = 0;
        for (let i = 4500; i < 5000; i++) sum += Math.abs(buf[i]);
        resolve(sum.toString());
      };
      return true;
    });
    if (!done) resolve(null);
    setTimeout(() => resolve(null), 1500);
  });
}
