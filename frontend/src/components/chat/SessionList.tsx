"use client";

import { MessageOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Empty, Skeleton, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import {
  SESSION_HISTORY_CHANGED_EVENT,
  SESSION_HISTORY_KEY,
  type SessionHistoryItem,
  useChatStore,
} from "@/stores/sessionStore";

const { Text, Title } = Typography;

const formatDate = (timestamp: number) =>
  new Date(timestamp).toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  });

const isRecent = (timestamp: number) => Date.now() - timestamp <= 7 * 24 * 60 * 60 * 1000;

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

    const onHistoryChanged = () => {
      refresh();
    };

    window.addEventListener("storage", onStorage);
    window.addEventListener(SESSION_HISTORY_CHANGED_EVENT, onHistoryChanged);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(SESSION_HISTORY_CHANGED_EVENT, onHistoryChanged);
    };
  }, [refresh]);

  const groupedSessions = useMemo(
    () => ({
      recent: sessions.filter((item) => isRecent(item.last_active_at)),
      earlier: sessions.filter((item) => !isRecent(item.last_active_at)),
    }),
    [sessions],
  );

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
    if (targetSessionId === sessionId || switchingId) {
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

  return (
    <div className="session-shell">
      <div className="session-top">
        <Title level={5} style={{ margin: 0, color: "#111827" }}>
          历史对话
        </Title>
        <Text type="secondary">继续上一次行程规划，或新建一轮咨询。</Text>

        <Button
          type="primary"
          icon={<PlusOutlined />}
          block
          loading={creating}
          disabled={isStreaming}
          onClick={() => {
            void handleCreate();
          }}
          className="new-button"
        >
          新建咨询
        </Button>
      </div>

      <div className="session-list">
        {loading ? (
          <Skeleton active paragraph={{ rows: 6 }} title={false} />
        ) : sessions.length === 0 ? (
          <div className="empty-box">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有历史会话" />
          </div>
        ) : (
          <>
            <SessionSection
              title="最近对话"
              items={groupedSessions.recent}
              currentSessionId={sessionId}
              switchingId={switchingId}
              onSwitch={handleSwitch}
            />
            <SessionSection
              title="更早记录"
              items={groupedSessions.earlier}
              currentSessionId={sessionId}
              switchingId={switchingId}
              onSwitch={handleSwitch}
            />
          </>
        )}
      </div>

      <style jsx>{`
        .session-shell {
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 16px 14px;
          gap: 14px;
        }

        .session-top {
          display: grid;
          gap: 6px;
        }

        .new-button {
          margin-top: 6px;
          height: 40px;
          border-radius: 12px;
          font-weight: 600;
          box-shadow: none;
        }

        .session-list {
          flex: 1;
          min-height: 0;
          overflow-y: auto;
        }

        .empty-box {
          margin-top: 8px;
          padding: 24px 12px;
          border: 1px dashed #d8e0ec;
          border-radius: 16px;
          background: #ffffff;
        }
      `}</style>
    </div>
  );
}

function SessionSection({
  title,
  items,
  currentSessionId,
  switchingId,
  onSwitch,
}: {
  title: string;
  items: SessionHistoryItem[];
  currentSessionId: string | null;
  switchingId: string | null;
  onSwitch: (sessionId: string) => Promise<void>;
}) {
  if (!items.length) {
    return null;
  }

  return (
    <section className="section">
      <Text className="section-title">{title}</Text>

      <div className="rows">
        {items.map((item) => {
          const active = item.session_id === currentSessionId;
          const loading = switchingId === item.session_id;

          return (
            <button
              key={item.session_id}
              type="button"
              className={`row ${active ? "active" : ""}`}
              disabled={loading}
              onClick={() => {
                void onSwitch(item.session_id);
              }}
            >
              <span className={`dot ${active ? "active" : ""}`} />
              <span className="row-icon">
                <MessageOutlined />
              </span>

              <span className="row-main">
                <span className="row-title">{item.title}</span>
                <span className="row-date">{formatDate(item.last_active_at)}</span>
              </span>

              {active ? <span className="current-pill">当前</span> : null}
            </button>
          );
        })}
      </div>

      <style jsx>{`
        .section {
          display: grid;
          gap: 10px;
          margin-top: 14px;
        }

        .section-title {
          color: #8a94a6;
          font-size: 12px;
        }

        .rows {
          display: grid;
          gap: 6px;
        }

        .row {
          width: 100%;
          display: grid;
          grid-template-columns: 8px 28px minmax(0, 1fr) auto;
          align-items: center;
          gap: 10px;
          padding: 10px 10px 10px 0;
          border: 0;
          border-radius: 14px;
          background: transparent;
          color: #111827;
          text-align: left;
          cursor: pointer;
        }

        .row:hover {
          background: #eef4ff;
        }

        .row.active {
          background: #eaf3ff;
        }

        .dot {
          width: 3px;
          height: 22px;
          border-radius: 999px;
          background: transparent;
          justify-self: center;
        }

        .dot.active {
          background: #2f80ed;
        }

        .row-icon {
          width: 28px;
          height: 28px;
          border-radius: 10px;
          background: #f2f5f9;
          color: #62748a;
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }

        .row.active .row-icon {
          background: #dbeafe;
          color: #2f80ed;
        }

        .row-main {
          min-width: 0;
          display: grid;
          gap: 4px;
        }

        .row-title {
          font-size: 14px;
          font-weight: 600;
          color: #1f2937;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .row-date {
          font-size: 12px;
          color: #8a94a6;
        }

        .current-pill {
          padding: 2px 8px;
          border-radius: 999px;
          background: #ffffff;
          border: 1px solid #cfe0ff;
          font-size: 12px;
          color: #2f80ed;
        }
      `}</style>
    </section>
  );
}
