import { getAuthStorage } from './auth';

let BASE_URL = '/api';

export function setApiBaseUrl(url: string) {
  BASE_URL = url;
}

export async function request(endpoint: string, options: RequestInit = {}): Promise<any> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  const token = await getAuthStorage().getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = 'API Request failed';
    try {
      const errorData = await response.json();
      message = errorData.detail || errorData.message || message;
    } catch (err) {
      // ignore
    }
    throw new Error(message);
  }

  return response.json();
}

export const api = {
  // Auth
  login: (credentials: any) => request('/auth/login', { method: 'POST', body: JSON.stringify(credentials) }),
  getProfile: () => request('/auth/me'),

  // Chat
  sendMessage: (data: any) => request('/chat/message', { method: 'POST', body: JSON.stringify(data) }),
  getConversations: () => request('/chat/conversations'),
  
  // Tasks (Control Plane)
  confirmTask: (taskId: string, decision: boolean) => request(`/tasks/${taskId}/confirm`, { 
    method: 'POST', 
    body: JSON.stringify({ confirm: decision }) 
  }),

  // Memory (Control Plane)
  getMemory: () => request('/user/memory'),
  deleteMemoryFact: (factId: string) => request(`/user/memory/${factId}`, { method: 'DELETE' }),
  wipeMemory: () => request('/user/memory', { method: 'DELETE' }),

  // Kill Switch (Control Plane)
  getKillSwitchStatus: () => request('/control/kill-switch/status'),
  armKillSwitch: () => request('/control/kill-switch/arm', { method: 'POST' }),
  disarmKillSwitch: () => request('/control/kill-switch/disarm', { method: 'POST' }),

  // Files
  listFiles: (path: string = '') => request(`/files/list?path=${encodeURIComponent(path)}`),
  readFile: (path: string) => request(`/files/read?path=${encodeURIComponent(path)}`),
  
  // Training
  getTrainingStatus: () => request('/training/status'),
  startTraining: (config: any) => request('/training/start', { method: 'POST', body: JSON.stringify(config) }),

  // System & Skills
  getSkills: () => request('/skills'),
  getSystemMetrics: () => request('/admin/metrics')
};
