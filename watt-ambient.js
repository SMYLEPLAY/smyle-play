/* ─────────────────────────────────────────────────────────────────────────
   WATT — calque d'ambiance « pétrole vivant ».
   Additif et NON intrusif : injecte un <canvas> en fond (z-index -1), derrière
   tout le contenu. Ne touche à AUCUN item, AUCUNE mécanique. Si WebGL échoue
   ou si la moindre erreur survient, on ne fait rien (l'app reste intacte).
   Réversible : retirer la balise <script> + la règle de fond dans style.css.
   Réf direction artistique : OBSIDIAN/02_WATT/2026-06-25_WATT_CREATIVE_DIRECTION.md
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  try {
    if (document.getElementById('watt-oil')) return;
    var c = document.createElement('canvas');
    c.id = 'watt-oil';
    c.setAttribute('aria-hidden', 'true');
    c.style.cssText =
      'position:fixed;inset:0;width:100%;height:100%;z-index:-1;pointer-events:none;display:block;';
    var mount = function () {
      document.body.insertBefore(c, document.body.firstChild);
      start();
    };
    var gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!gl) {
      c.style.background =
        'radial-gradient(1200px 800px at 72% -5%,#15101f,#050508 60%)';
      if (document.body) document.body.insertBefore(c, document.body.firstChild);
      else document.addEventListener('DOMContentLoaded',
        function(){document.body.insertBefore(c, document.body.firstChild);});
      return;
    }

    function size() {
      var w = window.innerWidth, h = window.innerHeight;
      c.width = w; c.height = h;            // ratio 1 = perf (fond subtil)
      gl.viewport(0, 0, w, h);
    }

    var vs = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
    var fs =
      'precision highp float;uniform vec2 u_r;uniform float u_t;' +
      'float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}' +
      'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);' +
      'return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}' +
      'float fbm(vec2 p){float s=0.,a=.5;for(int i=0;i<6;i++){s+=a*n(p);p*=2.02;a*=.5;}return s;}' +
      'void main(){vec2 uv=gl_FragCoord.xy/u_r;vec2 p=uv*vec2(u_r.x/u_r.y,1.)*2.4;float t=u_t*0.022;' +
      'vec2 q=vec2(fbm(p+t),fbm(p+vec2(5.2,1.3)-t*.8));' +
      'vec2 r=vec2(fbm(p+3.5*q+vec2(1.7,9.2)+t*.5),fbm(p+3.5*q+vec2(8.3,2.8)-t*.4));' +
      'float f=fbm(p+3.5*r);' +
      'vec3 col=mix(vec3(.010,.010,.020),vec3(.037,.032,.072),f);' +
      'col+=smoothstep(.64,.98,f)*vec3(.15,.085,.29)*.5;' +
      'col+=pow(max(0.,r.x),3.)*vec3(.04,.10,.26)*.45;' +
      'float vig=smoothstep(1.35,.22,length(uv-vec2(.5,.42)));col*=mix(.42,1.,vig)*.9;' +
      'gl_FragColor=vec4(col,1.);}';

    function sh(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s); return s;
    }
    var prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, vs));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog); gl.useProgram(prog);
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,1,1]), gl.STATIC_DRAW);
    var lp = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(lp);
    gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 0, 0);
    var ur = gl.getUniformLocation(prog, 'u_r');
    var ut = gl.getUniformLocation(prog, 'u_t');
    var t0 = Date.now(), raf = 0;

    function start() {
      size();
      window.addEventListener('resize', size);
      (function loop() {
        gl.uniform2f(ur, c.width, c.height);
        gl.uniform1f(ut, (Date.now() - t0) / 1000);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        raf = requestAnimationFrame(loop);
      })();
      // Économie : on coupe l'animation quand l'onglet n'est pas visible.
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) { cancelAnimationFrame(raf); }
        else { (function loop() {
          gl.uniform2f(ur, c.width, c.height);
          gl.uniform1f(ut, (Date.now() - t0) / 1000);
          gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
          raf = requestAnimationFrame(loop);
        })(); }
      });
    }

    if (document.body) mount();
    else document.addEventListener('DOMContentLoaded', mount);
  } catch (e) { /* fond optionnel : ne jamais casser l'app */ }
})();
