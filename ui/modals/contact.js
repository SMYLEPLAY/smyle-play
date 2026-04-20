/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/modals/contact.js
   Contact modal: local log + mailto fallback.

   Pure DOM/localStorage — no shared state. Self-contained.
   ───────────────────────────────────────────────────────────────────────── */

// ── 14. CONTACT MODAL ───────────────────────────────────────────────────────

function openContactModal() {
  document.getElementById('contactModal').classList.add('open');
  document.getElementById('contact-success').textContent = '';
  document.getElementById('contact-form').reset();
}

function closeContactModal() {
  document.getElementById('contactModal').classList.remove('open');
}

function submitContact() {
  const name    = document.getElementById('contact-name').value.trim();
  const email   = document.getElementById('contact-email').value.trim();
  const type    = document.getElementById('contact-type').value;
  const msg     = document.getElementById('contact-msg').value.trim();

  if (!msg) {
    document.getElementById('contact-success').style.color = '#ff5555';
    document.getElementById('contact-success').textContent = 'Merci d\'écrire un message.';
    return;
  }

  // Sauvegarder dans localStorage (log local)
  const feedbacks = JSON.parse(localStorage.getItem('smyle_feedback') || '[]');
  feedbacks.push({ name, email, type, msg, date: new Date().toISOString() });
  localStorage.setItem('smyle_feedback', JSON.stringify(feedbacks));

  // Ouvrir le client mail de l'utilisateur en fallback
  const subject = encodeURIComponent(`[WATT] ${type} — ${name || 'Anonyme'}`);
  const body    = encodeURIComponent(`Catégorie : ${type}\nNom : ${name || '—'}\nEmail : ${email || '—'}\n\n${msg}`);
  const mailto  = `mailto:smyletheplan@gmail.com?subject=${subject}&body=${body}`;
  window.location.href = mailto;

  document.getElementById('contact-success').style.color = '#44cc88';
  document.getElementById('contact-success').textContent = 'Message enregistré — merci pour ton retour !';
  setTimeout(closeContactModal, 2200);
}
