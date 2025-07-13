// Dashboard JavaScript functionality
let eventsTimelineChart;
let eventsTypeChart;

document.addEventListener('DOMContentLoaded', function() {
    // Load dashboard data
    loadDashboardStats();
    initializeCharts();
    
    // Set up auto-refresh every 30 seconds
    setInterval(loadDashboardStats, 30000);
    setInterval(loadRecentEvents, 15000);
});

function loadDashboardStats() {
    axios.get('/api/dashboard/stats')
        .then(response => {
            const data = response.data;
            
            // Update statistics cards
            document.getElementById('total-events').textContent = data.total_events.toLocaleString();
            document.getElementById('active-alerts').textContent = data.recent_alerts.length;
            document.getElementById('source-count').textContent = new Set(data.events_by_type.map(e => e.type)).size;
            
            // Update charts
            updateEventsTimelineChart(data.events_by_hour);
            updateEventsTypeChart(data.events_by_type);
            
            // Update recent events
            updateRecentEvents(data.recent_alerts);
            
            // Update top hosts
            updateTopHosts(data.top_hosts);
        })
        .catch(error => {
            console.error('Error loading dashboard stats:', error);
            showError('Failed to load dashboard statistics');
        });
}

function initializeCharts() {
    // Events Timeline Chart
    const timelineCtx = document.getElementById('events-timeline-chart').getContext('2d');
    eventsTimelineChart = new Chart(timelineCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Events per Hour',
                data: [],
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 253, 0.1)',
                fill: true,
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                }
            }
        }
    });
    
    // Events Type Chart
    const typeCtx = document.getElementById('events-type-chart').getContext('2d');
    eventsTypeChart = new Chart(typeCtx, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#0d6efd',
                    '#6610f2',
                    '#6f42c1',
                    '#d63384',
                    '#dc3545',
                    '#fd7e14',
                    '#ffc107',
                    '#198754',
                    '#20c997',
                    '#0dcaf0'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

function updateEventsTimelineChart(eventsData) {
    if (!eventsTimelineChart) return;
    
    const labels = eventsData.map(item => {
        const date = new Date(item.hour);
        return date.getHours() + ':00';
    });
    
    const data = eventsData.map(item => item.count);
    
    eventsTimelineChart.data.labels = labels;
    eventsTimelineChart.data.datasets[0].data = data;
    eventsTimelineChart.update();
}

function updateEventsTypeChart(eventsData) {
    if (!eventsTypeChart) return;
    
    const labels = eventsData.slice(0, 10).map(item => item.type);
    const data = eventsData.slice(0, 10).map(item => item.count);
    
    eventsTypeChart.data.labels = labels;
    eventsTypeChart.data.datasets[0].data = data;
    eventsTypeChart.update();
}

function loadRecentEvents() {
    axios.get('/api/events?per_page=5')
        .then(response => {
            const events = response.data.events;
            const tbody = document.getElementById('recent-events');
            
            if (events.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No recent events</td></tr>';
                return;
            }
            
            tbody.innerHTML = events.map(event => `
                <tr>
                    <td>${formatTimestamp(event.ts)}</td>
                    <td><span class="badge bg-info">${event.source}</span></td>
                    <td><span class="badge bg-secondary">${event.event_type}</span></td>
                    <td>${truncateText(event.message, 60)}</td>
                </tr>
            `).join('');
        })
        .catch(error => {
            console.error('Error loading recent events:', error);
        });
}

function updateRecentEvents(alerts) {
    const container = document.getElementById('recent-alerts');
    
    if (alerts.length === 0) {
        container.innerHTML = '<p class="text-muted text-center">No recent alerts</p>';
        return;
    }
    
    container.innerHTML = alerts.map(alert => `
        <div class="d-flex justify-content-between align-items-center p-2 mb-2 bg-dark rounded">
            <div>
                <strong>${alert.rule_name}</strong><br>
                <small class="text-muted">${formatTimestamp(alert.triggered_at)}</small>
            </div>
            <span class="badge bg-warning">${alert.event_count}</span>
        </div>
    `).join('');
}

function updateTopHosts(hostsData) {
    const tbody = document.getElementById('top-hosts');
    
    if (hostsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No data available</td></tr>';
        return;
    }
    
    const totalEvents = hostsData.reduce((sum, host) => sum + host.count, 0);
    
    tbody.innerHTML = hostsData.map(host => {
        const percentage = ((host.count / totalEvents) * 100).toFixed(1);
        return `
            <tr>
                <td>${host.host}</td>
                <td>${host.count.toLocaleString()}</td>
                <td>${percentage}%</td>
                <td>
                    <div class="progress" style="height: 8px;">
                        <div class="progress-bar" role="progressbar" 
                             style="width: ${percentage}%" 
                             aria-valuenow="${percentage}" 
                             aria-valuemin="0" 
                             aria-valuemax="100"></div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function formatTimestamp(timestamp) {
    return new Date(timestamp).toLocaleString();
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function showError(message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger alert-dismissible fade show';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.querySelector('main').prepend(alertDiv);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}
