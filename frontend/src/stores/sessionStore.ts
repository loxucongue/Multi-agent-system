import { create } from "zustand";

import { apiRequest } from "@/services/api";
import type {
  ChatMessage,
  ChatSendRequest,
  ChatSendResponse,
  CompareData,
  RouteCard,
  SessionCreateResponse,
  SessionDetailResponse,
  SessionState,
  UIAction,
} from "@/types";

export interface SessionHistoryItem {
  session_id: string;
  title: string;
  created_at: number;
  last_active_at: number;
}

export const SESSION_HISTORY_KEY = "travel_session_history_v1";
export const CURRENT_SESSION_KEY = "travel_current_session_id";

interface ChatStore {
  sessionId: string | null;
  stage: SessionState["stage"];
  leadStatus: SessionState["lead_status"];
  activeRouteId: number | null;
  candidateRouteIds: number[];

  messages: ChatMessage[];
  isStreaming: boolean;
  currentStreamText: string;
  error: string | null;

  routeCards: RouteCard[];
  compareData: CompareData | null;

  showLeadModal: boolean;
  showCompareDrawer: boolean;

  createSession: () => Promise<string>;
  sendMessage: (text: string) => Promise<string | null>;
  appendToken: (token: string) => void;
  finishStream: () => void;
  applyStatePatch: (patch: Record<string, unknown>) => void;
  setRouteCards: (cards: RouteCard[]) => void;
  handleUIAction: (action: UIAction) => void;
  setLeadModalVisible: (visible: boolean) => void;
  setCompareDrawerVisible: (visible: boolean) => void;
  setCompareData: (data: CompareData | null) => void;
  hydrateSession: (detail: SessionDetailResponse) => void;
  switchSession: (sessionId: string) => Promise<void>;
  setError: (err: string | null) => void;
  reset: () => void;
  addAssistantMessage: (content: string, extras?: Partial<ChatMessage>) => void;
}

interface StoreShape {
  sessionId: string | null;
  stage: SessionState["stage"];
  leadStatus: SessionState["lead_status"];
  activeRouteId: number | null;
  candidateRouteIds: number[];
  messages: ChatMessage[];
  isStreaming: boolean;
  currentStreamText: string;
  error: string | null;
  routeCards: RouteCard[];
  compareData: CompareData | null;
  showLeadModal: boolean;
  showCompareDrawer: boolean;
}

const INITIAL_STATE: StoreShape = {
  sessionId: null,
  stage: "init",
  leadStatus: "none",
  activeRouteId: null,
  candidateRouteIds: [],
  messages: [],
  isStreaming: false,
  currentStreamText: "",
  error: null,
  routeCards: [],
  compareData: null,
  showLeadModal: false,
  showCompareDrawer: false,
};

const createMessageId = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
};

const toErrorMessage = (error: unknown): string => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "请求失败，请稍后重试";
};

const isCompareData = (value: unknown): value is CompareData => {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const routes = (value as { routes?: unknown }).routes;
  return Array.isArray(routes);
};

const parseRouteIds = (value: unknown): number[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is number => typeof item === "number");
};

const readSessionHistory = (): SessionHistoryItem[] => {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(SESSION_HISTORY_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as SessionHistoryItem[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed;
  } catch {
    return [];
  }
};

const writeSessionHistory = (items: SessionHistoryItem[]) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(items));
};

const persistCurrentSessionId = (sessionId: string) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(CURRENT_SESSION_KEY, sessionId);
};

const deriveSessionTitle = (text: string): string => {
  const normalized = text.trim();
  if (!normalized) {
    return "新的旅游咨询";
  }

  const daysMatch = normalized.match(/(\d{1,2})\s*天/);
  const days = daysMatch?.[1];

  const destinationMatch =
    normalized.match(/去\s*([一-龥A-Za-z]{2,12})/) ??
    normalized.match(/([一-龥A-Za-z]{2,12})(?:旅游|跟团|自由行|行程)/);
  const destination = destinationMatch?.[1];

  if (destination && days) {
    return `${destination}${days}日游咨询`;
  }
  if (destination) {
    return `${destination}旅游咨询`;
  }
  return `${normalized.slice(0, 12)}咨询`;
};

const upsertSessionHistory = (sessionId: string, userText?: string) => {
  const items = readSessionHistory();
  const now = Date.now();
  const nextTitle = userText ? deriveSessionTitle(userText) : "新的旅游咨询";
  const idx = items.findIndex((item) => item.session_id === sessionId);

  if (idx < 0) {
    items.unshift({
      session_id: sessionId,
      title: nextTitle,
      created_at: now,
      last_active_at: now,
    });
    writeSessionHistory(items);
    return;
  }

  const current = items[idx];
  const shouldReplaceTitle = current.title === "新的旅游咨询" || current.title === "未命名咨询";
  items[idx] = {
    ...current,
    title: userText && shouldReplaceTitle ? nextTitle : current.title,
    last_active_at: now,
  };

  const reordered = [items[idx], ...items.filter((item) => item.session_id !== sessionId)];
  writeSessionHistory(reordered);
};

const mapDetailToState = (detail: SessionDetailResponse): Partial<StoreShape> & { sessionId: string } => ({
  sessionId: detail.session_id,
  stage: detail.stage as SessionState["stage"],
  leadStatus: detail.lead_status as SessionState["lead_status"],
  activeRouteId: detail.active_route_id,
  candidateRouteIds: detail.candidate_route_ids,
  routeCards: detail.candidate_cards,
  messages: [],
  currentStreamText: "",
  isStreaming: false,
  error: null,
  compareData: null,
  showCompareDrawer: false,
  showLeadModal: false,
});

export const useChatStore = create<ChatStore>((set, get) => ({
  ...INITIAL_STATE,

  createSession: async () => {
    const response = await apiRequest<SessionCreateResponse>("/session/create", {
      method: "POST",
    });

    persistCurrentSessionId(response.session_id);
    upsertSessionHistory(response.session_id);

    set({
      ...INITIAL_STATE,
      sessionId: response.session_id,
    });

    return response.session_id;
  },

  sendMessage: async (text: string) => {
    const message = text.trim();
    if (!message) {
      return null;
    }

    const userMessage: ChatMessage = {
      id: createMessageId(),
      role: "user",
      content: message,
      timestamp: Date.now(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage],
      isStreaming: true,
      currentStreamText: "",
      error: null,
    }));

    try {
      let sessionId = get().sessionId;
      if (!sessionId) {
        sessionId = await get().createSession();
      }

      persistCurrentSessionId(sessionId);
      upsertSessionHistory(sessionId, message);

      const payload: ChatSendRequest = {
        session_id: sessionId,
        message,
      };

      const response = await apiRequest<ChatSendResponse>("/chat/send", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      return response.run_id;
    } catch (error) {
      set({
        isStreaming: false,
        currentStreamText: "",
        error: toErrorMessage(error),
      });
      return null;
    }
  },

  appendToken: (token: string) => {
    set((state) => ({
      currentStreamText: `${state.currentStreamText}${token}`,
    }));
  },

  finishStream: () => {
    set((state) => {
      const streamText = state.currentStreamText;
      const shouldAppendAssistant = streamText.trim().length > 0;
      const nextMessages = shouldAppendAssistant
        ? [
            ...state.messages,
            {
              id: createMessageId(),
              role: "assistant" as const,
              content: streamText,
              timestamp: Date.now(),
            },
          ]
        : state.messages;

      return {
        messages: nextMessages,
        isStreaming: false,
        currentStreamText: "",
      };
    });
  },

  applyStatePatch: (patch: Record<string, unknown>) => {
    set((state) => {
      const nextLeadStatus =
        typeof patch.lead_status === "string"
          ? (patch.lead_status as SessionState["lead_status"])
          : state.leadStatus;

      return {
        stage:
          typeof patch.stage === "string"
            ? (patch.stage as SessionState["stage"])
            : state.stage,
        leadStatus: nextLeadStatus,
        activeRouteId:
          typeof patch.active_route_id === "number" || patch.active_route_id === null
            ? (patch.active_route_id as number | null)
            : state.activeRouteId,
        candidateRouteIds:
          patch.candidate_route_ids !== undefined
            ? parseRouteIds(patch.candidate_route_ids)
            : state.candidateRouteIds,
        showLeadModal: nextLeadStatus === "captured" ? false : state.showLeadModal,
      };
    });
  },

  setRouteCards: (cards: RouteCard[]) => {
    set({ routeCards: cards });
  },

  handleUIAction: (action: UIAction) => {
    const payload = action.payload as Record<string, unknown>;

    if (action.action === "collect_phone") {
      set((state) => ({
        showLeadModal: state.leadStatus !== "captured",
      }));
      return;
    }

    if (action.action === "show_compare") {
      const payloadCompare = payload.compare_data;
      const compareData = isCompareData(payloadCompare)
        ? payloadCompare
        : isCompareData(payload)
          ? payload
          : null;

      set({
        showCompareDrawer: true,
        compareData,
      });
      return;
    }

    if (action.action === "show_active_route") {
      if (typeof payload.route_id === "number") {
        set({ activeRouteId: payload.route_id });
      }
      return;
    }

    if (action.action === "show_candidates") {
      const routeIds = parseRouteIds(payload.route_ids);
      if (routeIds.length > 0) {
        set({ candidateRouteIds: routeIds });
      }
    }
  },

  setLeadModalVisible: (visible: boolean) => {
    set((state) => ({
      showLeadModal: state.leadStatus === "captured" ? false : visible,
    }));
  },

  setCompareDrawerVisible: (visible: boolean) => {
    set({ showCompareDrawer: visible });
  },

  setCompareData: (data: CompareData | null) => {
    set({ compareData: data });
  },

  hydrateSession: (detail: SessionDetailResponse) => {
    set(mapDetailToState(detail));
    persistCurrentSessionId(detail.session_id);
    upsertSessionHistory(detail.session_id);
  },

  switchSession: async (sessionId: string) => {
    try {
      const detail = await apiRequest<SessionDetailResponse>(`/session/${sessionId}`);
      get().hydrateSession(detail);
    } catch (error) {
      set({ error: toErrorMessage(error) });
    }
  },

  setError: (err: string | null) => {
    set({ error: err });
  },

  reset: () => {
    set({ ...INITIAL_STATE });
  },

  addAssistantMessage: (content: string, extras?: Partial<ChatMessage>) => {
    const message: ChatMessage = {
      id: extras?.id ?? createMessageId(),
      role: "assistant",
      content,
      timestamp: extras?.timestamp ?? Date.now(),
      cards: extras?.cards,
      ui_actions: extras?.ui_actions,
    };

    set((state) => ({
      messages: [...state.messages, message],
    }));
  },
}));
