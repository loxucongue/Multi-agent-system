"use client";

import { useCallback, useEffect, useRef } from "react";

import { API_BASE_URL } from "@/services/api";
import { useChatStore } from "@/stores/sessionStore";
import type { RouteCard, UIAction } from "@/types";

const MAX_RECONNECT = 3;
const RECONNECT_DELAY = 3000;

const safeJsonParse = <T>(value: string): T | null => {
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
};

export function useSSE() {
  const store = useChatStore();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectCountRef = useRef(0);

  const disconnect = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  const connect = useCallback(
    (runId: string) => {
      const openConnection = (resetReconnect: boolean) => {
        if (resetReconnect) {
          reconnectCountRef.current = 0;
        }

        disconnect();

        const url = `${API_BASE_URL}/chat/stream?run_id=${runId}`;
        const eventSource = new EventSource(url);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
          reconnectCountRef.current = 0;
        };

        eventSource.addEventListener("token", (event) => {
          const data = safeJsonParse<{ text?: string }>((event as MessageEvent).data);
          if (data?.text) {
            store.appendToken(data.text);
          }
        });

        eventSource.addEventListener("ui_action", (event) => {
          const action = safeJsonParse<UIAction>((event as MessageEvent).data);
          if (action) {
            store.handleUIAction(action);
          }
        });

        eventSource.addEventListener("cards", (event) => {
          const cards = safeJsonParse<RouteCard[]>((event as MessageEvent).data);
          if (Array.isArray(cards)) {
            store.setRouteCards(cards);
          }
        });

        eventSource.addEventListener("state_patch", (event) => {
          const patch = safeJsonParse<Record<string, unknown>>((event as MessageEvent).data);
          if (patch) {
            store.applyStatePatch(patch);
          }
        });

        eventSource.addEventListener("done", () => {
          reconnectCountRef.current = 0;
          store.finishStream();
          disconnect();
        });

        eventSource.addEventListener("error", (event) => {
          if (!(event instanceof MessageEvent)) {
            return;
          }

          const data = safeJsonParse<{ message?: string }>(event.data);
          store.setError(data?.message ?? "服务端返回错误");
          store.finishStream();
          disconnect();
        });

        eventSource.onerror = () => {
          if (eventSourceRef.current !== eventSource) {
            return;
          }

          if (reconnectCountRef.current < MAX_RECONNECT) {
            reconnectCountRef.current += 1;
            window.setTimeout(() => {
              openConnection(false);
            }, RECONNECT_DELAY);
            return;
          }

          store.setError("连接中断，请重试");
          store.finishStream();
          disconnect();
        };
      };

      openConnection(true);
    },
    [disconnect, store],
  );

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return { connect, disconnect };
}
