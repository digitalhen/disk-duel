// Click-to-copy on .install-cmd or any [data-copy] target.
// Delegated so it works for elements added later.
document.addEventListener("click", (e) => {
    const target = e.target.closest("[data-copy]");
    if (!target) return;

    const text = target.dataset.copy;
    const flash = () => {
        target.classList.add("copied");
        setTimeout(() => target.classList.remove("copied"), 1400);
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(flash).catch(() => {
            fallbackCopy(text);
            flash();
        });
    } else {
        fallbackCopy(text);
        flash();
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
