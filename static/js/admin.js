let authToken = localStorage.getItem('bot_auth_token') || '';
let authType = '';

window.addEventListener('load', async () => {
    await checkAuth();
    loadStats();
    loadConfig();
    setInterval(loadStats, 5000);
});

async function checkAuth() {
    try {
        const headers = authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
        const res = await fetch('/admin/api/auth-check', { headers, credentials: 'include' });
        const data = await res.json();

        if (data.authenticated) {
            authType = data.type || '';
            document.getElementById('adminLoginOverlay').style.display = 'none';
            document.getElementById('userIdentity').innerText = data.email || 'Cloudflare Admin';
            loadStats();
            loadConfig();
        } else {
            document.getElementById('adminLoginOverlay').style.display = 'flex';
        }
    } catch (e) {
        console.error('Auth check error:', e);
        document.getElementById('adminLoginOverlay').style.display = 'flex';
    }
}

async function handleAdminLogin(e) {
    e.preventDefault();
    const password = document.getElementById('adminConsolePassword').value;
    const errDiv = document.getElementById('adminLoginErr');
    errDiv.style.display = 'none';

    try {
        const res = await fetch('/admin/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });

        if (res.ok) {
            const data = await res.json();
            authToken = data.token;
            localStorage.setItem('bot_auth_token', authToken);
            document.getElementById('adminLoginOverlay').style.display = 'none';
            document.getElementById('userIdentity').innerText = data.email || 'Local Admin';
            loadStats();
            loadConfig();
        } else {
            errDiv.style.display = 'flex';
        }
    } catch (e) {
        errDiv.style.display = 'flex';
    }
}

async function loadStats() {
    try {
        const res = await fetch('/admin/api/stats');
        const data = await res.json();

        document.getElementById('mStatus').innerText = (data.status || 'online').toUpperCase();
        document.getElementById('mServers').innerText = data.server_count || 0;
        document.getElementById('mMembers').innerText = `${(data.total_members || 0).toLocaleString()} total members`;
        document.getElementById('mRam').innerText = `${data.system ? data.system.ram : 0} MB`;
        document.getElementById('mPing').innerText = `${data.latency || 0} ms`;
    } catch (e) {
        console.error('Stats error:', e);
    }
}

async function loadConfig() {
    try {
        const headers = authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
        const servRes = await fetch('/admin/api/servers', { headers });
        if (servRes.ok) {
            const servers = await servRes.json();
            
            const wSelect = document.getElementById('cfgWelcomeChannel');
            const mSelect = document.getElementById('cfgModLogChannel');
            const gSelect = document.getElementById('modGuild');

            wSelect.innerHTML = '<option value="">None (Disabled)</option>';
            mSelect.innerHTML = '<option value="">None (Disabled)</option>';
            gSelect.innerHTML = '<option value="" disabled selected>Select a server...</option>';

            servers.forEach(s => {
                const optG = document.createElement('option');
                optG.value = s.id;
                optG.innerText = `${s.name} (${s.member_count} users)`;
                gSelect.appendChild(optG);

                if (s.channels) {
                    s.channels.forEach(c => {
                        const optW = document.createElement('option');
                        optW.value = c.id;
                        optW.innerText = `${s.name} -> #${c.name}`;
                        wSelect.appendChild(optW);

                        const optM = document.createElement('option');
                        optM.value = c.id;
                        optM.innerText = `${s.name} -> #${c.name}`;
                        mSelect.appendChild(optM);
                    });
                }
            });
        }

        const confRes = await fetch('/admin/api/config', { headers });
        if (confRes.ok) {
            const cfg = await confRes.json();
            document.getElementById('cfgPrefix').value = cfg.PREFIX || '$';
            document.getElementById('cfgMutedRole').value = cfg.MUTED_ROLE_NAME || 'Muted';
            document.getElementById('cfgWelcomeChannel').value = cfg.WELCOME_CHANNEL_ID || '';
            document.getElementById('cfgModLogChannel').value = cfg.MOD_LOG_CHANNEL_ID || '';
        }
    } catch (e) {
        console.error('Config load error:', e);
    }
}

async function saveConfig(e) {
    e.preventDefault();
    const payload = {
        PREFIX: document.getElementById('cfgPrefix').value,
        MUTED_ROLE_NAME: document.getElementById('cfgMutedRole').value,
        WELCOME_CHANNEL_ID: document.getElementById('cfgWelcomeChannel').value,
        MOD_LOG_CHANNEL_ID: document.getElementById('cfgModLogChannel').value
    };

    try {
        const headers = { 'Content-Type': 'application/json' };
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

        const res = await fetch('/admin/api/config', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            alert('Settings updated successfully!');
        } else {
            alert('Failed saving configuration.');
        }
    } catch (e) {
        alert('Failed saving configuration.');
    }
}

async function savePresence(e) {
    e.preventDefault();
    const payload = {
        status: document.getElementById('pStatus').value,
        activity: document.getElementById('pActivity').value,
        text: document.getElementById('pText').value,
        rotation: false
    };
    try {
        const headers = { 'Content-Type': 'application/json' };
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

        const res = await fetch('/admin/api/presence', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload)
        });
        if (res.ok) alert('Presence updated on Discord!');
    } catch (e) {
        alert('Failed updating presence.');
    }
}

async function runModAction(e) {
    e.preventDefault();
    const payload = {
        guild_id: document.getElementById('modGuild').value,
        action: document.getElementById('modAction').value,
        user_id: document.getElementById('modUser').value,
        reason: document.getElementById('modReason').value
    };
    try {
        const headers = { 'Content-Type': 'application/json' };
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

        const res = await fetch('/admin/api/mod/action', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Action successful: ${data.message}`);
            document.getElementById('modUser').value = '';
            document.getElementById('modReason').value = '';
            loadGuildWarnings();
        } else {
            alert(`Failed: ${data.message}`);
        }
    } catch (e) {
        alert('Moderation action failed.');
    }
}

async function loadGuildWarnings() {
    const guildId = document.getElementById('modGuild').value;
    const list = document.getElementById('warningsAuditList');
    if (!guildId) return;

    try {
        const headers = authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
        const res = await fetch(`/admin/api/mod/warnings?guild_id=${guildId}`, { headers });
        if (res.ok) {
            const data = await res.json();
            if (!data.warnings || data.warnings.length === 0) {
                list.innerHTML = '<p style="color: var(--text-muted); padding: 5px;">No active warnings in this server 🎉</p>';
                return;
            }
            list.innerHTML = '';
            data.warnings.forEach(w => {
                const item = document.createElement('div');
                item.style.cssText = 'background: var(--bg-input); padding: 10px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;';
                item.innerHTML = `
                    <div>
                        <strong>${w.user_name}</strong> (<code>${w.user_id}</code>)
                    </div>
                    <div>
                        <span style="background: var(--color-red); color: #fff; padding: 2px 8px; border-radius: 10px; font-weight: 700; font-size: 0.8rem;">⚠️ ${w.count}</span>
                    </div>
                `;
                list.appendChild(item);
            });
        }
    } catch (e) {
        list.innerHTML = '<p style="color: var(--color-red)">Failed loading warnings.</p>';
    }
}

function logoutAdmin() {
    localStorage.removeItem('bot_auth_token');
    authToken = '';
    // A Cloudflare Access session lives in the CF_Authorization cookie, not in
    // localStorage. Clearing the local token alone would leave the Access session
    // active and let the next visit to /admin straight back in, so hand off to
    // Cloudflare's own logout endpoint to actually end the session.
    if (authType === 'cloudflare') {
        window.location.href = '/cdn-cgi/access/logout';
        return;
    }
    window.location.href = '/';
}
