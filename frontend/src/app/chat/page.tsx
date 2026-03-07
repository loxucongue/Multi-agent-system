"use client";

import { Alert, Button, Spin } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import type { CompareAIAnalysisResponse, CompareData, SessionDetailResponse } from "@/types";

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

const dedupeRouteIds = (routeIds: number[]) => {
  const seen = new Set<number>();
  const result: number[] = [];
  routeIds.forEach((id) => {
    if (seen.has(id)) {
      return;
    }
    seen.add(id);
    result.push(id);
  });
  return result;
};

export default function ChatPage() {
  const [initializing, setInitializing] = useState(true);
  const [activeCheckedForCompare, setActiveCheckedForCompare] = useState(false);
  const [aiCompareLoading, setAiCompareLoading] = useState(false);

  const [viewportWidth, setViewportWidth] = useState<number>(typeof window === "undefined" ? 1440 : window.innerWidth);
  const [rightPanelWidth, setRightPanelWidth] = useState(360);
  const [isResizingRightPanel, setIsResizingRightPanel] = useState(false);
  const resizeStartXRef = useRef(0);
  const resizeStartWidthRef = useRef(360);

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

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const onResize = () => setViewportWidth(window.innerWidth);
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const rightPanelMinWidth = 280;
  const rightPanelMaxWidth = useMemo(() => Math.max(320, Math.floor(viewportWidth / 3)), [viewportWidth]);

  const clampRightPanelWidth = useCallback(
    (value: number) => Math.min(rightPanelMaxWidth, Math.max(rightPanelMinWidth, value)),
    [rightPanelMaxWidth],
  );

  useEffect(() => {
    setRightPanelWidth((prev) => clampRightPanelWidth(prev));
  }, [clampRightPanelWidth]);

  useEffect(() => {
    if (!isResizingRightPanel) {
      return;
    }

    const onMouseMove = (event: MouseEvent) => {
      const delta = resizeStartXRef.current - event.clientX;
      const nextWidth = clampRightPanelWidth(resizeStartWidthRef.current + delta);
      setRightPanelWidth(nextWidth);
    };

    const onMouseUp = () => {
      setIsResizingRightPanel(false);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };

    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
  }, [clampRightPanelWidth, isResizingRightPanel]);

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

      let finalIds = dedupeRouteIds(routeIds);
      if (activeCheckedForCompare && activeRouteId !== null && !finalIds.includes(activeRouteId)) {
        finalIds = [activeRouteId, ...finalIds];
      }
      finalIds = dedupeRouteIds(finalIds).slice(0, 5);

      if (finalIds.length < 2) {
        setError("至少需要两条线路进行对比");
        return;
      }

      try {
        const compare = await apiRequest<CompareData>(`/session/${sessionId}/compare`, {
          method: "POST",
          body: JSON.stringify({ route_ids: finalIds }),
        });
        setCompareData(compare);
        setCompareDrawerVisible(true);
      } catch {
        setError("获取对比数据失败，请稍后重试");
      }
    },
    [activeCheckedForCompare, activeRouteId, sessionId, setCompareData, setCompareDrawerVisible, setError],
  );

  const handleAICompare = useCallback(async () => {
    if (!sessionId || !compareData?.routes?.length) {
      setError("暂无可分析的对比数据");
      return;
    }

    const routeIds = dedupeRouteIds(compareData.routes.map((item) => item.route_id)).slice(0, 2);
    if (routeIds.length < 2) {
      setError("至少需要两条线路才能进行 AI 对比分析");
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
      setError("AI 对比分析失败，请稍后重试");
    } finally {
      setAiCompareLoading(false);
    }
  }, [addAssistantMessage, compareData?.routes, sessionId, setError]);

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

  const activeRoute = useMemo(() => routeCards.find((card) => card.id === activeRouteId) ?? null, [activeRouteId, routeCards]);

  const candidateCards = useMemo(() => {
    const candidateIdSet = new Set(candidateRouteIds);
    const filtered = routeCards.filter((card) => {
      if (card.id === activeRouteId) {
        return false;
      }
      if (candidateIdSet.size > 0) {
        return candidateIdSet.has(card.id);
      }
      return true;
    });
    return filtered;
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
      supplier: "平台精选",
      days: deriveDays(activeRoute.summary),
      highlights: deriveHighlights(activeRoute.summary),
    };
  }, [activeRoute]);

  useEffect(() => {
    setActiveCheckedForCompare(false);
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

        <div className="hidden lg:flex" style={{ height: "100%" }}>
          <div
            role="separator"
            aria-label="resize-right-panel"
            style={{ width: 8, cursor: "col-resize", background: isResizingRightPanel ? "#d9d9d9" : "transparent" }}
            onMouseDown={(event) => {
              resizeStartXRef.current = event.clientX;
              resizeStartWidthRef.current = rightPanelWidth;
              setIsResizingRightPanel(true);
            }}
          />

          <div style={{ width: rightPanelWidth, borderLeft: "1px solid #f0f0f0", padding: 16, overflowY: "auto" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <ActiveRouteCard
                activeRouteId={activeRouteId}
                route={activeRouteCard}
                compareChecked={activeCheckedForCompare}
                onCompareCheckedChange={setActiveCheckedForCompare}
                onViewItinerary={(route) => {
                  void handleOpenRouteDetail(route.id);
                }}
              />

              <CandidateCards
                cards={candidateCards}
                onGuideRematch={() => {
                  void handleSend("请重新为我匹配符合当前条件的旅游线路，我可以继续补充需求");
                }}
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
    </ChatLayout>
  );
}
