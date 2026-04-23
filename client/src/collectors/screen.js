export function collectScreen() {
  return {
    width:            screen.width,
    height:           screen.height,
    availWidth:       screen.availWidth,
    availHeight:      screen.availHeight,
    colorDepth:       screen.colorDepth,
    pixelDepth:       screen.pixelDepth,
    devicePixelRatio: window.devicePixelRatio || null,
    innerWidth:       window.innerWidth,
    innerHeight:      window.innerHeight,
    outerWidth:       window.outerWidth,
    outerHeight:      window.outerHeight,
  };
}
