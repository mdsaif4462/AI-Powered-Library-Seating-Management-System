(function () {
  const $ = (id) => document.getElementById(id);
  const form = $('slot-form'), map = $('seat-map'), msg = $('msg');
  const bar = $('confirm-bar'), barText = $('confirm-text'), confirmBtn = $('confirm-btn');
  let selected = null;

  const pad = (h) => String(h).padStart(2, '0') + ':00';

  function show(text, type) {
    msg.innerHTML = '';
    if (!text) return;
    const div = document.createElement('div');
    div.className = 'alert alert-' + type;
    div.textContent = text;
    msg.appendChild(div);
  }

  function slotParams() {
    return {
      date: $('date').value,
      start: $('start').value,
      duration: $('duration').value,
    };
  }

  async function loadSeats() {
    selected = null;
    bar.classList.add('d-none');
    const params = new URLSearchParams({
      ...slotParams(),
      power: $('pref-power').checked ? 1 : 0,
      window: $('pref-window').checked ? 1 : 0,
      quiet: $('pref-quiet').checked ? 1 : 0,
    });
    const res = await fetch('/api/seats?' + params);
    const data = await res.json();
    if (!res.ok) { show(data.error || 'Something went wrong.', 'danger'); return; }
    show('', '');
    render(data.seats, new Set(data.recommended));
  }

  function render(seats, recommended) {
    map.innerHTML = '';
    const zones = {};
    seats.forEach((s) => (zones[s.zone] = zones[s.zone] || []).push(s));

    Object.entries(zones).forEach(([zone, list]) => {
      const wrap = document.createElement('div');
      wrap.className = 'seat-zone';
      const title = document.createElement('h6');
      const free = list.filter((s) => s.available).length;
      title.textContent = `${zone} — ${free}/${list.length} free`;
      const grid = document.createElement('div');
      grid.className = 'seat-grid';

      list.forEach((s) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'seat ' + (!s.available ? 'seat-taken'
                         : recommended.has(s.id) ? 'seat-recommended' : 'seat-available');
        btn.disabled = !s.available;
        btn.textContent = s.seat_code;
        const icons = document.createElement('small');
        icons.textContent = (s.has_power ? '⚡' : '') + (s.near_window ? '🪟' : '') + (s.is_quiet ? '🤫' : '') || '\u00a0';
        btn.appendChild(icons);
        btn.addEventListener('click', () => select(s, btn));
        grid.appendChild(btn);
      });
      wrap.append(title, grid);
      map.appendChild(wrap);
    });
  }

  function select(seat, btn) {
    document.querySelectorAll('.seat-selected').forEach((b) => b.classList.remove('seat-selected'));
    btn.classList.add('seat-selected');
    selected = seat;
    const p = slotParams();
    barText.textContent = `Seat ${seat.seat_code} (${seat.zone}) · ${p.date} · ` +
      `${pad(+p.start)}–${pad(+p.start + +p.duration)}`;
    bar.classList.remove('d-none');
  }

  confirmBtn.addEventListener('click', async () => {
    if (!selected) return;
    confirmBtn.disabled = true;
    const res = await fetch('/api/bookings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...slotParams(), seat_id: selected.id }),
    });
    const data = await res.json();
    confirmBtn.disabled = false;
    if (res.ok) { window.location.href = data.redirect; return; }
    show(data.error || 'Booking failed.', 'danger');
    loadSeats();
  });

  form.addEventListener('submit', (e) => { e.preventDefault(); loadSeats(); });
})();
