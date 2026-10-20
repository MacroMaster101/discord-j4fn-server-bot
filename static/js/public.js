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

        renderServers(data.servers || []);
    } catch (e) {
        console.error('Error fetching public stats:', e);
    }
}

let lastServersKey = null;

// Anyone can invite the bot and name their server anything, so every value is set with
// textContent and icons are only loaded from Discord's CDN.
function renderServers(servers) {
    const container = document.getElementById('publicServers');
    if (!container) return;

    // Stats refresh every few seconds; skip the rebuild when nothing changed so icons
    // don't flicker.
    const key = JSON.stringify(servers);
    if (key === lastServersKey) return;
    lastServersKey = key;

    const countEl = document.getElementById('serversCount');
    if (countEl) countEl.textContent = `${servers.length.toLocaleString()} server${servers.length === 1 ? '' : 's'}`;

    container.replaceChildren();
    if (!servers.length) {
        const empty = document.createElement('div');
        empty.className = 'server-empty';
        const icon = document.createElement('i');
        icon.className = 'fa-solid fa-shield-halved';
        const title = document.createElement('strong');
        title.textContent = 'No servers joined yet';
        const hint = document.createElement('p');
        hint.textContent = 'Add the bot to your Discord server to see it featured here.';
        empty.append(icon, title, hint);
        container.appendChild(empty);
        return;
    }

    servers.forEach(s => {
        const name = s.name || 'Discord Server';
        const card = document.createElement('article');
        card.className = 'server-card';

        let icon;
        if (typeof s.icon === 'string' && s.icon.startsWith('https://cdn.discordapp.com/')) {
            icon = document.createElement('img');
            icon.src = s.icon;
            icon.alt = '';
            icon.loading = 'lazy';
            icon.referrerPolicy = 'no-referrer';
        } else {
            icon = document.createElement('div');
            icon.textContent = name.split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase() || '?';
        }
        icon.className = 'server-icon';

        const info = document.createElement('div');
        info.className = 'server-info';

        const title = document.createElement('h3');
        title.textContent = name;
        title.title = name;

        const meta = document.createElement('div');
        meta.className = 'server-meta';
        const members = document.createElement('span');
        members.textContent = `${(s.member_count || 0).toLocaleString()} members`;
        const badge = document.createElement('span');
        const online = s.online || 0;
        badge.className = online ? 'server-badge online' : 'server-badge';
        badge.textContent = online ? `${online.toLocaleString()} online` : 'Quiet';
        meta.append(members, badge);

        info.append(title, meta);
        card.append(icon, info);
        container.appendChild(card);
    });
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
