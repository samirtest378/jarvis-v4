/**
 * WebSocket client for JARVIS server communication.
 */

export type MessageHandler = (msg: Record<string, unknown>) => void;

export interface JarvisSocket {
  send(data: Record<string, unknown>): boolean;
  onMessage(handler: MessageHandler): void;
  onConnectionChange(handler: (connected: boolean) => void): void;
  close(): void;
  isConnected(): boolean;
}

export function createSocket(url: string, protocols: string[] = []): JarvisSocket {
  let ws: WebSocket | null = null;
  let handlers: MessageHandler[] = [];
  let connectionHandlers: Array<(connected: boolean) => void> = [];
  let reconnectDelay = 1000;
  let closed = false;
  let connected = false;

  function connect() {
    if (closed) return;

    ws = new WebSocket(url, protocols);

    ws.onopen = () => {
      connected = true;
      reconnectDelay = 1000;
      console.log("[ws] connected");
      for (const handler of connectionHandlers) handler(true);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        for (const h of handlers) h(msg);
      } catch {
        console.warn("[ws] bad message", event.data);
      }
    };

    ws.onclose = () => {
      connected = false;
      for (const handler of connectionHandlers) handler(false);
      if (!closed) {
        console.log(`[ws] reconnecting in ${reconnectDelay}ms`);
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
      }
    };

    ws.onerror = (err) => {
      console.error("[ws] error", err);
      ws?.close();
    };
  }

  connect();

  return {
    send(data) {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
        return true;
      }
      return false;
    },
    onMessage(handler) {
      handlers.push(handler);
    },
    onConnectionChange(handler) {
      connectionHandlers.push(handler);
      handler(connected);
    },
    close() {
      closed = true;
      ws?.close();
    },
    isConnected() {
      return connected;
    },
  };
}
