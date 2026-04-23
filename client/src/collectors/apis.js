export function collectAPIs() {
  const has = (...path) => {
    let o = window;
    for (const k of path) { if (o == null || !(k in Object(o))) return false; o = o[k]; }
    return true;
  };
  return {
    crypto:           has("crypto"),
    cryptoSubtle:     has("crypto", "subtle"),
    webGL:            has("WebGLRenderingContext"),
    webGL2:           has("WebGL2RenderingContext"),
    webRTC:           has("RTCPeerConnection"),
    serviceWorker:    has("navigator", "serviceWorker"),
    paymentRequest:   has("PaymentRequest"),
    MutationObserver: has("MutationObserver"),
    performance:      has("performance"),
  };
}
