// Events page JavaScript functionality
let currentPage = 1;
let currentFilters = {};

document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadFilterOptions();
    loadEvents();
    
    // Set up event listeners
    document.getElementById('apply-filters').addEventListener('click', applyFilters);
    document.getElementById('refresh-events').addEventListener('click', () => loadEvents());
    document.getElementById('per-page').addEventListener('change', () => {
        currentPage = 1;
        loadEvents();
    });
    
    // Set default time range (last 24 hours)
    const now = new Date();
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    
    document.getElementById('start-time').value = formatDateTimeLocal(yesterday);
    document.getElementById('end-time').value = formatDateTimeLocal(now);
});

function loadFilterOptions() {
    // Load unique sources and hosts for filter dropdowns
    axios.get('/api/events?per_page=1000')
        .then(response => {
            const events = response.data.events;
            
            // Get unique sources
            const sources = [...new Set(events.map(e => e.source))].sort();
            const sourceSelect = document.getElementById('source');
            sources.forEach(source => {
                const option = document.createElement('option');
                option.value = source;
                option.textContent = source;
                sourceSelect.appendChild(option);
            });
            
            // Get unique hosts
            const hosts = [...new Set(events.map(e => e.host).filter(h => h))].sort();
            const hostSelect = document.getElementById('host');
            hosts.forEach(host => {
                const option = document.createElement('option');
                option.value = host;
                option.textContent = host;
                hostSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading filter options:', error);
        });
}

function applyFilters() {
    currentPage = 1;
    
    currentFilters = {
        event_type: document.getElementById('event-type').value,
        source: document.getElementById('source').value,
        host: document.getElementById('host').value,
        start_time: document.getElementById('start-time').value ? 
                    new Date(document.getElementById('start-time').value).toISOString() : null,
        end_time: document.getElementById('end-time').value ? 
                  new Date(document.getElementById('end-time').value).toISOString() : null,
        search: document.getElementById('search-text').value
    };
    
    // Remove empty filters
    Object.keys(currentFilters).forEach(key => {
        if (!currentFilters[key]) {
            delete currentFilters[key];
        }
    });
    
    loadEvents();
}

function loadEvents() {
    const perPage = document.getElementById('per-page').value;
    
    // Build query parameters
    const params = new URLSearchParams({
        page: currentPage,
        per_page: perPage,
        ...currentFilters
    });
    
    // Show loading spinner
    const tbody = document.getElementById('events-table');
    tbody.innerHTML = `
        <tr>
            <td colspan="6" class="text-center">
                <div class="spinner-border" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </td>
        </tr>
    `;
    
    axios.get(`/api/events?${params}`)
        .then(response => {
            const data = response.data;
            displayEvents(data.events);
            updatePagination(data.current_page, data.pages, data.total);
            document.getElementById('total-count').textContent = data.total;
        })
        .catch(error => {
            console.error('Error loading events:', error);
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-danger">
                        Error loading events: ${error.message}
                    </td>
                </tr>
            `;
        });
}

function displayEvents(events) {
    const tbody = document.getElementById('events-table');
    
    if (events.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No events found</td></tr>';
        return;
    }
    
    tbody.innerHTML = events.map(event => `
        <tr>
            <td>${formatTimestamp(event.ts)}</td>
            <td><span class="badge bg-info">${event.source}</span></td>
            <td>${event.host || 'N/A'}</td>
            <td><span class="badge bg-secondary">${event.event_type}</span></td>
            <td>${truncateText(event.message, 80)}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="showEventDetails(${event.id})">
                    <i class="fas fa-eye"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

function updatePagination(currentPage, totalPages, totalItems) {
    const paginationNav = document.getElementById('pagination-nav');
    const pagination = document.getElementById('pagination');
    
    if (totalPages <= 1) {
        paginationNav.style.display = 'none';
        return;
    }
    
    paginationNav.style.display = 'block';
    
    let paginationHTML = '';
    
    // Previous button
    if (currentPage > 1) {
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="goToPage(${currentPage - 1})">Previous</a>
            </li>
        `;
    }
    
    // Page numbers
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    if (startPage > 1) {
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="goToPage(1)">1</a>
            </li>
        `;
        if (startPage > 2) {
            paginationHTML += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        paginationHTML += `
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="goToPage(${i})">${i}</a>
            </li>
        `;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            paginationHTML += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="goToPage(${totalPages})">${totalPages}</a>
            </li>
        `;
    }
    
    // Next button
    if (currentPage < totalPages) {
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="goToPage(${currentPage + 1})">Next</a>
            </li>
        `;
    }
    
    pagination.innerHTML = paginationHTML;
}

function goToPage(page) {
    currentPage = page;
    loadEvents();
}

function showEventDetails(eventId) {
    // Find the event in the current data
    const params = new URLSearchParams({
        page: currentPage,
        per_page: document.getElementById('per-page').value,
        ...currentFilters
    });
    
    axios.get(`/api/events?${params}`)
        .then(response => {
            const event = response.data.events.find(e => e.id === eventId);
            if (event) {
                displayEventDetailsModal(event);
            }
        })
        .catch(error => {
            console.error('Error loading event details:', error);
        });
}

function displayEventDetailsModal(event) {
    const content = document.getElementById('event-details-content');
    
    content.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <h6>Basic Information</h6>
                <table class="table table-sm">
                    <tr><td><strong>ID:</strong></td><td>${event.id}</td></tr>
                    <tr><td><strong>Timestamp:</strong></td><td>${formatTimestamp(event.ts)}</td></tr>
                    <tr><td><strong>Source:</strong></td><td>${event.source}</td></tr>
                    <tr><td><strong>Host:</strong></td><td>${event.host || 'N/A'}</td></tr>
                    <tr><td><strong>Event Type:</strong></td><td>${event.event_type}</td></tr>
                </table>
            </div>
            <div class="col-md-6">
                <h6>Message</h6>
                <pre class="bg-dark p-2 rounded"><code>${event.message}</code></pre>
            </div>
        </div>
        
        ${event.metadata ? `
            <div class="row mt-3">
                <div class="col-12">
                    <h6>Metadata</h6>
                    <pre class="bg-dark p-2 rounded"><code>${JSON.stringify(event.metadata, null, 2)}</code></pre>
                </div>
            </div>
        ` : ''}
        
        ${event.enrichment ? `
            <div class="row mt-3">
                <div class="col-12">
                    <h6>Enrichment Data</h6>
                    <pre class="bg-dark p-2 rounded"><code>${JSON.stringify(event.enrichment, null, 2)}</code></pre>
                </div>
            </div>
        ` : ''}
    `;
    
    new bootstrap.Modal(document.getElementById('event-details-modal')).show();
}

function formatTimestamp(timestamp) {
    return new Date(timestamp).toLocaleString();
}

function formatDateTimeLocal(date) {
    // Format date for datetime-local input
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}
