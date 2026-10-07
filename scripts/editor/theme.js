/* ธีมสว่าง/มืด — ใช้ร่วมกันทั้งหน้าแรกและ editor · โหลดใน <head> ก่อน CSS วาด กันจอกระพริบ */
(function () {
  var KEY = "clipcut.theme", t = "dark";
  try { t = localStorage.getItem(KEY) || "dark"; } catch (e) { /* โหมดส่วนตัว = มืด */ }
  document.documentElement.dataset.theme = t;
  window.toggleTheme = function () {
    var n = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = n;
    try { localStorage.setItem(KEY, n); } catch (e) { /* ไม่เป็นไร */ }
    var b = document.getElementById("btnTheme"); if (b) b.textContent = n === "light" ? "ธีมมืด" : "ธีมสว่าง";
    if (window.drawWave) window.drawWave();
  };
  document.addEventListener("DOMContentLoaded", function () {
    var b = document.getElementById("btnTheme");
    if (b) { b.textContent = t === "light" ? "ธีมมืด" : "ธีมสว่าง"; b.onclick = window.toggleTheme; }
  });
})();
