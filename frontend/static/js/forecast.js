(function () {
  const input = document.getElementById('forecast-date');
  const tip = document.getElementById('forecast-tip');
  let chart;

  const color = (v) => (v < 50 ? '#198754' : v < 80 ? '#ffc107' : '#dc3545');
  const label = (h) => String(h).padStart(2, '0') + ':00';

  async function load() {
    const res = await fetch('/api/forecast?date=' + input.value);
    const data = await res.json();
    if (!res.ok) return;
    const labels = data.forecast.map((r) => label(r.hour));
    const values = data.forecast.map((r) => r.occupancy);

    tip.textContent = `Quietest time: ${label(data.best_hour)} · Busiest: ${label(data.peak_hour)}`;
    tip.classList.remove('d-none');

    if (chart) chart.destroy();
    chart = new Chart(document.getElementById('forecastChart'), {
      type: 'bar',
      data: { labels, datasets: [{ label: 'Predicted occupancy (%)', data: values,
                                   backgroundColor: values.map(color), borderRadius: 4 }] },
      options: { scales: { y: { min: 0, max: 100, title: { display: true, text: '% of seats' } } },
                 plugins: { legend: { display: false } } },
    });
  }

  input.addEventListener('change', load);
  load();
})();
