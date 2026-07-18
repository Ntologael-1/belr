// Centralisation des notifications Toasts de BEL'R
function showToast(message, type = 'success') {
    const toastEl = document.getElementById('liveToast');
    const toastMessage = document.getElementById('toastMessage');
    const toastIcon = document.getElementById('toastIcon');
    const themes = {
        'success': { bg: 'bg-success', icon: 'fa-circle-check' },
        'error': { bg: 'bg-danger', icon: 'fa-triangle-exclamation' },
        'info': { bg: 'bg-info text-dark', icon: 'fa-circle-info' },
        'warning': { bg: 'bg-warning text-dark', icon: 'fa-exclamation' }
    };
    if (!toastEl || !toastMessage || !toastIcon) return;

    // Réinitialisation
    toastEl.classList.remove('bg-success', 'bg-danger', 'bg-info', 'bg-warning', 'text-dark');
    
    // Application du thème
    const currentTheme = themes[type] || themes['success'];
    toastEl.classList.add(...currentTheme.bg.split(' '));
    toastIcon.className = `bi ${currentTheme.icon} fs-5`;
    
    toastMessage.textContent = message;
    
    const bootstrapToast = bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 4000 });
    bootstrapToast.show();
}