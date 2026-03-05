import { create } from "zustand";

import { apiRequest } from "@/services/api";
import type {
  ChatMessage,
  ChatSendRequest,
  ChatSendResponse,
  CompareData,
  RouteCard,
  SessionCreateResponse,
  SessionState,
  UIAction,
} from "@/types";

interface ChatStore {
  // ─── 会话状态 ───
  sessionId: string | null;
  stage: SessionState["stage"];
  leadStatus: SessionState["lead_status"];
  activeRouteId: number | null;
  candidateRouteIds: number[];

  // ─── 消息 ───
  messages: ChatMessage[];
  isStreaming: boolean;
  currentStreamText: string;
  error: string | null;

  // ─── 路线卡片 ───
  routeCards: RouteCard[];
  compareData: CompareData | null;

  // ─── UI 控制 ───
  showLeadModal: boolean;
  showCompareDrawer: boolean;

  // ─── Actions ───
  createSession: () => Promise<string>;
  sendMessage: (text: string) => Promise<string | null>;
  appendToken: (token: string) => void;
  finishStream: () => void;
  applyStatePatch: (patch: Record<string, unknown>) => void;
  setRouteCards: (cards: RouteCard[]) => void;
  handleUIAction: (action: UIAction) => void;
  setLeadModalVisible: (visible: boolean) => void;
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

export const useChatStore = create<ChatStore>((set, get) => ({
  ...INITIAL_STATE,

  createSession: async () => {
    const response = await apiRequest<SessionCreateResponse>("/session/create", {
      method: "POST",
    });

    set({ sessionId: response.session_id });
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
