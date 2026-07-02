/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/modals/premium.js
   Premium interest modal: register lead + mailto notification.

   Calls helpers from:
     ui/core/storage.js — getCurrentUser

   Must load after storage.js.
   ───────────────────────────────────────────────────────────────────────── */

// ── 14a. PREMIUM MODAL ──────────────────────────────────────────────────────

function openPremiumModal() {
  document.getElementById('premiumModal').classList.add('open');
  document.getElementById('premiumMsg').textContent = '';
}

function closePremiumModal() {
  document.getElementById('premiumModal').classList.remove('open');
}

function submitPremiumInterest() {
  const user = getCurrentUser();
  // Sauvegarder l'intérêt en localStorage
  const interests = JSON.parse(localStorage.getItem('smyle_premium_interests') || '[]');
  const email = user ? user.email : 'anonyme';
  if (!interests.includes(email)) {
    interests.push(email);
    localStorage.setItem('smyle_premium_interests', JSON.stringify(interests));
  }
  const msg = document.getElementById('premiumMsg');
  msg.style.color = '#ffd700';
  msg.textContent = '✓ Noté ! Tu seras averti(e) à l\'ouverture de l\'espace artiste.';
  // Ouvrir client mail pour notifier l'équipe
  if (user) {
    const subject = encodeURIComponent('[WATT] Intérêt Premium Artiste');
    const body = encodeURIComponent(`Utilisateur intéressé : ${user.name} <${user.email}>`);
    setTimeout(() => { window.location.href = `mailto:smyletheplan@gmail.com?subject=${subject}&body=${body}`; }, 1200);
  }
}
