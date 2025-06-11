// Toggle section collapse
function toggleSection(header) {
    header.classList.toggle('collapsed');
    const content = header.nextElementSibling;
    content.classList.toggle('collapsed');
}

// Update status display
function formatSpeed(speed) {
    return speed === 0 ? 'Unlimited' : `${speed} KB/s`;
}

function updateStatus() {
    fetch('/get_status')
        .then(response => response.json())
        .then(data => {
            const statusDiv = document.getElementById('statusDisplay');
            statusDiv.className = 'status ' + data.current_state;
            
            document.getElementById('currentState').textContent = data.current_state;
            document.getElementById('lastCheck').textContent = data.last_check;
            
            // Display current speeds
            const formatSpeed = (speed) => speed === 0 ? 'Unlimited' : `${speed} KB/s`;
            
            const uploadSpeed = data.current_upload;
            const downloadSpeed = data.current_download;
            
            document.getElementById('currentSpeed').innerHTML = `
                Current speeds: ⬆ ${formatSpeed(uploadSpeed)} | ⬇ ${formatSpeed(downloadSpeed)}
            `;
            
            // Get the last check element to insert before it
            const lastCheckElement = document.querySelector('.last-check');
            
            // Show triggered criteria if throttled
            if (data.current_state === 'throttled' && data.triggered_criteria.length > 0) {
                const criteriaText = `Triggered by: ${data.triggered_criteria.join(' and ')}`;
                let criteriaElement = document.getElementById('triggeredCriteria');
                
                if (!criteriaElement) {
                    criteriaElement = document.createElement('p');
                    criteriaElement.id = 'triggeredCriteria';
                    criteriaElement.className = 'triggered-criteria';
                    statusDiv.insertBefore(criteriaElement, lastCheckElement);
                }
                
                criteriaElement.textContent = criteriaText;
            } else {
                const criteriaElement = document.getElementById('triggeredCriteria');
                if (criteriaElement) criteriaElement.remove();
            }
        });
}

// Update status every 5 seconds
updateStatus();
setInterval(updateStatus, 5000);

// Handle form submission
document.getElementById('configForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const formData = new FormData(this);
    const data = {};
    formData.forEach((value, key) => data[key] = value);
    
    fetch('/update_config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams(data).toString()
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message);
        updateStatus();
    })
    .catch(error => {
        alert('Error saving configuration');
        console.error('Error:', error);
    });
});

// Initialize sections
document.addEventListener('DOMContentLoaded', function() {
    // Open Throttle Settings section by default
    const throttleHeader = document.querySelector('.section:nth-child(1) .section-header');
    const throttleContent = document.querySelector('.section:nth-child(1) .section-content');
    throttleHeader.classList.remove('collapsed');
    throttleContent.classList.remove('collapsed');
    
    // All other sections start collapsed
    const otherSections = document.querySelectorAll('.section:not(:nth-child(1))');
    otherSections.forEach(section => {
        const header = section.querySelector('.section-header');
        const content = section.querySelector('.section-content');
        header.classList.add('collapsed');
        content.classList.add('collapsed');
    });
});