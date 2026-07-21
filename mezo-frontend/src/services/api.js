const BASE_URL = '/api';

export async function request(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const token = localStorage.getItem('mezo_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ message: 'Network error' }));
    throw new Error(errorData.message || 'API Request failed');
  }

  return response.json();
}

export const api = {
  // Auth
  login: (credentials) => request('/auth/login', { method: 'POST', body: JSON.stringify(credentials) }),
  getProfile: () => request('/auth/me'),

  // Chat
  sendMessage: (data) => request('/chat/message', { method: 'POST', body: JSON.stringify(data) }),
  getConversations: () => request('/chat/conversations'),
  
  // Files
  listFiles: (path = '') => request(`/files/list?path=${encodeURIComponent(path)}`),
  readFile: (path) => request(`/files/read?path=${encodeURIComponent(path)}`),
  
  // Training
  getTrainingStatus: () => request('/training/status'),
  startTraining: (config) => request('/training/start', { method: 'POST', body: JSON.stringify(config) }),

  // System & Skills
  getSkills: () => request('/skills'),
  getSystemMetrics: () => request('/admin/metrics')
};
