/* ---------- Start ---------- */
(async () => {
  await loadSettings();
  try { App.me = await api('me'); } catch { return; }
  setTeams(App.me.teams);
  renderSideFoot();
  applyPermissions();
  checkVersion();
  refreshMailBadge();
  setInterval(() => { if (!document.hidden) { refreshMailBadge(); refreshNavCounts(); } }, 60 * 1000);
  setInterval(() => { if (!document.hidden) syncAppBadge(); }, 5 * 60 * 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { refreshMailBadge(); syncAppBadge(); } });
  if (App.me.must_2fa) location.hash = '#/profile';
  route();
  if (!App.me.must_2fa) setTimeout(showTaskBanner, 1200);
})();
