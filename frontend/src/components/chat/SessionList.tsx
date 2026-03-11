"use client";

import { MessageOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Empty, Skeleton, Space, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { SESSION_HISTORY_KEY, type SessionHistoryItem, useChatStore } from "@/stores/sessionStore";

const { Text } = Typography;

const formatTime = (ts: number): string =>
  new Date(ts).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

const isRecent = (ts: number): boolean => Date.now() - ts <= 7 * 24 * 60 * 60 * 1000;

const readHistory = (): SessionHistoryItem[] => {
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
    return parsed.sort((a, b) => {
      if (b.created_at !== a.created_at) {
        return b.created_at - a.created_at;
      }
      return b.last_active_at - a.last_active_at;
    });
  } catch {
    return [];
  }
};

export default function SessionList() {
  const [sessions, setSessions] = useState<SessionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [switchingId, setSwitchingId] = useState<string | null>(null);

  const { sessionId, createSession, switchSession, isStreaming } = useChatStore(
    useShallow((state) => ({
      sessionId: state.sessionId,
      createSession: state.createSession,
      switchSession: state.switchSession,
      isStreaming: state.isStreaming,
    })),
  );

  const refresh = useCallback(() => {
    setSessions(readHistory());
  }, []);

  useEffect(() => {
    refresh();
    setLoading(false);
  }, [refresh]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === SESSION_HISTORY_KEY) {
        refresh();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("storage", onStorage);
    };
  }, [refresh]);

  const handleCreate = async () => {
    if (creating || isStreaming) {
      return;
    }
    setCreating(true);
    try {
      await createSession();
      refresh();
    } finally {
      setCreating(false);
    }
  };

  const handleSwitch = async (targetSessionId: string) => {
    if (targetSessionId === sessionId) {
      return;
    }
    setSwitchingId(targetSessionId);
    try {
      await switchSession(targetSessionId);
      refresh();
    } finally {
      setSwitchingId(null);
    }
  };

  const grouped = useMemo(() => {
    const recent = sessions.filter((item) => isRecent(item.created_at));
    const earlier = sessions.filter((item) => !isRecent(item.created_at));
    return { recent, earlier };
  }, [sessions]);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: 16, borderBottom: "1px solid #e5e8ef" }}>
        <Button
          icon={<PlusOutlined />}
          block
          loading={creating}
          disabled={isStreaming}
          onClick={() => {
            void handleCreate();
          }}
          style={{
            height: 44,
            borderRadius: 12,
            background: "#e9eef7",
            borderColor: "#d4deef",
            color: "#2f5db5",
            fontWeight: 600,
          }}
        >
          开启新咨询
        </Button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        {loading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : sessions.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有历史会话" />
        ) : (
          <>
            <Section title="最近对话" items={grouped.recent} sessionId={sessionId} switchingId={switchingId} onSwitch={handleSwitch} />
            {grouped.earlier.length > 0 ? (
              <Section title="更早" items={grouped.earlier} sessionId={sessionId} switchingId={switchingId} onSwitch={handleSwitch} />
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  items,
  sessionId,
  switchingId,
  onSwitch,
}: {
  title: string;
  items: SessionHistoryItem[];
  sessionId: string | null;
  switchingId: string | null;
  onSwitch: (sessionId: string) => Promise<void>;
}) {
  if (!items.length) {
    return null;
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
        {title}
      </Text>
      <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map((item) => {
          const active = item.session_id === sessionId;
          const switching = switchingId === item.session_id;

          return (
            <div key={item.session_id}>
              <Button
                block
                loading={switching}
                onClick={() => {
                  void onSwitch(item.session_id);
                }}
                style={{
                  height: "auto",
                  textAlign: "left",
                  borderRadius: 12,
                  padding: "10px 12px",
                  borderColor: active ? "#bfd0ff" : "#e6ebf5",
                  background: active ? "#eaf1ff" : "#f7f9fd",
                }}
              >
                <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
                  <Space size={8} align="center" style={{ width: "100%" }}>
                    <MessageOutlined style={{ color: "#6a7da6", flex: "0 0 auto" }} />
                    <Text
                      strong
                      style={{
                        color: "#213457",
                        display: "block",
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {item.title}
                    </Text>
                  </Space>
                  <div style={{ fontSize: 11, color: "#8a94a6", lineHeight: 1.35, paddingLeft: 22 }}>
                    <div>创建：{formatTime(item.created_at)}</div>
                    <div>最近：{formatTime(item.last_active_at)}</div>
                  </div>
                </div>
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
