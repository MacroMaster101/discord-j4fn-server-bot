window.addEventListener('load', () => {
    fetchPublicStats();
    setInterval(fetchPublicStats, 4000);
});

async function fetchPublicStats() {
    try {
        const res = await fetch('/api/public/stats');
        if (!res.ok) return;
        const data = await res.json();

        const statusEl = document.getElementById('statStatus');
        const serversEl = document.getElementById('statServers');
        const usersEl = document.getElementById('statUsers');
        const pingEl = document.getElementById('statPing');

        if (statusEl) statusEl.innerText = (data.status || 'ONLINE').toUpperCase();
        if (serversEl) serversEl.innerText = data.server_count || 0;
        if (usersEl) usersEl.innerText = (data.total_members || 0).toLocaleString();
        if (pingEl) pingEl.innerText = `${data.latency || 0} ms`;
    } catch (e) {
        console.error('Error fetching public stats:', e);
    }
}

function filterCmds(cat, btn) {
    document.querySelectorAll('.cmd-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    document.querySelectorAll('.cmd-box').forEach(box => {
        if (cat === 'all' || box.getAttribute('data-cat') === cat) {
            box.style.display = 'block';
        } else {
            box.style.display = 'none';
        }
    });
}
