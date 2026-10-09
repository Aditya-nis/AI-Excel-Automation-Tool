// AI Power BI + Data Cleaning + MIS Report Engine JS Helpers

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

const CSRF_TOKEN = getCookie('csrftoken');

function showToast(message, isError = false) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = message;
  t.style.background = isError ? '#ef4444' : '#0f172a';
  t.style.display = 'block';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => {
    t.style.display = 'none';
  }, 4000);
}

async function apiRequest(url, method = 'GET', data = null) {
  const options = {
    method: method,
    headers: {
      'X-CSRFToken': CSRF_TOKEN,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    }
  };
  if (data && method !== 'GET') {
    options.body = JSON.stringify(data);
  }
  try {
    const response = await fetch(url, options);
    const resData = await response.json();
    if (!response.ok) {
      throw new Error(resData.error || resData.detail || 'API request failed');
    }
    return resData;
  } catch (err) {
    showToast(err.message, true);
    throw err;
  }
}

function switchWorkspace(workspaceId) {
  if (!workspaceId) return;
  apiRequest(`/api/v1/workspaces/${workspaceId}/switch/`, 'POST')
    .then(() => {
      window.location.reload();
    })
    .catch(err => showToast(err.message, true));
}

function openModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.add('active');
}

function closeModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.remove('active');
}

// Render Chart Helper using Chart.js
function renderChart(canvasId, type, labels, data, labelTitle = 'Metric') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  
  if (window._charts && window._charts[canvasId]) {
    window._charts[canvasId].destroy();
  }
  if (!window._charts) window._charts = {};

  const colors = [
    '#4f46e5', '#0ea5e9', '#10b981', '#f59e0b',
    '#ef4444', '#8b5cf6', '#64748b', '#14b8a6'
  ];

  window._charts[canvasId] = new Chart(ctx, {
    type: type,
    data: {
      labels: labels,
      datasets: [{
        label: labelTitle,
        data: data,
        backgroundColor: type === 'pie' || type === 'doughnut' ? colors : '#4f46e5',
        borderColor: type === 'line' ? '#4f46e5' : undefined,
        tension: 0.25,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: type === 'pie' || type === 'doughnut',
          position: 'bottom'
        }
      },
      scales: (type === 'pie' || type === 'doughnut') ? {} : {
        y: {
          beginAtZero: true,
          grid: { color: '#f1f5f9' }
        },
        x: {
          grid: { display: false }
        }
      }
    }
  });
  return window._charts[canvasId];
}

// Dark Mode Toggle & Persistence
function initTheme() {
  const savedTheme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeIcon(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.innerHTML = theme === 'dark' ? '☀️' : '🌙';
    btn.setAttribute('title', theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode');
  }
}

// User Menu Dropdown Toggle
function toggleUserMenu(event) {
  if (event) event.stopPropagation();
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) menu.classList.toggle('active');
}

// Close dropdown on clicking outside
document.addEventListener('click', function(e) {
  const menu = document.getElementById('user-dropdown-menu');
  if (menu && menu.classList.contains('active')) {
    if (!e.target.closest('.user-menu-container')) {
      menu.classList.remove('active');
    }
  }
});

// Update notification count badge
async function loadNotificationBadge() {
  try {
    const res = await fetch('/api/v1/notifications/');
    if (res.ok) {
      const data = await res.json();
      const notifs = Array.isArray(data) ? data : (data.results || []);
      const unread = notifs.filter(n => !n.is_read).length;
      const badge = document.getElementById('notif-badge');
      if (badge) {
        if (unread > 0) {
          badge.textContent = unread > 9 ? '9+' : unread;
          badge.style.display = 'inline-block';
        } else {
          badge.style.display = 'none';
        }
      }
    }
  } catch (err) {
    // Silent fail
  }
}

document.addEventListener('DOMContentLoaded', function() {
  initTheme();
  loadNotificationBadge();
});

