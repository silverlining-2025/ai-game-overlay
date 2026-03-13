/**
 * WebSocket client for connecting to the Python backend.
 * Auto-reconnects with 2s backoff.
 */

type MessageHandler = (data: unknown) => void;

class CoachWebSocket {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, MessageHandler[]>();
  private shouldReconnect = true;
  private reconnectMs = 2000;

  constructor(private url: string = "ws://localhost:9600") {}

  connect(): void {
    this.shouldReconnect = true;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.emit("connected", {});
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as {
          type?: string;
          data?: unknown;
        };
        this.emit("message", data);
        if (data.type) {
          this.emit(data.type, data.data ?? data);
        }
      } catch {
        this.emit("raw", event.data);
      }
    };

    this.ws.onclose = () => {
      this.emit("disconnected", {});
      if (this.shouldReconnect) {
        setTimeout(() => this.connect(), this.reconnectMs);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  send(type: string, payload: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({ type, ts: Date.now(), data: payload }),
      );
    }
  }

  on(event: string, handler: MessageHandler): () => void {
    const list = this.handlers.get(event) ?? [];
    list.push(handler);
    this.handlers.set(event, list);
    return () => {
      const current = this.handlers.get(event);
      if (current) {
        this.handlers.set(
          event,
          current.filter((h) => h !== handler),
        );
      }
    };
  }

  private emit(event: string, data: unknown): void {
    this.handlers.get(event)?.forEach((h) => h(data));
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.ws?.close();
  }
}

export const coachSocket = new CoachWebSocket("ws://localhost:9600");
export type { CoachWebSocket };
