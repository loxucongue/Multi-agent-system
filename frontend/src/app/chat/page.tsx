"use client";

import { Alert, Button, Spin } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import ChatInput from "@/components/chat/ChatInput";
import ChatLayout from "@/components/chat/ChatLayout";
import MessageList from "@/components/chat/MessageList";
import QuickButtons from "@/components/chat/QuickButtons";
import CompareDrawer from "@/components/compare/CompareDrawer";
import LeadModal from "@/components/lead/LeadModal";
import ActiveRouteCard, { type ActiveRouteCardData } from "@/components/route-card/ActiveRouteCard";
import CandidateCards from "@/components/route-card/CandidateCards";
import RouteDetailPanel from "@/components/route-card/RouteDetailPanel";
import { useSSE } from "@/hooks/useSSE";
import { API_BASE_URL, apiRequest } from "@/services/api";
import { CURRENT_SESSION_KEY, useChatStore } from "@/stores/sessionStore";
import type { CompareData, SessionDetailResponse } from "@/types";

const deriveDays = (summary: string): number => {
  const match = summary.match(/(\d{1,2})\s*天/);
  if (!match) {
    return 0;
  }
  return Number(match[1]);
};

const deriveHighlights = (summary: string): string[] => {
  const parts = summary
    .split(/[，。；,;.!?\n]+/)
    .map((item) => item.trim())
    .filter((item) => item.length >= 4);
  if (parts.length === 0) {
    return ["行程亮点待确认"];
  }
  return parts.slice(0, 5);
};

export default function ChatPage() {
  const [initializing, setInitializing] = useState(true);
  const { connect } = useSSE();

  const {
    sessionId,
    activeRouteId,
    candidateRouteIds,
    routeCards,
    routeDetailPanel,
    showLeadModal,
    showCompareDrawer,
    compareData,
    error,
    messages,
    isStreaming,
    createSession,
    hydrateSession,
    sendMessage,
    openRouteDetail,
    closeRouteDetail,
    setLeadModalVisible,
    setCompareDrawerVisible,
    setCompareData,
    setError,
  } = useChatStore(
    useShallow((state) => ({
      sessionId: state.sessionId,
      activeRouteId: state.activeRouteId,
      candidateRouteIds: state.candidateRouteIds,
      routeCards: state.routeCards,
      routeDetailPanel: state.routeDetailPanel,
      showLeadModal: state.showLeadModal,
      showCompareDrawer: state.showCompareDrawer,
      compareData: state.compareData,
      error: state.error,
      messages: state.messages,
      isStreaming: state.isStreaming,
      createSession: state.createSession,
      hydrateSession: state.hydrateSession,
      sendMessage: state.sendMessage,
      openRouteDetail: state.openRouteDetail,
      closeRouteDetail: state.closeRouteDetail,
      setLeadModalVisible: state.setLeadModalVisible,
      setCompareDrawerVisible: state.setCompareDrawerVisible,
      setCompareData: state.setCompareData,
      setError: state.setError,
    })),
  );

  useEffect(() => {
    let cancelled = false;

    const initializeSession = async () => {
      setInitializing(true);
      try {
        const savedSessionId = window.localStorage.getItem(CURRENT_SESSION_KEY);
        if (savedSessionId) {
          try {
            const response = await fetch(`${API_BASE_URL}/session/${savedSessionId}`);
            if (response.ok) {
              const detail = (await response.json()) as SessionDetailResponse;
              if (!cancelled) {
                hydrateSession(detail);
              }
              return;
            }

            if (response.status === 404 || response.status === 410) {
              window.localStorage.removeItem(CURRENT_SESSION_KEY);
            } else if (!cancelled) {
              setError("恢复会话失败，已为您创建新会话。");
            }
          } catch {
            if (!cancelled) {
              setError("恢复会话失败，已为您创建新会话。");
            }
          }
        }

        const newSessionId = await createSession();
        if (!cancelled) {
          window.localStorage.setItem(CURRENT_SESSION_KEY, newSessionId);
        }
      } catch {
        if (!cancelled) {
          setError("创建会话失败：无法连接后端服务，请先启动 backend(8000)");
        }
      } finally {
        if (!cancelled) {
          setInitializing(false);
        }
      }
    };

    void initializeSession();
    return () => {
      cancelled = true;
    };
  }, [createSession, hydrateSession, setError]);

  useEffect(() => {
    if (sessionId) {
      window.localStorage.setItem(CURRENT_SESSION_KEY, sessionId);
    }
  }, [sessionId]);

  const handleSend = useCallback(
    async (text: string) => {
      setError(null);
      const runId = await sendMessage(text);
      if (runId) {
        connect(runId);
      }
    },
    [connect, sendMessage, setError],
  );

  const handleCompare = useCallback(
    async (routeIds: number[]) => {
      if (!sessionId) {
        setError("会话不存在，请刷新页面后重试");
        return;
      }

      try {
        const compare = await apiRequest<CompareData>(`/session/${sessionId}/compare`, {
          method: "POST",
          body: JSON.stringify({ route_ids: routeIds }),
        });
        setCompareData(compare);
        setCompareDrawerVisible(true);
      } catch {
        setError("获取对比数据失败，请稍后重试");
      }
    },
    [sessionId, setCompareData, setCompareDrawerVisible, setError],
  );

  const handleOpenRouteDetail = useCallback(
    async (routeId: number, scrollToPrice = false) => {
      if (!sessionId) {
        setError("会话不存在，请刷新页面后重试");
        return;
      }
      await openRouteDetail(sessionId, routeId);
      if (scrollToPrice) {
        window.setTimeout(() => {
          const section = document.getElementById("route-detail-price");
          section?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 60);
      }
    },
    [openRouteDetail, sessionId, setError],
  );

  const activeRoute = useMemo(
    () => routeCards.find((card) => card.id === activeRouteId) ?? null,
    [activeRouteId, routeCards],
  );

  const activeRouteCard = useMemo<ActiveRouteCardData | null>(() => {
    if (!activeRoute) {
      return null;
    }
    return {
      id: activeRoute.id,
      name: activeRoute.name,
      tags: activeRoute.tags,
      summary: activeRoute.summary,
      supplier: "平台精选",
      days: deriveDays(activeRoute.summary),
      highlights: deriveHighlights(activeRoute.summary),
    };
  }, [activeRoute]);

  const lastUserMessage = useMemo(
    () => [...messages].reverse().find((message) => message.role === "user") ?? null,
    [messages],
  );

  const handleRetry = async () => {
    if (!lastUserMessage || isStreaming) {
      return;
    }
    await handleSend(lastUserMessage.content);
  };

  if (initializing) {
    return (
      <ChatLayout>
        <div className="flex h-full items-center justify-center">
          <Spin description="正在恢复会话..." />
        </div>
      </ChatLayout>
    );
  }

  return (
    <ChatLayout>
      <div className="flex h-full">
        <div className="flex-1 flex flex-col min-w-0">
          <MessageList />

          {error ? (
            <div style={{ marginTop: 10 }}>
              <Alert
                type="error"
                showIcon
                title={error}
                action={
                  <Button size="small" disabled={!lastUserMessage || isStreaming} onClick={() => void handleRetry()}>
                    重试
                  </Button>
                }
              />
            </div>
          ) : null}

          <QuickButtons onSend={handleSend} />
          <ChatInput onSend={handleSend} />
        </div>

        <div className="w-[320px] border-l p-4 overflow-y-auto hidden lg:block">
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {routeDetailPanel ? (
              <RouteDetailPanel
                data={routeDetailPanel.data}
                loading={routeDetailPanel.loading}
                onClose={closeRouteDetail}
              />
            ) : (
              <ActiveRouteCard
                activeRouteId={activeRouteId}
                route={activeRouteCard}
                onViewPriceSchedule={(route) => {
                  void handleOpenRouteDetail(route.id, true);
                }}
                onViewItinerary={(route) => {
                  void handleOpenRouteDetail(route.id);
                }}
                onAddCompare={(route) => {
                  const ids = [route.id, ...candidateRouteIds.filter((id) => id !== route.id)].slice(0, 2);
                  if (ids.length < 2) {
                    setError("至少需要两条线路进行对比");
                    return;
                  }
                  void handleCompare(ids);
                }}
              />
            )}

            <CandidateCards
              cards={routeCards}
              onSelect={(routeId) => {
                void handleOpenRouteDetail(routeId);
              }}
              onCompare={(routeIds) => {
                void handleCompare(routeIds);
              }}
            />
          </div>
        </div>
      </div>

      <CompareDrawer
        open={showCompareDrawer}
        data={compareData}
        onClose={() => {
          setCompareDrawerVisible(false);
        }}
      />

      <LeadModal
        open={showLeadModal}
        onClose={() => {
          setLeadModalVisible(false);
        }}
      />
    </ChatLayout>
  );
}
