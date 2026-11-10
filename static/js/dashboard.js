// Real-Time Dashboard & Telemetry Visualizer

let latencyChart = null;
let trafficChart = null;
let resourceChart = null;

const SLA_LATENCY_LIMIT = 100.0; // Media recommendation sub-100ms SLA target

document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    if (window.INITIAL_HISTORY && window.INITIAL_HISTORY.length > 0) {
        updateCharts(window.INITIAL_HISTORY);
    }
    // Start continuous telemetry polling
    setInterval(fetchMetrics, 2000);
});

function initCharts() {
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        plugins: {
            legend: {
                labels: { color: '#94a3b8', font: { size: 11 } }
            }
        },
        scales: {
            x: {
                grid: { color: 'rgba(51, 65, 85, 0.4)' },
                ticks: { color: '#94a3b8', maxTicksLimit: 8, font: { size: 10 } }
            },
            y: {
                grid: { color: 'rgba(51, 65, 85, 0.4)' },
                ticks: { color: '#94a3b8', font: { size: 10 } }
            }
        }
    };

    // 1. Latency Trend Chart
    const ctxLatency = document.getElementById('latencyChart').getContext('2d');
    latencyChart = new Chart(ctxLatency, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'p95 Latency (ms)',
                    data: [],
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true
                },
                {
                    label: 'Avg Latency (ms)',
                    data: [],
                    borderColor: '#22c55e',
                    borderWidth: 1.5,
                    borderDash: [4, 4],
                    tension: 0.2
                },
                {
                    label: 'SLA Limit (100ms)',
                    data: [],
                    borderColor: '#ef4444',
                    borderWidth: 1.5,
                    borderDash: [6, 6],
                    pointRadius: 0
                }
            ]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: { ...commonOptions.scales.y, min: 0, suggestedMax: 160 }
            }
        }
    });

    // 2. Traffic & Error Rate Chart
    const ctxTraffic = document.getElementById('trafficChart').getContext('2d');
    trafficChart = new Chart(ctxTraffic, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'RPS',
                    data: [],
                    borderColor: '#a855f7',
                    backgroundColor: 'rgba(168, 85, 247, 0.1)',
                    borderWidth: 2,
                    yAxisID: 'y'
                },
                {
                    label: 'Error %',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.2)',
                    borderWidth: 2,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            ...commonOptions,
            scales: {
                x: commonOptions.scales.x,
                y: {
                    ...commonOptions.scales.y,
                    position: 'left',
                    title: { display: true, text: 'RPS', color: '#94a3b8' }
                },
                y1: {
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#ef4444' },
                    title: { display: true, text: 'Error %', color: '#ef4444' },
                    min: 0,
                    suggestedMax: 15
                }
            }
        }
    });

    // 3. System Resources Chart
    const ctxResource = document.getElementById('resourceChart').getContext('2d');
    resourceChart = new Chart(ctxResource, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'CPU %',
                    data: [],
                    borderColor: '#eab308',
                    backgroundColor: 'rgba(234, 179, 8, 0.1)',
                    borderWidth: 2,
                    tension: 0.3
                },
                {
                    label: 'Memory %',
                    data: [],
                    borderColor: '#ec4899',
                    backgroundColor: 'rgba(236, 72, 153, 0.1)',
                    borderWidth: 2,
                    tension: 0.3
                }
            ]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: { ...commonOptions.scales.y, min: 0, max: 100 }
            }
        }
    });
}

function updateCharts(history) {
    if (!history || history.length === 0) return;

    const labels = history.map(d => d.time_label);
    const p95s = history.map(d => d.latency_p95_ms);
    const avgs = history.map(d => d.latency_avg_ms);
    const slaLimits = history.map(() => SLA_LATENCY_LIMIT);

    const rps = history.map(d => d.rps);
    const errors = history.map(d => d.error_rate_pct);

    const cpus = history.map(d => d.cpu_usage_pct);
    const mems = history.map(d => d.memory_usage_pct);

    // Update Latency
    latencyChart.data.labels = labels;
    latencyChart.data.datasets[0].data = p95s;
    latencyChart.data.datasets[1].data = avgs;
    latencyChart.data.datasets[2].data = slaLimits;
    latencyChart.update('none');

    // Update Traffic
    trafficChart.data.labels = labels;
    trafficChart.data.datasets[0].data = rps;
    trafficChart.data.datasets[1].data = errors;
    trafficChart.update('none');

    // Update Resources
    resourceChart.data.labels = labels;
    resourceChart.data.datasets[0].data = cpus;
    resourceChart.data.datasets[1].data = mems;
    resourceChart.update('none');
}

async function fetchMetrics() {
    try {
        const response = await fetch('/api/metrics');
        if (!response.ok) return;
        const data = await response.json();

        // Update KPIs
        const cur = data.current;
        document.getElementById('val-latency-p95').innerText = cur.latency_p95_ms;
        document.getElementById('val-latency-avg').innerText = cur.latency_avg_ms;
        document.getElementById('val-rpm').innerText = cur.rpm;
        document.getElementById('val-rps').innerText = cur.rps;
        document.getElementById('val-error-rate').innerText = cur.error_rate_pct;
        document.getElementById('val-cpu').innerText = cur.cpu_usage_pct;
        document.getElementById('val-memory').innerText = cur.memory_usage_pct;

        document.getElementById('fill-cpu').style.width = cur.cpu_usage_pct + '%';
        document.getElementById('fill-memory').style.width = cur.memory_usage_pct + '%';

        // Update SLA badge & card colors
        const slaBadge = document.getElementById('sla-badge');
        const slaStatus = document.getElementById('sla-status');
        const cardLatency = document.getElementById('card-latency');

        if (cur.latency_p95_ms > SLA_LATENCY_LIMIT) {
            slaBadge.className = 'status-pill sla-pill breached';
            slaStatus.innerText = 'SLA BREACHED (>100ms)';
            cardLatency.style.borderColor = 'var(--accent-red)';
        } else {
            slaBadge.className = 'status-pill sla-pill compliant';
            slaStatus.innerText = 'SUB-100MS OK';
            cardLatency.style.borderColor = 'var(--border-color)';
        }

        // Update version and simulation badge
        if (data.deployment_version) {
            document.getElementById('current-version').innerText = data.deployment_version;
        }
        if (data.simulation_profile) {
            document.getElementById('current-sim-badge').innerText = 'Mode: ' + data.simulation_profile.toUpperCase();
        }

        // Update Charts
        updateCharts(data.history);

        // Update Alerts Table
        renderAlerts(data.active_alerts);

    } catch (err) {
        console.error("Failed fetching telemetry:", err);
    }
}

function renderAlerts(alerts) {
    const tbody = document.getElementById('alert-table-body');
    const badge = document.getElementById('alert-count-badge');

    badge.innerText = `${alerts.length} Active`;
    if (alerts.length > 0) {
        badge.className = 'badge badge-danger';
    } else {
        badge.className = 'badge';
    }

    if (!alerts || alerts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align:center; color: var(--text-secondary); padding: 18px;">
                    ✅ All systems nominal. No active threshold alerts.
                </td>
            </tr>
        `;
        return;
    }

    let rows = '';
    for (const a of alerts) {
        const sevClass = a.severity === 'CRITICAL' ? 'sev-critical' : 'sev-warning';
        rows += `
            <tr>
                <td><span class="severity-pill ${sevClass}">${a.severity}</span></td>
                <td><strong>${a.metric_label}</strong></td>
                <td>${a.value}${a.unit}</td>
                <td>&ge; ${a.threshold}${a.unit}</td>
                <td>${a.timestamp}</td>
                <td><span style="color: ${a.severity === 'CRITICAL' ? '#ef4444' : '#eab308'}">● ACTIVE</span></td>
            </tr>
        `;
    }
    tbody.innerHTML = rows;
}

async function setSimulation(profile) {
    try {
        await fetch('/api/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile })
        });
        fetchMetrics();
    } catch (err) {
        console.error("Failed setting simulation profile:", err);
    }
}

async function clearAlerts() {
    try {
        await fetch('/api/alerts/clear', { method: 'POST' });
        fetchMetrics();
    } catch (err) {
        console.error("Failed clearing alerts:", err);
    }
}

