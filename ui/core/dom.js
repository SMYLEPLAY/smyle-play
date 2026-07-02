/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/dom.js
   Pure DOM / formatting helpers. No shared state.
   Doit être chargé après state.js et avant tout consommateur dans index.html.
   ───────────────────────────────────────────────────────────────────────── */

// ── 3. ENCODE FILE PATH ──────────────────────────────────────────────────────

function encodeFilePath(folder, filename) {
  return folder.split('/').map(encodeURIComponent).join('/') + '/' + encodeURIComponent(filename);
}

// ── FORMAT PLAYS ─────────────────────────────────────────────────────────────

function fmtPlays(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return n.toString();
}

// ── BUILD ALT URL (fallback audio) ───────────────────────────────────────────

function buildAltUrl(url) {
  // Si l'URL contient /JUNGLE%20OSMOSE/, essayer /%20JUNGLE%20OSMOSE/
  if (url.includes('/JUNGLE%20OSMOSE/'))
    return url.replace('/JUNGLE%20OSMOSE/', '/%20JUNGLE%20OSMOSE/');
  // Si déjà avec espace, essayer sans
  if (url.includes('/%20JUNGLE%20OSMOSE/'))
    return url.replace('/%20JUNGLE%20OSMOSE/', '/JUNGLE%20OSMOSE/');
  return null;
}

// ── FORMAT TIME ──────────────────────────────────────────────────────────────

function fmtTime(s) {
  if (!s || isNaN(s)) return '0:00';
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function fmtTimeLong(s) {
  if (!s || isNaN(s)) return '';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}h ${m}min`;
  if (m > 0) return `${m} min ${String(sec).padStart(2,'0')} sec`;
  return `${sec} sec`;
}

// ── HUB HELPERS (format / escape / slugify) ──────────────────────────────────

function _fmtHub(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function _esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _slugify(name) {
  return (name || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

// ── 15. TOAST ────────────────────────────────────────────────────────────────

function showToast(msg) {
  let t = document.getElementById('smyle-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'smyle-toast';
    Object.assign(t.style, {
      position:'fixed', bottom:'96px', left:'50%', transform:'translateX(-50%)',
      background:'rgba(15,5,30,.95)', border:'1px solid rgba(136,0,255,.3)',
      color:'rgba(200,160,255,.9)', fontSize:'11px', letterSpacing:'.2em',
      textTransform:'uppercase', padding:'10px 22px', borderRadius:'3px',
      zIndex:'9999', transition:'opacity .3s, transform .3s',
      opacity:'0', pointerEvents:'none', whiteSpace:'nowrap',
    });
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = '1';
  t.style.transform = 'translateX(-50%) translateY(0)';
  clearTimeout(t._tmr);
  t._tmr = setTimeout(() => {
    t.style.opacity = '0';
    t.style.transform = 'translateX(-50%) translateY(6px)';
  }, 2600);
}
