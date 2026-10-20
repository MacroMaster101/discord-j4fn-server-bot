// Server-admin dashboard. Everything here is scoped to one guild: the id goes
// with every request and the server checks it against the signed-in user's own
// server list. Values come from Discord, so they are written with textContent.

const API = '/api';
let ME = null;
let GUILD = '';
let SIGNALS = [];

window.addEventListener('load', init);

async function init() {
    const error = new URLSearchParams(location.search).get('error');
    if (error) showGateError(error);

    try {
        const res = await fetch(`${API}/me`, { credentials: 'include' });
        ME = await res.json();
    } catch (e) {
        showGateError('network');
        return;
    }

    if (!ME.authenticated) {
        if (ME.oauth_enabled === false) {
            document.getElementById('signInBtn').style.display = 'none';
            document.getElementById('signInBlurb').textContent =
                'Discord sign-in is not configured on this bot yet.';
        }
        return;
    }
    if (!ME.guilds || !ME.guilds.length) {
        showGateError('noservers');
        return;
    }

    document.getElementById('signInGate').hidden = true;
    document.getElementById('dashNav').hidden = false;
    document.getElementById('dashMain').hidden = false;

    const who = document.getElementById('whoami');
    who.textContent = ME.owner ? `${ME.username} (owner)` : ME.username;

    const picker = document.getElementById('guildPicker');
    picker.textContent = '';
    ME.guilds.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.id;
        opt.textContent = g.name;
        picker.appendChild(opt);
    });
    picker.addEventListener('change', () => selectGuild(picker.value));

    const enabled = document.getElementById('dEnabled');
    enabled.addEventListener('change', () => {
        const label = document.getElementById('dEnabledLabel');
        label.textContent = enabled.checked ? 'Enabled' : 'Disabled';
        label.style.color = enabled.checked
            ? 'var(--color-emerald)' : 'var(--text-muted)';
    });

    selectGuild(ME.guilds[0].id);
}

function showGateError(code) {
    const messages = {
        state: 'That sign-in link expired. Please try again.',
        denied: 'Sign-in was cancelled.',
        nocode: 'Discord did not return a sign-in code.',
        discord: 'Could not reach Discord. Please try again shortly.',
        noservers: 'You do not run any server that this bot is in.',
        network: 'Could not reach the bot.',
    };
    const box = document.getElementById('signInError');
    box.textContent = messages[code] || 'Something went wrong signing in.';
    box.style.display = 'block';
}

function selectGuild(id) {
    GUILD = id;
    loadGuildAutomod();
    loadBlocked();
    loadWarnings();
}

function headers(json) {
    return json ? { 'Content-Type': 'application/json' } : {};
}

function emptyNote(host, text) {
    host.textContent = '';
    const p = document.createElement('p');
    p.style.cssText = 'color: var(--text-muted); font-size: 0.8rem;';
    p.textContent = text;
    host.appendChild(p);
}

async function loadGuildAutomod() {
    const res = await fetch(`${API}/automod?guild_id=${encodeURIComponent(GUILD)}`,
                            { credentials: 'include' });
    if (!res.ok) return;
    const data = await res.json();
    const cfg = data.config || {};
    SIGNALS = data.signals || [];

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    const tick = (id, v) => { const el = document.getElementById(id); if (el) el.checked = !!v; };

    tick('dEnabled', cfg.enabled);
    document.getElementById('dEnabled').dispatchEvent(new Event('change'));
    set('dThreshold', cfg.scam_threshold);
    set('dAction', cfg.scam_action || 'timeout');
    set('dTimeout', cfg.scam_timeout_minutes);
    set('dRate', cfg.rate_limit);
    set('dBlockDomains', (cfg.block_domains || []).join(', '));
    set('dKeywords', (cfg.extra_keywords || []).join(', '));
    tick('dInvites', cfg.block_invites);
    tick('dMentions', cfg.block_mass_mentions);
    tick('dImages', cfg.image_checks);
    tick('dBanRepeat', cfg.ban_on_repeat);

    const overrides = Object.keys(data.overrides || {}).length;
    document.getElementById('dOverrideCount').textContent =
        overrides ? `${overrides} setting(s) customised` : 'using defaults';

    renderSignals(SIGNALS, cfg.disabled_signals || []);
    renderRecent(data.recent || []);
}

function renderSignals(signals, disabled) {
    const host = document.getElementById('dSignals');
    const off = new Set((disabled || []).map(s => String(s).toLowerCase()));
    host.textContent = '';
    signals.forEach(sig => {
        const row = document.createElement('label');
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.className = 'd-signal';
        box.dataset.signal = sig.label;
        box.checked = !off.has(sig.label.toLowerCase());
        const name = document.createElement('span');
        name.textContent = sig.label;
        row.appendChild(box);
        row.appendChild(name);
        host.appendChild(row);
    });
}

function renderRecent(hits) {
    const host = document.getElementById('dRecent');
    if (!hits.length) return emptyNote(host, 'No auto-mod actions in this server yet.');
    host.textContent = '';
    hits.forEach(hit => {
        const row = document.createElement('div');
        row.className = `automod-hit is-${hit.action}`;
        const top = document.createElement('div');
        top.className = 'hit-top';
        const who = document.createElement('span');
        who.textContent = hit.user;
        const what = document.createElement('span');
        what.textContent = `${hit.action} · ${hit.score}`;
        top.appendChild(who); top.appendChild(what);
        const why = document.createElement('div');
        why.style.cssText = 'font-size: 0.8rem; color: var(--text-secondary);';
        why.textContent = hit.reason;
        const meta = document.createElement('div');
        meta.className = 'hit-meta';
        meta.textContent = `${hit.time} · #${hit.channel}`;
        row.appendChild(top); row.appendChild(why); row.appendChild(meta);
        host.appendChild(row);
    });
}

async function saveGuildAutomod(e) {
    e.preventDefault();
    const num = id => Number(document.getElementById(id).value);
    const list = id => document.getElementById(id).value
        .split(',').map(v => v.trim().toLowerCase()).filter(Boolean);

    const payload = {
        guild_id: GUILD,
        enabled: document.getElementById('dEnabled').checked,
        scam_threshold: num('dThreshold'),
        scam_action: document.getElementById('dAction').value,
        scam_timeout_minutes: num('dTimeout'),
        rate_limit: num('dRate'),
        block_domains: list('dBlockDomains'),
        extra_keywords: list('dKeywords'),
        block_invites: document.getElementById('dInvites').checked,
        block_mass_mentions: document.getElementById('dMentions').checked,
        image_checks: document.getElementById('dImages').checked,
        ban_on_repeat: document.getElementById('dBanRepeat').checked,
        disabled_signals: Array.from(document.querySelectorAll('.d-signal'))
            .filter(b => !b.checked).map(b => b.dataset.signal),
    };

    const res = await fetch(`${API}/automod`, {
        method: 'POST', credentials: 'include',
        headers: headers(true), body: JSON.stringify(payload),
    });
    if (res.ok) { alert('Saved.'); loadGuildAutomod(); }
    else alert('Could not save those settings.');
}

async function resetGuildAutomod() {
    if (!confirm('Reset this server to the bot defaults?')) return;
    const payload = { guild_id: GUILD, reset: true };
    const res = await fetch(`${API}/automod/reset`, {
        method: 'POST', credentials: 'include',
        headers: headers(true), body: JSON.stringify(payload),
    });
    if (res.ok) loadGuildAutomod();
    else alert('Could not reset this server.');
}

async function testGuildMessage() {
    const text = document.getElementById('dTestText').value.trim();
    const out = document.getElementById('dTestResult');
    if (!text) { out.textContent = 'Type a message to score it.'; return; }

    const res = await fetch(`${API}/automod/test`, {
        method: 'POST', credentials: 'include', headers: headers(true),
        body: JSON.stringify({ guild_id: GUILD, text, attachments: 1 }),
    });
    if (!res.ok) { out.textContent = 'Test failed.'; return; }
    const d = await res.json();

    out.textContent = '';
    const box = document.createElement('div');
    box.className = `automod-verdict ${d.blocked ? 'is-blocked' : 'is-clean'}`;
    const verdict = document.createElement('div');
    verdict.style.fontWeight = '600';
    verdict.style.color = d.blocked ? 'var(--color-red)' : 'var(--color-emerald)';
    verdict.textContent = `${d.blocked ? 'Would be removed' : 'Would pass'} — score ${d.score} / ${d.threshold}`;
    const why = document.createElement('div');
    why.style.cssText = 'margin-top: 4px; color: var(--text-muted);';
    why.textContent = d.reasons.length ? d.reasons.join(', ') : 'no signals matched';
    box.appendChild(verdict); box.appendChild(why);
    out.appendChild(box);
}

async function loadBlocked() {
    const host = document.getElementById('dBlocked');
    const res = await fetch(`${API}/automod/blocked?guild_id=${encodeURIComponent(GUILD)}`,
                            { credentials: 'include' });
    if (!res.ok) return emptyNote(host, 'Could not load blocked images.');
    const entries = await res.json();
    if (!entries.length) {
        return emptyNote(host, 'None yet — reply to a scam post with $automod blockimage.');
    }
    host.textContent = '';
    entries.slice().reverse().forEach(entry => {
        const row = document.createElement('div');
        row.className = 'automod-hit is-delete';
        const top = document.createElement('div');
        top.className = 'hit-top';
        const note = document.createElement('span');
        note.textContent = entry.note || 'no note';
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'btn-unblock'; btn.textContent = 'Unblock';
        btn.onclick = () => unblock(entry.id);
        top.appendChild(note); top.appendChild(btn);
        const meta = document.createElement('div');
        meta.className = 'hit-meta';
        meta.textContent = `#${entry.id} · by ${entry.moderator || 'unknown'}`;
        row.appendChild(top); row.appendChild(meta);
        host.appendChild(row);
    });
}

async function unblock(id) {
    const res = await fetch(`${API}/automod/blocked/remove`, {
        method: 'POST', credentials: 'include', headers: headers(true),
        body: JSON.stringify({ guild_id: GUILD, id }),
    });
    if (res.ok) loadBlocked(); else alert('Could not unblock that image.');
}

async function loadWarnings() {
    const host = document.getElementById('dWarnings');
    const res = await fetch(`${API}/mod/warnings?guild_id=${encodeURIComponent(GUILD)}`,
                            { credentials: 'include' });
    if (!res.ok) return emptyNote(host, 'Could not load warnings.');
    const data = await res.json();
    const rows = Array.isArray(data) ? data : (data.warnings || []);
    if (!rows.length) return emptyNote(host, 'No warnings on record.');

    host.textContent = '';
    rows.slice(0, 40).forEach(w => {
        const row = document.createElement('div');
        row.className = 'automod-hit is-delete';
        const top = document.createElement('div');
        top.className = 'hit-top';
        const who = document.createElement('span');
        who.textContent = w.user || w.user_id || 'unknown';
        const count = document.createElement('span');
        count.textContent = w.count ? `${w.count} warning(s)` : '';
        top.appendChild(who); top.appendChild(count);
        row.appendChild(top);
        if (w.reason) {
            const why = document.createElement('div');
            why.style.cssText = 'font-size: 0.8rem; color: var(--text-secondary);';
            why.textContent = w.reason;
            row.appendChild(why);
        }
        host.appendChild(row);
    });
}

async function runGuildModAction(e) {
    e.preventDefault();
    const payload = {
        guild_id: GUILD,
        action: document.getElementById('dModAction').value,
        user: document.getElementById('dModUser').value.trim(),
        reason: document.getElementById('dModReason').value,
    };
    if (!confirm(`${payload.action} ${payload.user} in this server?`)) return;

    const res = await fetch(`${API}/mod/action`, {
        method: 'POST', credentials: 'include',
        headers: headers(true), body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    alert(res.ok ? (body.message || 'Done.') : (body.message || 'That action failed.'));
    if (res.ok) { loadWarnings(); document.getElementById('dModForm').reset(); }
}
