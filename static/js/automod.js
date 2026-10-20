// Auto-mod panel. Shares the auth token and API mount picked in admin.js, which
// loads first; everything here is additive to that page.

function amHeaders(json) {
    const headers = json ? { 'Content-Type': 'application/json' } : {};
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    return headers;
}

function amList(value) {
    return (value || '')
        .split(',')
        .map(v => v.trim().toLowerCase())
        .filter(Boolean);
}

async function loadAutomod() {
    try {
        const res = await fetch(`${API}/automod`, { headers: amHeaders(false) });
        if (!res.ok) return;
        const data = await res.json();
        const cfg = data.config || {};

        const setVal = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value;
        };
        const setChecked = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.checked = !!value;
        };

        setChecked('amEnabled', cfg.enabled);
        updateEnabledLabel(cfg.enabled);
        setVal('amThreshold', cfg.scam_threshold);
        setVal('amAction', cfg.scam_action || 'timeout');
        setVal('amTimeout', cfg.scam_timeout_minutes);
        setVal('amRateLimit', cfg.rate_limit);
        setVal('amRateWindow', cfg.rate_window);
        setVal('amDuplicate', cfg.duplicate_limit);
        setVal('amCrosspost', cfg.crosspost_limit);
        setVal('amMentions', cfg.mention_limit);
        setVal('amNewAccount', cfg.new_account_days);
        setVal('amImageDupe', cfg.image_dupe_limit);
        setVal('amImageRaid', cfg.image_raid_accounts);
        setChecked('amImageChecks', cfg.image_checks);
        setChecked('amDeepHash', cfg.image_deep_hash);
        setVal('amBlockDomains', (cfg.block_domains || []).join(', '));
        setVal('amAllowDomains', (cfg.allow_domains || []).join(', '));
        setVal('amKeywords', (cfg.extra_keywords || []).join(', '));
        setChecked('amInvites', cfg.block_invites);
        setChecked('amMassMentions', cfg.block_mass_mentions);
        setChecked('amPurge', cfg.purge_on_scam);
        setChecked('amBanRepeat', cfg.ban_on_repeat);

        const mode = document.getElementById('amHashMode');
        if (mode) {
            mode.textContent = data.pil_available
                ? '(perceptual)'
                : '(metadata only — Pillow not installed)';
        }

        const statsLabel = document.getElementById('amStatsLabel');
        if (statsLabel && data.stats) {
            statsLabel.textContent =
                `${data.stats.tracked_users} tracked · ${data.stats.flagged_users} flagged`
                + ` · ${data.stats.tracked_images || 0} images`
                + ` · ${data.blocked_images || 0} blocked`;
        }

        renderAutomodSignals(data.signals || [], cfg.disabled_signals || []);
        renderAutomodHits(data.recent || []);
    } catch (e) {
        console.error('Auto-mod load error:', e);
    }
}

function updateEnabledLabel(on) {
    const label = document.getElementById('amEnabledLabel');
    if (!label) return;
    label.textContent = on ? 'Enabled' : 'Disabled';
    label.style.color = on ? 'var(--color-emerald)' : 'var(--text-muted)';
}

// A checkbox per scoring category. Checked = the signal counts toward the score;
// unchecked lands in disabled_signals, for wording that is normal in this server.
function renderAutomodSignals(signals, disabled) {
    const host = document.getElementById('amSignals');
    if (!host) return;

    const off = new Set((disabled || []).map(s => String(s).toLowerCase()));
    host.textContent = '';

    signals.forEach(signal => {
        const row = document.createElement('label');

        const box = document.createElement('input');
        box.type = 'checkbox';
        box.dataset.signal = signal.label;
        box.className = 'am-signal';
        box.checked = !off.has(signal.label.toLowerCase());

        const name = document.createElement('span');
        name.textContent = signal.label;

        const weight = document.createElement('span');
        weight.className = 'signal-weight';
        weight.textContent = `+${signal.weight}`;

        row.appendChild(box);
        row.appendChild(name);
        row.appendChild(weight);
        host.appendChild(row);
    });
}

// Every field here originates in Discord (usernames, channel names, message text),
// so each one is written with textContent — never innerHTML.
function renderAutomodHits(hits) {
    const list = document.getElementById('amRecentList');
    if (!list) return;
    list.textContent = '';

    if (!hits.length) {
        const empty = document.createElement('p');
        empty.style.color = 'var(--text-muted)';
        empty.style.fontSize = '0.85rem';
        empty.textContent = 'No auto-mod actions recorded yet.';
        list.appendChild(empty);
        return;
    }

    hits.forEach(hit => {
        const row = document.createElement('div');
        row.className = `automod-hit is-${hit.action}`;

        const top = document.createElement('div');
        top.className = 'hit-top';
        const who = document.createElement('span');
        who.textContent = hit.user;
        const what = document.createElement('span');
        what.textContent = `${hit.action} · score ${hit.score}`;
        top.appendChild(who);
        top.appendChild(what);

        const reason = document.createElement('div');
        reason.style.fontSize = '0.8rem';
        reason.style.color = 'var(--text-secondary)';
        reason.textContent = hit.reason;

        const meta = document.createElement('div');
        meta.className = 'hit-meta';
        meta.textContent = `${hit.time} · ${hit.guild} #${hit.channel}`;

        row.appendChild(top);
        row.appendChild(reason);
        row.appendChild(meta);
        list.appendChild(row);
    });
}

// Blocked images are per guild, so this follows the Moderation Console's server
// picker rather than having a second one. Values come from Discord moderators,
// so every one is written with textContent.
async function loadBlockedImages() {
    const list = document.getElementById('amBlockedList');
    if (!list) return;
    const guildId = (document.getElementById('modGuild') || {}).value;

    const message = text => {
        list.textContent = '';
        const p = document.createElement('p');
        p.style.cssText = 'color: var(--text-muted); font-size: 0.8rem;';
        p.textContent = text;
        list.appendChild(p);
    };

    if (!guildId) {
        message('Select a server in the Moderation Console to load its blocked images.');
        return;
    }

    try {
        const res = await fetch(`${API}/automod/blocked?guild_id=${encodeURIComponent(guildId)}`,
                                { headers: amHeaders(false) });
        if (!res.ok) { message('Failed loading blocked images.'); return; }
        const entries = await res.json();

        if (!entries.length) {
            message('None yet — reply to a scam post with $automod blockimage.');
            return;
        }

        list.textContent = '';
        entries.slice().reverse().forEach(entry => {
            const row = document.createElement('div');
            row.className = 'automod-hit is-delete';

            const top = document.createElement('div');
            top.className = 'hit-top';
            const note = document.createElement('span');
            note.textContent = entry.note || 'no note';
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'btn-unblock';
            remove.textContent = 'Unblock';
            remove.onclick = () => unblockImage(guildId, entry.id);
            top.appendChild(note);
            top.appendChild(remove);

            const meta = document.createElement('div');
            meta.className = 'hit-meta';
            meta.textContent = `#${entry.id} · by ${entry.moderator || 'unknown'}`;

            row.appendChild(top);
            row.appendChild(meta);
            list.appendChild(row);
        });
    } catch (e) {
        message('Failed loading blocked images.');
    }
}

async function unblockImage(guildId, id) {
    try {
        const res = await fetch(`${API}/automod/blocked/remove`, {
            method: 'POST',
            headers: amHeaders(true),
            body: JSON.stringify({ guild_id: guildId, id }),
        });
        if (res.ok) loadBlockedImages();
        else alert('Failed to unblock that image.');
    } catch (e) {
        alert('Failed to unblock that image.');
    }
}

async function saveAutomod(e) {
    e.preventDefault();
    const num = id => Number(document.getElementById(id).value);
    const disabledSignals = Array.from(document.querySelectorAll('.am-signal'))
        .filter(box => !box.checked)
        .map(box => box.dataset.signal);

    const payload = {
        enabled: document.getElementById('amEnabled').checked,
        scam_threshold: num('amThreshold'),
        scam_action: document.getElementById('amAction').value,
        disabled_signals: disabledSignals,
        scam_timeout_minutes: num('amTimeout'),
        rate_limit: num('amRateLimit'),
        rate_window: num('amRateWindow'),
        duplicate_limit: num('amDuplicate'),
        crosspost_limit: num('amCrosspost'),
        mention_limit: num('amMentions'),
        new_account_days: num('amNewAccount'),
        image_dupe_limit: num('amImageDupe'),
        image_raid_accounts: num('amImageRaid'),
        image_checks: document.getElementById('amImageChecks').checked,
        image_deep_hash: document.getElementById('amDeepHash').checked,
        block_domains: amList(document.getElementById('amBlockDomains').value),
        allow_domains: amList(document.getElementById('amAllowDomains').value),
        extra_keywords: amList(document.getElementById('amKeywords').value),
        block_invites: document.getElementById('amInvites').checked,
        block_mass_mentions: document.getElementById('amMassMentions').checked,
        purge_on_scam: document.getElementById('amPurge').checked,
        ban_on_repeat: document.getElementById('amBanRepeat').checked,
    };

    try {
        const res = await fetch(`${API}/automod`, {
            method: 'POST',
            headers: amHeaders(true),
            body: JSON.stringify(payload),
        });
        if (res.ok) {
            updateEnabledLabel(payload.enabled);
            alert('Anti-spam filter updated!');
            loadAutomod();
        } else {
            alert('Failed saving the anti-spam filter.');
        }
    } catch (err) {
        alert('Failed saving the anti-spam filter.');
    }
}

async function testAutomod() {
    const input = document.getElementById('amTestText');
    const out = document.getElementById('amTestResult');
    if (!input || !out) return;

    const text = input.value.trim();
    if (!text) {
        out.textContent = 'Type a message to score it.';
        return;
    }

    out.textContent = 'Scoring...';
    try {
        const res = await fetch(`${API}/automod/test`, {
            method: 'POST',
            headers: amHeaders(true),
            body: JSON.stringify({ text, attachments: 1 }),
        });
        if (!res.ok) {
            out.textContent = 'Test failed.';
            return;
        }
        const data = await res.json();

        out.textContent = '';
        const box = document.createElement('div');
        box.className = `automod-verdict ${data.blocked ? 'is-blocked' : 'is-clean'}`;

        const verdict = document.createElement('div');
        verdict.style.fontWeight = '600';
        verdict.style.color = data.blocked ? 'var(--color-red)' : 'var(--color-emerald)';
        verdict.textContent = data.blocked
            ? `Would be removed — score ${data.score} / ${data.threshold}`
            : `Would pass — score ${data.score} / ${data.threshold}`;

        const why = document.createElement('div');
        why.style.marginTop = '4px';
        why.style.color = 'var(--text-muted)';
        why.textContent = data.reasons.length ? data.reasons.join(', ') : 'no signals matched';

        box.appendChild(verdict);
        box.appendChild(why);
        out.appendChild(box);
    } catch (err) {
        out.textContent = 'Test failed.';
    }
}

window.addEventListener('load', () => {
    const toggle = document.getElementById('amEnabled');
    if (toggle) toggle.addEventListener('change', () => updateEnabledLabel(toggle.checked));
    loadAutomod();
    setInterval(loadAutomod, 15000);

    const guildPicker = document.getElementById('modGuild');
    if (guildPicker) guildPicker.addEventListener('change', loadBlockedImages);
});
