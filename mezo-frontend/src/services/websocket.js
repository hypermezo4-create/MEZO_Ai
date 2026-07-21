import { SSEService } from 'mezo-shared-client';

// The old websocket.js was a class with a connect() and emit() method.
// Our SSEService behaves the same way, so we just instantiate and export it.
// Note: We use SSE now instead of WebSocket for chat/workflows on the backend, 
// so this service acts as the wrapper to keep the frontend interface similar.

const url = typeof window !== 'undefined' ? `http://${window.location.host}/api/stream` : '/api/stream';
export const wsService = new SSEService(url);

// In case the frontend expects to call send() on it:
(wsService as any).send = (event, payload) => {
  console.warn('[MEZO] send() called on SSEService. SSE is unidirectional. Use API for upstream.');
};
