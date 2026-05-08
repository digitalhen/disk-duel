// Copy-button handler. Delegated so it works for any element with [data-copy].
document.addEventListener("click", (e) => {
    const btn = e.target.closest(".copy-btn[data-copy]");
    if (!btn) return;

    const text = btn.dataset.copy;
    const done = () => {
        const orig = btn.textContent;
        btn.textContent = "Copied";
        btn.classList.add("copied");
        setTimeout(() => {
            btn.textContent = orig;
            btn.classList.remove("copied");
        }, 1400);
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done).catch(() => {
            fallbackCopy(text);
            done();
        });
    } else {
        fallbackCopy(text);
        done();
    }
});

function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-1000px";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (_) {}
    ta.remove();
}
