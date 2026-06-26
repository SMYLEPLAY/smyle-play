/* ─────────────────────────────────────────────────────────────────────────
   WATT — calque d'ambiance « pétrole vivant ».
   Additif et NON intrusif : injecte un <canvas> en fond (z-index -1), derrière
   tout le contenu. Ne touche à AUCUN item, AUCUNE mécanique. Si WebGL échoue
   ou si la moindre erreur survient, on ne fait rien (l'app reste intacte).
   Réversible : retirer la balise <script> + la règle de fond dans style.css.
   Réglage 2026-06-26 : mouvement accentué + parallaxe curseur, mais reste très
   sombre (loi 85 % noir). Réf : OBSIDIAN/02_WATT/2026-06-25_WATT_CREATIVE_DIRECTION.md
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  try {
    if (document.getElementById('watt-oil')) return;
    var c = document.createElement('canvas');
    c.id = 'watt-oil';
    c.setAttribute('aria-hidden', 'true');
    c.style.cssText =
      'position:fixed;inset:0;width:100%;height:100%;z-index:-1;pointer-events:none;display:block;';

    var gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!gl) {
      c.style.background =
        'radial-gradient(1200px 800px at 72% -5%,#17122a,#050508 60%)';
      var put = function(){ document.body.insertBefore(c, document.body.firstChild); };
      if (document.body) put(); else document.addEventListener('DOMContentLoaded', put);
      return;
    }

    function size() {
      var w = window.innerWidth, h = window.innerHeight;
      c.width = w; c.height = h;            // ratio 1 = perf (fond subtil)
      gl.viewport(0, 0, w, h);
    }

    var vs = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
    var fs =
      'precision highp float;uniform vec2 u_r;uniform float u_t;uniform vec2 u_m;' +
      'float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}' +
      'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);' +
      'return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}' +
      'float fbm(vec2 p){float s=0.,a=.5;for(int i=0;i<6;i++){s+=a*n(p);p*=2.02;a*=.5;}return s;}' +
      'void main(){vec2 uv=gl_FragCoord.xy/u_r;vec2 p=uv*vec2(u_r.x/u_r.y,1.)*2.3;' +
      'p+=(u_m-0.5)*0.55;' +                         /* parallaxe curseur, douce */
      'float t=u_t*0.05;' +                          /* mouvement accentué */
      'vec2 q=vec2(fbm(p+t),fbm(p+vec2(5.2,1.3)-t*.85));' +
      'vec2 r=vec2(fbm(p+3.6*q+vec2(1.7,9.2)+t*.6),fbm(p+3.6*q+vec2(8.3,2.8)-t*.5));' +
      'float f=fbm(p+3.6*r);' +
      'vec3 col=mix(vec3(.012,.012,.024),vec3(.05,.043,.094),f);' +   /* base très sombre */
      'col+=smoothstep(.55,.98,f)*vec3(.17,.10,.34)*.72;' +          /* veines violettes plus lisibles */
      'col+=pow(max(0.,r.x),2.6)*vec3(.05,.12,.30)*.6;' +            /* profondeur bleue */
      'col+=pow(max(0.,q.y),3.5)*vec3(.10,.06,.22)*.5;' +
      'float vig=smoothstep(1.4,.18,length(uv-vec2(.5,.42)));col*=mix(.4,1.,vig);' +
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
    var um = gl.getUniformLocation(prog, 'u_m');
    var t0 = Date.now(), raf = 0;
    var mx = 0.5, my = 0.5, tx = 0.5, ty = 0.5;   /* cible + valeur lissée */
    window.addEventListener('mousemove', function (e) {
      tx = e.clientX / window.innerWidth;
      ty = e.clientY / window.innerHeight;
    }, { passive: true });

    function frame() {
      mx += (tx - mx) * 0.04;                       /* lissage = mouvement organique */
      my += (ty - my) * 0.04;
      gl.uniform2f(ur, c.width, c.height);
      gl.uniform1f(ut, (Date.now() - t0) / 1000);
      gl.uniform2f(um, mx, my);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      raf = requestAnimationFrame(frame);
    }
    function run() { cancelAnimationFrame(raf); frame(); }

    function start() {
      size();
      window.addEventListener('resize', size);
      run();
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) cancelAnimationFrame(raf); else run();
      });
    }

    if (document.body) { document.body.insertBefore(c, document.body.firstChild); start(); }
    else document.addEventListener('DOMContentLoaded', function () {
      document.body.insertBefore(c, document.body.firstChild); start();
    });
  } catch (e) { /* fond optionnel : ne jamais casser l'app */ }
})();
