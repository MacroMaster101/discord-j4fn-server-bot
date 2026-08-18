// Token sign-in for the public /login page. Cloudflare Access gates /admin at the
// edge, so this path deliberately talks to the ungated /api/... mount instead.

async function handleLogin(event) {
    event.preventDefault();
    const button = document.getElementById('loginBtn');
    const errBox = document.getElementById('loginErr');
    const errText = document.getElementById('loginErrText');
    const password = document.getElementById('adminPassword').value;

    errBox.style.display = 'none';
    button.disabled = true;

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        const data = await res.json().catch(() => ({}));

        if (res.ok && data.token) {
            localStorage.setItem('bot_auth_token', data.token);
            // /console is the same dashboard on a path Access does not gate.
            window.location.href = '/console';
            return;
        }

        // Surface the throttle message so a locked-out admin knows to wait rather
        // than assuming the password is wrong.
        errText.textContent = data.message || 'Invalid password. Please try again.';
        errBox.style.display = 'flex';
    } catch (e) {
        errText.textContent = 'Could not reach the server. Try again.';
        errBox.style.display = 'flex';
    } finally {
        button.disabled = false;
    }
}
