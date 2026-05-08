// Render the comparison bar chart on dual-mode run pages.
(function () {
    const dataEl = document.getElementById("chart-data");
    if (!dataEl) return;
    const canvas = document.getElementById("chart");
    if (!canvas) return;

    const data = JSON.parse(dataEl.textContent);

    // Group by unit so MB/s, IOPS, and µs each get their own subchart.
    // Chart.js single chart with mismatched units would mislead.
    const byUnit = new Map();
    for (const t of data.tests) {
        if (!byUnit.has(t.unit)) byUnit.set(t.unit, []);
        byUnit.get(t.unit).push(t);
    }

    // Render the largest group into the existing canvas; for additional
    // unit groups, append more canvases below it.
    const groups = [...byUnit.entries()].sort((a, b) => b[1].length - a[1].length);
    const parent = canvas.parentElement;

    groups.forEach(([unit, tests], i) => {
        let target;
        if (i === 0) {
            target = canvas;
        } else {
            target = document.createElement("canvas");
            target.height = 120;
            const h = document.createElement("h3");
            h.textContent = unit;
            h.style.marginTop = "24px";
            parent.appendChild(h);
            parent.appendChild(target);
        }

        new Chart(target, {
            type: "bar",
            data: {
                labels: tests.map(t => t.name),
                datasets: [
                    {
                        label: data.label_a,
                        data: tests.map(t => t.a),
                        backgroundColor: "#58a6ff",
                    },
                    {
                        label: data.label_b,
                        data: tests.map(t => t.b),
                        backgroundColor: "#f78166",
                    },
                ],
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { labels: { color: "#c9d1d9" } },
                    title: { display: i > 0, text: unit, color: "#c9d1d9" },
                },
                scales: {
                    x: { ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
                    y: { ticks: { color: "#8b949e" }, grid: { color: "#21262d" }, title: { display: true, text: unit, color: "#8b949e" } },
                },
            },
        });
    });
})();
