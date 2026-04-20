/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/toast.js
   Toast global réutilisable sur toutes les pages.
   API :
     window.smyleToast('Message', { type: 'success' | 'info' | 'error', duration: 3000 })

   Auto-inject du container. Idempotent (ne crée qu'une fois).
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  const CSS = `
    .smyle-toast-wrap {
      position: fixed;
      top: 22px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 10000;
      display: flex;
      flex-direction: column;
      gap: 10px;
      pointer-events: none;
    }
    .smyle-toast {
      pointer-events: auto;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 11px 18px;
      border-radius: 999px;
      background: rgba(8, 0, 24, 0.92);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid rgba(136, 0, 255, 0.25);
      color: #e6ddff;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 13px;
      font-weight: 500;
      letter-spacing: 0.01em;
      box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255,255,255,0.03);
      opacity: 0;
      transform: translateY(-12px);
      transition: opacity .3s ease, transform .3s ease;
      max-width: calc(100vw - 40px);
    }
    .smyle-toast.show { opacity: 1; transform: translateY(0); }
    .smyle-toast.success { border-color: rgba(255, 215, 0, 0.4); color: #FFD700; }
    .smyle-toast.success .smyle-toast-icon { color: #FFD700; }
    .smyle-toast.error   { border-color: rgba(255, 60, 80, 0.5); color: #ff6b7a; }
    .smyle-toast.info    { border-color: rgba(136, 0, 255, 0.35); color: #cc88ff; }
    .smyle-toast-icon { width: 16px; height: 16px; flex-shrink: 0; }
    @media (max-width: 600px) {
      .smyle-toast-wrap { top: 12px; }
      .smyle-toast { font-size: 12px; padding: 9px 14px; }
    }
  `;

  const ICONS = {
    success: '<svg class="smyle-toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    error:   '<svg class="smyle-toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    info:    '<svg class="smyle-toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  };

  function _injectStyle() {
    if (document.getElementById('smyle-toast-style')) return;
    const s = document.createElement('style');
    s.id = 'smyle-toast-style';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function _getWrap() {
    let wrap = document.getElementById('smyle-toast-wrap');
    if (wrap) return wrap;
    wrap = document.createElement('div');
    wrap.id = 'smyle-toast-wrap';
    wrap.className = 'smyle-toast-wrap';
    document.body.appendChild(wrap);
    return wrap;
  }

  function smyleToast(message, options = {}) {
    _injectStyle();
    const { type = 'info', duration = 3200 } = options;
    const wrap = _getWrap();

    const toast = document.createElement('div');
    toast.className = `smyle-toast ${type}`;
    toast.innerHTML = `${ICONS[type] || ICONS.info}<span>${String(message)}</span>`;
    wrap.appendChild(toast);

    // Reflow to trigger transition
    requestAnimationFrame(() => toast.classList.add('show'));

    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 320);
    }, duration);
  }

  if (typeof window !== 'undefined') {
    window.smyleToast = smyleToast;
  }
})();
