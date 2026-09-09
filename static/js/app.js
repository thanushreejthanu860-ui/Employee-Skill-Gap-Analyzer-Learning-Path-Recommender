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
    new Chart(departmentCanvas, {type:'bar', data:{labels:data.departments.map(item=>item.department), datasets:[{label:'Readiness', data:data.departments.map(item=>item.readiness), backgroundColor:'#6256d9', borderRadius:6, barThickness:24}]}, options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true,max:100,grid:{color:'#ecebf4'},ticks:{callback:value=>value+'%'}},x:{grid:{display:false}}}}});
  }
  const gapCanvas = document.getElementById('gapChart');
  if (data && gapCanvas && window.Chart) new Chart(gapCanvas, {type:'doughnut', data:{labels:data.common_gaps.map(item=>item.skill), datasets:[{data:data.common_gaps.map(item=>item.count), backgroundColor:['#6256d9','#f3a43b','#34b89b','#ee6b68','#4b9fe1','#9a8dea'], borderWidth:0}]}, options:{responsive:true, maintainAspectRatio:false, cutout:'68%', plugins:{legend:{position:'bottom',labels:{usePointStyle:true,padding:16}}}}});
});