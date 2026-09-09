document.addEventListener('DOMContentLoaded', () => {
  const backButton = document.getElementById('backButton');
  if (backButton) {
    if (window.history.length <= 1) backButton.hidden = true;
    backButton.addEventListener('click', () => {
      if (window.history.length > 1) window.history.back();
      else window.location.href = '/dashboard';
    });
  }
  const menu = document.getElementById('menuToggle');
  if (menu) menu.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
  const notificationButton = document.getElementById('notificationButton');
  const notificationPanel = document.getElementById('notificationPanel');
  if (notificationButton && notificationPanel) {
    notificationButton.addEventListener('click', (event) => { event.stopPropagation(); notificationPanel.classList.toggle('show'); });
    document.addEventListener('click', (event) => { if (!notificationPanel.contains(event.target)) notificationPanel.classList.remove('show'); });
    const markRead = document.getElementById('markNotificationsRead');
    if (markRead) markRead.addEventListener('click', () => { document.querySelectorAll('.notification-dot').forEach(dot => dot.hidden = true); notificationPanel.classList.remove('show'); });
  }
  const data = window.dashboardData;
  const departmentCanvas = document.getElementById('departmentChart');
  if (data && departmentCanvas && window.Chart) {
    const context = departmentCanvas.getContext('2d');
    const areaGradient = context.createLinearGradient(0, 0, 0, departmentCanvas.height || 240);
    areaGradient.addColorStop(0, 'rgba(37, 99, 235, .25)');
    areaGradient.addColorStop(1, 'rgba(37, 99, 235, 0)');
    new Chart(departmentCanvas, {
      type: 'line',
      data: {
        labels: data.departments.map(item => item.department),
        datasets: [{
          label: 'Readiness',
          data: data.departments.map(item => item.readiness),
          borderColor: '#2879ef',
          backgroundColor: areaGradient,
          pointBackgroundColor: '#fff',
          pointBorderColor: '#2879ef',
          pointBorderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
          tension: .42,
          fill: true
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: item => ` ${item.raw}% readiness` } } },
        scales: {
          y: { beginAtZero: true, max: 100, border: { display: false }, grid: { color: 'rgba(86, 143, 198, .14)' }, ticks: { color: '#537296', font: { size: 9 }, callback: value => value + '%' } },
          x: { border: { display: false }, grid: { display: false }, ticks: { color: '#537296', font: { size: 9 }, maxRotation: 0 } }
        }
      }
    });
  }
  const gapList = document.querySelector('.gap-list');
  if (data && gapList) {
    gapList.innerHTML = '<div class="gap-chart-wrap"><canvas id="gapChart"></canvas></div>';
  }
  const gapCanvas = document.getElementById('gapChart');
  if (data && gapCanvas && window.Chart) new Chart(gapCanvas, {
    type: 'doughnut',
    data: {
      labels: data.common_gaps.map(item => item.skill),
      datasets: [{ data: data.common_gaps.map(item => item.count), backgroundColor: ['#ff4e5f', '#ffb522', '#16aa9b', '#4e83f4', '#7c6cf2', '#f28ab0'], borderColor: 'rgba(255,255,255,.7)', borderWidth: 2, hoverOffset: 5 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '67%',
      rotation: -90,
      plugins: {
        legend: { position: 'right', labels: { color: '#29466d', usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 13, font: { size: 10 } } },
        tooltip: { callbacks: { label: item => ` ${item.label}: ${item.raw}` } }
      }
    }
  });
});