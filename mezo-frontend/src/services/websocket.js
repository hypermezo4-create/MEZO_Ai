class WebSocketService {
  constructor() {
    this.ws = null;
    this.listeners = new Map();
  }

  connect(url = `ws://${window.location.host}/ws`) {
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('[MEZO WS] Connected to backend service');
      this.emit('connection', { status: 'connected' });
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.emit(data.event || 'message', data.payload);
      } catch (err) {
        console.error('[MEZO WS] Message parse error', err);
      }
    };

    this.ws.onclose = () => {
      console.log('[MEZO WS] Connection closed, reconnecting in 3s...');
      this.emit('connection', { status: 'disconnected' });
      setTimeout(() => this.connect(url), 3000);
    };
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  off(event, callback) {
    if (!this.listeners.has(event)) return;
    const callbacks = this.listeners.get(event).filter(cb => cb !== callback);
    this.listeners.set(event, callbacks);
  }

  emit(event, payload) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(cb => cb(payload));
    }
  }

  send(event, payload) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, payload }));
    }
  }
}

export const wsService = new WebSocketService();
