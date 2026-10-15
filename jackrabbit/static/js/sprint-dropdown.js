// Dropdown handling for the "Move to Sprint" control (loaded from base.html;
// no inline <script> in base.html per the coding standards).
document.addEventListener('click', function(event) {
    // Close dropdowns when clicking outside
    if (!event.target.closest('[id^="move-to-sprint-"]')) {
        document.querySelectorAll('[id^="move-to-sprint-dropdown-"]').forEach(function(dropdown) {
            dropdown.classList.add('hidden');
        });
        document.querySelectorAll('[id^="move-to-sprint-"]').forEach(function(btn) {
            btn.setAttribute('aria-expanded', 'false');
        });
    }
});

// Toggle dropdown
document.addEventListener('click', function(event) {
    const btn = event.target.closest('[id^="move-to-sprint-"]:not([id^="move-to-sprint-dropdown-"])');
    if (btn) {
        const ticketId = btn.id.replace('move-to-sprint-', '');
        const dropdown = document.getElementById('move-to-sprint-dropdown-' + ticketId);
        if (dropdown) {
            const isHidden = dropdown.classList.contains('hidden');
            // Close all other dropdowns first
            document.querySelectorAll('[id^="move-to-sprint-dropdown-"]').forEach(function(d) {
                d.classList.add('hidden');
            });
            document.querySelectorAll('[id^="move-to-sprint-"]').forEach(function(b) {
                b.setAttribute('aria-expanded', 'false');
            });
            // Toggle this one
            if (isHidden) {
                dropdown.classList.remove('hidden');
                btn.setAttribute('aria-expanded', 'true');
            } else {
                dropdown.classList.add('hidden');
                btn.setAttribute('aria-expanded', 'false');
            }
        }
    }
});
