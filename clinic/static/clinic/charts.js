// Gráficos locales: no requieren CDN ni transmitir datos a terceros.
const data = JSON.parse(document.getElementById('chart-data').textContent);
function bars(id, entries, money) {
  const root = document.getElementById(id);
  const max = Math.max(1, ...entries.map(e => e[1]));
  if (!entries.length) { root.textContent = 'Sin datos'; return; }
  for (const [label, value] of entries) {
    const button = document.createElement('button');
    button.className = 'bar'; button.style.width = `${Math.max(8, value / max * 100)}%`;
    const text = `${label}: ${money ? '$' : ''}${value.toLocaleString('es-CO')}`;
    button.textContent = text; button.title = text;
    button.onclick = () => { let out = root.querySelector('output'); if (!out) { out = document.createElement('output'); root.append(out); } out.textContent = text; };
    root.append(button);
  }
}
bars('months-chart', Object.entries(data.months), true);
bars('services-chart', data.services, false);
