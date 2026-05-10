// Render sustained-write thermal charts for runs that include time-series data.
// Two charts per thermal test: bandwidth-over-time and temperature-over-time.
// Data shape (from pages.py → tojson):
//   thermal_series = [
//     { test_name, drives: [
//       { label, media_name, color_role: "a"|"b",
//         bw_samples: [[t_s, mb_s], ...],
//         temp_samples: [[t_s, c|null], ...] },
//       ...
//     ]},
//   ]
(function () {
    const dataEl = document.getElementById("thermal-data");
    if (!dataEl) return;
    const series = JSON.parse(dataEl.textContent);
    if (!Array.isArray(series) || !series.length) return;

    const colorFor = (role) => role === "b" ? "#f78166" : "#58a6ff";
    const fillFor  = (role) => role === "b"
        ? "rgba(247, 129, 102, 0.12)"
        : "rgba(88, 166, 255, 0.12)";

    const baseOptions = (yLabel) => ({
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        parsing: false,
        plugins: {
            legend: { labels: { color: "#c9d1d9" } },
            tooltip: { mode: "nearest", intersect: false },
        },
        scales: {
            x: {
                type: "linear",
                title: { display: true, text: "Time (s)", color: "#8b949e" },
                ticks: { color: "#8b949e" },
                grid:  { color: "#21262d" },
            },
            y: {
                title: { display: true, text: yLabel, color: "#8b949e" },
                ticks: { color: "#8b949e" },
                grid:  { color: "#21262d" },
                beginAtZero: yLabel.indexOf("MB/s") >= 0,
            },
        },
        interaction: { mode: "nearest", axis: "x", intersect: false },
    });

    series.forEach((entry) => {
        const bwCanvas = document.querySelector(
            `canvas.thermal-bw[data-test="${cssEscape(entry.test_name)}"]`);
        const tempCanvas = document.querySelector(
            `canvas.thermal-temp[data-test="${cssEscape(entry.test_name)}"]`);
        if (!bwCanvas && !tempCanvas) return;

        const bwDatasets = [];
        const tempDatasets = [];
        for (const d of entry.drives) {
            const c = colorFor(d.color_role);
            const f = fillFor(d.color_role);
            if (Array.isArray(d.bw_samples) && d.bw_samples.length) {
                bwDatasets.push({
                    label: d.media_name || d.label || "",
                    data: d.bw_samples.map(([t, v]) => ({ x: t, y: v })),
                    borderColor: c,
                    backgroundColor: f,
                    borderWidth: 1.4,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.1,
                });
            }
            if (Array.isArray(d.temp_samples) && d.temp_samples.length) {
                tempDatasets.push({
                    label: d.media_name || d.label || "",
                    data: d.temp_samples
                        .filter(([, v]) => v !== null && v !== undefined)
                        .map(([t, v]) => ({ x: t, y: v })),
                    borderColor: c,
                    backgroundColor: c,
                    borderWidth: 1.6,
                    pointRadius: 2,
                    fill: false,
                    tension: 0.2,
                });
            }
        }

        if (bwCanvas && bwDatasets.length) {
            new Chart(bwCanvas, {
                type: "line",
                data: { datasets: bwDatasets },
                options: baseOptions("MB/s"),
            });
        }
        if (tempCanvas && tempDatasets.length) {
            new Chart(tempCanvas, {
                type: "line",
                data: { datasets: tempDatasets },
                options: baseOptions("°C"),
            });
        }
    });

    // Tiny CSS.escape polyfill (pre-2017 Safari etc.). Modern Chart.js
    // already targets ES6, so this is just defensive.
    function cssEscape(s) {
        if (window.CSS && CSS.escape) return CSS.escape(s);
        return String(s).replace(/[^a-zA-Z0-9_-]/g, (c) => "\\" + c);
    }
})();
