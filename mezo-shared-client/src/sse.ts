type Listener = (payload: any) => void;

export class SSEService {
  private eventSource: EventSource | null = null;
  private listeners: Map<string, Listener[]> = new Map();
  private url: string;

  constructor(url: string) {
    this.url = url;
  }

  connect() {
    if (this.eventSource) return;

    this.eventSource = new EventSource(this.url);

    this.eventSource.onopen = () => {
      console.log(`[MEZO SSE] Connected to ${this.url}`);
      this.emit('connection', { status: 'connected' });
    };

    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.emit(data.event || 'message', data.payload || data);
      } catch (err) {
        console.error('[MEZO SSE] Message parse error', err);
      }
    };

    this.eventSource.onerror = (err) => {
      console.error('[MEZO SSE] Connection error', err);
      this.emit('connection', { status: 'disconnected' });
      this.eventSource?.close();
      this.eventSource = null;
      // Reconnect after 3 seconds
      setTimeout(() => this.connect(), 3000);
    };
  }

  on(event: string, callback: Listener) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event)!.push(callback);
  }

  off(event: string, callback: Listener) {
    if (!this.listeners.has(event)) return;
    const callbacks = this.listeners.get(event)!.filter(cb => cb !== callback);
    this.listeners.set(event, callbacks);
  }

  emit(event: string, payload: any) {
    if (this.listeners.has(event)) {
      this.listeners.get(event)!.forEach(cb => cb(payload));
    }
  }

  disconnect() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
