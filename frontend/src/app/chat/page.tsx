"use client";

import { Alert, Button, Spin, Typography } from "antd";
import { MessageOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import ChatInput from "@/components/chat/ChatInput";
import ChatLayout from "@/components/chat/ChatLayout";
import MessageList from "@/components/chat/MessageList";
import QuickButtons from "@/components/chat/QuickButtons";
import CompareDrawer from "@/components/compare/CompareDrawer";
import LeadModal from "@/components/lead/LeadModal";
import RouteDetailPanel from "@/components/route-card/RouteDetailPanel";
import RouteWorkspace from "@/components/route-card/RouteWorkspace";
import type { ActiveRouteCardData } from "@/components/route-card/ActiveRouteCard";
import { useSSE } from "@/hooks/useSSE";
import { API_BASE_URL, apiRequest } from "@/services/api";
import { CURRENT_SESSION_KEY, useChatStore } from "@/stores/sessionStore";
import type { CompareAIAnalysisResponse, CompareData, RouteCard, SessionDetailResponse } from "@/types";

const { Text } = Typography;

const normalizeHighlights = (card: RouteCard): string[] => {
  const tags = Array.isArray(card.highlight_tags) ? card.highlight_tags.filter(Boolean) : [];
  if (tags.length > 0) {
    return tags.slice(0, 5);
  }

  return ["路线亮点待补充"];
};

const dedupeRouteIds = (routeIds: number[]) => {
  const seen = new Set<number>();
  const result: number[] = [];

  routeIds.forEach((id) => {
    if (!seen.has(id)) {
      seen.add(id);
      result.push(id);
    }
  });

  return result;
};

export default function ChatPage() {
  const [initializing, setInitializing] = useState(true);
  const [activeCheckedForCompare, setActiveCheckedForCompare] = useState(false);
  const [candidateCheckedRouteIds, setCandidateCheckedRouteIds] = useState<number[]>([]);
  const [aiCompareLoading, setAiCompareLoading] = useState(false);

  const { connect, disconnect } = useSSE();

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
    applyStatePatch,
    addAssistantMessage,
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
      applyStatePatch: state.applyStatePatch,
      addAssistantMessage: state.addAssistantMessage,
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
              setError("恢复会话失败，已为你创建新会话。");
            }
          } catch {
            if (!cancelled) {
              setError("恢复会话失败，已为你创建新会话。");
            }
          }
        }

        const newSessionId = await createSession();
        if (!cancelled) {
          window.localStorage.setItem(CURRENT_SESSION_KEY, newSessionId);
        }
      } catch {
        if (!cancelled) {
          setError("创建会话失败，请确认后端服务已启动。");
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

  useEffect(() => {
    disconnect();
  }, [disconnect, sessionId]);

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
        setError("会话不存在，请刷新页面后重试。");
        return;
      }

      let finalIds = dedupeRouteIds(routeIds);
      if (activeCheckedForCompare && activeRouteId !== null && !finalIds.includes(activeRouteId)) {
        finalIds = [activeRouteId, ...finalIds];
      }
      finalIds = dedupeRouteIds(finalIds).slice(0, 5);

      if (finalIds.length < 2) {
        setError("至少需要两条路线才能开始对比。");
        return;
      }

      try {
        const compare = await apiRequest<CompareData>(`/session/${sessionId}/compare`, {
          method: "POST",
          body: JSON.stringify({ route_ids: finalIds }),
        });
        setCompareData(compare);
        setCompareDrawerVisible(true);
        applyStatePatch({ stage: "comparing" });
      } catch {
        setError("获取对比数据失败，请稍后重试。");
      }
    },
    [activeCheckedForCompare, activeRouteId, applyStatePatch, sessionId, setCompareData, setCompareDrawerVisible, setError],
  );

  const handleAICompare = useCallback(async () => {
    if (!sessionId || !compareData?.routes?.length) {
      setError("当前没有可分析的对比数据。");
      return;
    }

    const routeIds = dedupeRouteIds(compareData.routes.map((item) => item.route_id)).slice(0, 2);
    if (routeIds.length < 2) {
      setError("至少需要两条路线才能进行 AI 对比分析。");
      return;
    }

    setAiCompareLoading(true);
    try {
      const result = await apiRequest<CompareAIAnalysisResponse>(`/session/${sessionId}/compare/ai-analysis`, {
        method: "POST",
        body: JSON.stringify({ route_ids: routeIds }),
      });

      if (result.analysis.trim()) {
        addAssistantMessage(result.analysis.trim());
      }
    } catch {
      setError("AI 对比分析失败，请稍后再试。");
    } finally {
      setAiCompareLoading(false);
    }
  }, [addAssistantMessage, compareData?.routes, sessionId, setError]);

  const handleOpenRouteDetail = useCallback(
    async (routeId: number, scrollToPrice = false) => {
      if (!sessionId) {
        setError("会话不存在，请刷新页面后重试。");
        return;
      }

      await openRouteDetail(sessionId, routeId);
      if (scrollToPrice) {
        window.setTimeout(() => {
          document.getElementById("route-detail-price")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 60);
      }
    },
    [openRouteDetail, sessionId, setError],
  );

  const activeRoute = useMemo(() => routeCards.find((card) => card.id === activeRouteId) ?? null, [activeRouteId, routeCards]);

  const candidateCards = useMemo(() => {
    const candidateIdSet = new Set(candidateRouteIds);
    return routeCards.filter((card) => {
      if (card.id === activeRouteId) {
        return false;
      }

      if (candidateIdSet.size > 0) {
        return candidateIdSet.has(card.id);
      }

      return true;
    });
  }, [activeRouteId, candidateRouteIds, routeCards]);

  const activeRouteCard = useMemo<ActiveRouteCardData | null>(() => {
    if (!activeRoute) {
      return null;
    }

    return {
      id: activeRoute.id,
      name: activeRoute.name,
      tags: activeRoute.tags,
      summary: activeRoute.summary,
      supplier: activeRoute.supplier || "待确认",
      days: activeRoute.days ?? 0,
      highlights: normalizeHighlights(activeRoute),
      price_min: activeRoute.price_min,
      price_max: activeRoute.price_max,
    };
  }, [activeRoute]);

  useEffect(() => {
    setActiveCheckedForCompare(false);
    setCandidateCheckedRouteIds([]);
  }, [activeRouteId, sessionId]);

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

  const compareSelectedCount =
    candidateCheckedRouteIds.length + (activeCheckedForCompare && activeRouteId !== null ? 1 : 0);

  const routeWorkspace = (
    <RouteWorkspace
      activeRouteId={activeRouteId}
      activeRoute={activeRouteCard}
      activeCheckedForCompare={activeCheckedForCompare}
      onActiveCheckedForCompareChange={setActiveCheckedForCompare}
      candidateCards={candidateCards}
      candidateCheckedRouteIds={candidateCheckedRouteIds}
      onCandidateCheckedRouteIdsChange={setCandidateCheckedRouteIds}
      compareSelectedCount={compareSelectedCount}
      compareData={compareData}
      aiCompareLoading={aiCompareLoading}
      onOpenRouteDetail={(routeId, scrollToPrice) => {
        void handleOpenRouteDetail(routeId, scrollToPrice);
      }}
      onGuideRematch={() => {
        void handleSend("请重新为我匹配符合当前条件的旅游路线，我可以继续补充需求。");
      }}
      onCompare={(routeIds) => {
        void handleCompare(routeIds);
      }}
      onOpenCompareDrawer={() => {
        setCompareDrawerVisible(true);
      }}
      onAICompare={() => {
        void handleAICompare();
      }}
    />
  );

  if (initializing) {
    return (
      <ChatLayout>
        <div className="loading-shell">
          <Spin description="正在恢复会话..." />
        </div>

        <style jsx>{`
          .loading-shell {
            display: flex;
            height: 100%;
            align-items: center;
            justify-content: center;
          }
        `}</style>
      </ChatLayout>
    );
  }

  return (
    <ChatLayout>
      <div className="page-shell">
        <div className="chat-column">
          <div className="chat-panel">
            <div className="hint-bar">
              <MessageOutlined />
              <Text>先描述你的旅行需求，我会同步推荐路线并在右侧整理方案。</Text>
            </div>

            <MessageList onSend={handleSend} />

            {error ? (
              <div className="error-row">
                <Alert
                  type="error"
                  showIcon
                  message={error}
                  action={
                    <Button size="small" disabled={!lastUserMessage || isStreaming} onClick={() => void handleRetry()}>
                      重试
                    </Button>
                  }
                />
              </div>
            ) : null}

            <div className="mobile-workspace">{routeWorkspace}</div>

            <div className="footer-shell">
              <QuickButtons onSend={handleSend} />
              <ChatInput onSend={handleSend} />
            </div>
          </div>
        </div>

        <aside className="workspace-column">{routeWorkspace}</aside>
      </div>

      <CompareDrawer
        open={showCompareDrawer}
        data={compareData}
        aiCompareLoading={aiCompareLoading}
        onAICompare={() => {
          void handleAICompare();
        }}
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

      <RouteDetailPanel
        open={Boolean(routeDetailPanel)}
        data={routeDetailPanel?.data ?? null}
        loading={Boolean(routeDetailPanel?.loading)}
        onClose={closeRouteDetail}
      />

      <style jsx>{`
        .page-shell {
          flex: 1 1 auto;
          height: calc(100dvh - 64px);
          min-height: calc(100dvh - 64px);
          display: grid;
          grid-template-columns: minmax(0, 1fr) 360px;
          gap: 16px;
          min-width: 0;
          padding: 16px;
          overflow: hidden;
        }

        .chat-column,
        .workspace-column {
          min-width: 0;
          min-height: 0;
          height: 100%;
        }

        .chat-panel,
        .workspace-column {
          min-height: 0;
          border-radius: 24px;
          border: 1px solid #e6ebf2;
          background: #ffffff;
        }

        .chat-panel {
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 16px;
          gap: 12px;
        }

        .workspace-column {
          height: 100%;
          overflow-y: auto;
          padding: 16px;
        }

        .hint-bar {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          min-height: 40px;
          padding: 10px 12px;
          border-radius: 14px;
          background: #f8fafc;
          color: #64748b;
        }

        .error-row {
          margin-top: -4px;
        }

        .footer-shell {
          display: grid;
          gap: 12px;
          padding-top: 4px;
        }

        .mobile-workspace {
          display: none;
        }

        @media (max-width: 1199px) {
          .page-shell {
            height: calc(100dvh - 64px);
            grid-template-columns: minmax(0, 1fr);
          }

          .workspace-column {
            display: none;
          }

          .mobile-workspace {
            display: block;
            flex-shrink: 0;
            max-height: 40vh;
            overflow-y: auto;
            border-radius: 18px;
            border: 1px solid #e6ebf2;
            padding: 8px;
            background: #f8fafc;
          }
        }

        @media (max-width: 768px) {
          .page-shell {
            padding: 12px;
          }

          .chat-panel {
            padding: 12px;
            border-radius: 18px;
          }
        }
      `}</style>
    </ChatLayout>
  );
}
