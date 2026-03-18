/**
 * WebSocket client for connecting to the Python backend.
 * Auto-reconnects with 2s backoff.
 */
class CoachWebSocket {
    url;
    ws = null;
    handlers = new Map();
    shouldReconnect = true;
    reconnectMs = 2000;
    constructor(url = "ws://localhost:9600") {
        this.url = url;
    }
    connect() {
        this.shouldReconnect = true;
        this.ws = new WebSocket(this.url);
        this.ws.onopen = () => {
            this.emit("connected", {});
        };
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.emit("message", data);
                if (data.type) {
                    this.emit(data.type, data.data ?? data);
                }
            }
            catch {
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
    send(type, payload) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type, ts: Date.now(), data: payload }));
        }
    }
    on(event, handler) {
        const list = this.handlers.get(event) ?? [];
        list.push(handler);
        this.handlers.set(event, list);
        return () => {
            const current = this.handlers.get(event);
            if (current) {
                this.handlers.set(event, current.filter((h) => h !== handler));
            }
        };
    }
    emit(event, data) {
        this.handlers.get(event)?.forEach((h) => h(data));
    }
    disconnect() {
        this.shouldReconnect = false;
        this.ws?.close();
    }
}
export const coachSocket = new CoachWebSocket("ws://localhost:9600");
