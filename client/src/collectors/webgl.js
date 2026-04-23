import { safe } from "../helpers.js";

export function collectWebGL() {
  const c  = document.createElement("canvas");
  const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
  if (!gl) return null;

  const dbg = gl.getExtension("WEBGL_debug_renderer_info");

  const paramNames = [
    "MAX_VERTEX_ATTRIBS", "MAX_VERTEX_UNIFORM_VECTORS",
    "MAX_VARYING_VECTORS", "MAX_VERTEX_TEXTURE_IMAGE_UNITS",
    "MAX_TEXTURE_IMAGE_UNITS", "MAX_COMBINED_TEXTURE_IMAGE_UNITS",
    "MAX_TEXTURE_SIZE", "MAX_CUBE_MAP_TEXTURE_SIZE",
    "MAX_RENDERBUFFER_SIZE", "MAX_VIEWPORT_DIMS",
    "ALIASED_LINE_WIDTH_RANGE", "ALIASED_POINT_SIZE_RANGE",
    "RED_BITS", "GREEN_BITS", "BLUE_BITS", "ALPHA_BITS",
    "DEPTH_BITS", "STENCIL_BITS", "MAX_FRAGMENT_UNIFORM_VECTORS",
  ];

  const params = {};
  for (const p of paramNames) {
    params[p] = safe(() => {
      const v = gl.getParameter(gl[p]);
      return (v instanceof Float32Array || v instanceof Int32Array) ? Array.from(v) : v;
    });
  }

  let renderDataURL = null;
  safe(() => {
    c.width = 64; c.height = 64;
    const vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, "attribute vec2 p;void main(){gl_Position=vec4(p,0,1);}");
    gl.compileShader(vs);
    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, "void main(){gl_FragColor=vec4(0.2,0.6,0.8,1);}");
    gl.compileShader(fs);
    const prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs);
    gl.linkProgram(prog); gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-.2, -.9, 0, .4, -.26, 0, 0, .732, 0]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    renderDataURL = c.toDataURL();
  });

  return {
    vendor:         dbg ? safe(() => gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL))   : null,
    renderer:       dbg ? safe(() => gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : null,
    maskedVendor:   safe(() => gl.getParameter(gl.VENDOR)),
    maskedRenderer: safe(() => gl.getParameter(gl.RENDERER)),
    version:        safe(() => gl.getParameter(gl.VERSION)),
    shadingVersion: safe(() => gl.getParameter(gl.SHADING_LANGUAGE_VERSION)),
    extensions:     safe(() => gl.getSupportedExtensions()) || [],
    params,
    renderDataURL,
  };
}
