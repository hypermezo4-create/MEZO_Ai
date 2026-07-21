export interface AuthStorage {
  getToken(): Promise<string | null>;
  setToken(token: string): Promise<void>;
  clearToken(): Promise<void>;
}

// Default implementation uses localStorage (for web)
export class WebAuthStorage implements AuthStorage {
  async getToken(): Promise<string | null> {
    return localStorage.getItem('mezo_token');
  }
  
  async setToken(token: string): Promise<void> {
    localStorage.setItem('mezo_token', token);
  }
  
  async clearToken(): Promise<void> {
    localStorage.removeItem('mezo_token');
  }
}

// Global registry for auth storage so it can be swapped by desktop/mobile
let activeAuthStorage: AuthStorage = new WebAuthStorage();

export function setAuthStorage(storage: AuthStorage) {
  activeAuthStorage = storage;
}

export function getAuthStorage(): AuthStorage {
  return activeAuthStorage;
}
