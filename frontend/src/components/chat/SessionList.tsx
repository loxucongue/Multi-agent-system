"use client";

import { ClockCircleOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Empty, List, Skeleton, Space, Spin, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { SESSION_HISTORY_KEY, type SessionHistoryItem, useChatStore } from "@/stores/sessionStore";

const { Text } = Typography;

const formatTime = (ts: number): string => {
  return new Date(ts).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

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
    return parsed.sort((a, b) => b.last_active_at - a.last_active_at);
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
    if (targetSessionId === sessionId || isStreaming) {
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

  const isEmpty = !loading && sessions.length === 0;
  const isNormal = !loading && sessions.length > 0;

  const content = useMemo(() => {
    if (loading) {
      return (
        <div style={{ padding: 12 }}>
          <Skeleton active paragraph={{ rows: 5 }} />
          <div style={{ marginTop: 8 }}>
            <Spin size="small" /> <Text type="secondary">加载会话中...</Text>
          </div>
        </div>
      );
    }

    if (isEmpty) {
      return (
        <div style={{ padding: "20px 12px" }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<Text type="secondary">发送消息开始咨询</Text>}
          />
        </div>
      );
    }

    if (!isNormal) {
      return null;
    }

    return (
      <List
        dataSource={sessions}
        style={{ padding: "0 8px 8px" }}
        renderItem={(item) => {
          const active = item.session_id === sessionId;
          const switching = switchingId === item.session_id;
          return (
            <List.Item style={{ padding: 0, border: 0, marginBottom: 8 }}>
              <Button
                block
                type={active ? "primary" : "default"}
                ghost={!active}
                loading={switching}
                onClick={() => {
                  void handleSwitch(item.session_id);
                }}
                style={{
                  height: "auto",
                  textAlign: "left",
                  padding: 10,
                  borderRadius: 10,
                }}
              >
                <div style={{ width: "100%" }}>
                  <div
                    style={{
                      fontWeight: 600,
                      marginBottom: 6,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {item.title}
                  </div>
                  <Space size={6} direction="vertical">
                    <Text type={active ? undefined : "secondary"} style={{ fontSize: 12 }}>
                      创建：{formatTime(item.created_at)}
                    </Text>
                    <Text type={active ? undefined : "secondary"} style={{ fontSize: 12 }}>
                      <ClockCircleOutlined style={{ marginRight: 4 }} />
                      最近：{formatTime(item.last_active_at)}
                    </Text>
                  </Space>
                </div>
              </Button>
            </List.Item>
          );
        }}
      />
    );
  }, [handleSwitch, isEmpty, isNormal, loading, sessionId, sessions, switchingId]);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: 12, borderBottom: "1px solid rgba(255,255,255,0.15)" }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          block
          loading={creating}
          disabled={isStreaming}
          onClick={() => {
            void handleCreate();
          }}
        >
          新建会话
        </Button>
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>{content}</div>
    </div>
  );
}
