"use client";

import { LoadingOutlined, RobotOutlined, UserOutlined, WarningOutlined } from "@ant-design/icons";
import { Button, Empty, Skeleton, Spin, Typography } from "antd";
import type {
  HTMLAttributes,
  LiHTMLAttributes,
  TableHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
  TrHTMLAttributes,
} from "react";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useShallow } from "zustand/react/shallow";

import { useChatStore } from "@/stores/sessionStore";
import type { ChatMessage } from "@/types";

const { Paragraph, Text, Title } = Typography;
const STREAM_CURSOR = "▍";

const markdownComponents = {
  p: (props: HTMLAttributes<HTMLParagraphElement>) => <p style={{ margin: "0 0 8px 0" }} {...props} />,
  ul: (props: HTMLAttributes<HTMLUListElement>) => <ul style={{ margin: "0 0 8px 18px" }} {...props} />,
  ol: (props: HTMLAttributes<HTMLOListElement>) => <ol style={{ margin: "0 0 8px 18px" }} {...props} />,
  li: (props: LiHTMLAttributes<HTMLLIElement>) => <li style={{ marginBottom: 4 }} {...props} />,
  table: (props: TableHTMLAttributes<HTMLTableElement>) => (
    <div
      style={{
        overflowX: "auto",
        margin: "0 0 16px 0",
        border: "1px solid #d9e2ec",
        borderRadius: 14,
        background: "#ffffff",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.6)",
      }}
    >
      <table
        style={{
          width: "100%",
          minWidth: 760,
          borderCollapse: "separate",
          borderSpacing: 0,
          background: "#ffffff",
          tableLayout: "fixed",
        }}
        {...props}
      />
    </div>
  ),
  th: (props: ThHTMLAttributes<HTMLTableCellElement>) => (
    <th
      style={{
        padding: "10px 12px",
        textAlign: "left",
        fontWeight: 600,
        fontSize: 13,
        color: "#334155",
        background: "#eef4fb",
        borderBottom: "1px solid #d9e2ec",
        borderRight: "1px solid #d9e2ec",
        lineHeight: 1.6,
      }}
      {...props}
    />
  ),
  tr: (props: TrHTMLAttributes<HTMLTableRowElement>) => <tr style={{ background: "#ffffff" }} {...props} />,
  td: (props: TdHTMLAttributes<HTMLTableCellElement>) => (
    <td
      style={{
        padding: "12px 14px",
        verticalAlign: "top",
        borderTop: "1px solid #e5eaf1",
        borderRight: "1px solid #e5eaf1",
        color: "#1f2937",
        fontSize: 13,
        lineHeight: 1.7,
        background: "#ffffff",
      }}
      {...props}
    />
  ),
};

const EMPTY_SUGGESTIONS = [
  "我想从北京出发去云南玩 6 天，预算 1.2 万，两位成人。",
  "帮我推荐适合海岛度假的路线，想轻松一些。",
  "我想先看看日本自由行和跟团的选择。",
];

const isSessionExpiredMessage = (message: ChatMessage) => {
  return message.role === "system" && message.content.includes("会话已过期");
};

function BubbleAvatar({ role }: { role: "user" | "assistant" }) {
  const isUser = role === "user";

  return (
    <>
      <span className={`avatar ${isUser ? "user" : "assistant"}`}>
        {isUser ? <UserOutlined /> : <RobotOutlined />}
      </span>

      <style jsx>{`
        .avatar {
          width: 34px;
          height: 34px;
          border-radius: 12px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          flex: 0 0 34px;
          margin-top: 18px;
        }

        .avatar.user {
          background: #eef4ff;
          color: #2f80ed;
          border: 1px solid #dbe7fb;
        }

        .avatar.assistant {
          background: #eef2f7;
          color: #4b5563;
          border: 1px solid #e1e7ef;
        }
      `}</style>
    </>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  if (message.role === "system") {
    return (
      <div className="system-row">
        <div className={`system-pill ${isSessionExpiredMessage(message) ? "warning" : ""}`}>
          {isSessionExpiredMessage(message) ? <WarningOutlined /> : null}
          {message.content}
        </div>

        <style jsx>{`
          .system-row {
            display: flex;
            justify-content: center;
            margin-bottom: 16px;
          }

          .system-pill {
            padding: 8px 12px;
            border-radius: 999px;
            background: #ffffff;
            border: 1px solid #dce4ef;
            color: #6b7280;
            font-size: 12px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
          }

          .system-pill.warning {
            background: #fff4eb;
            border-color: #ffd3ad;
            color: #c2410c;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className={`bubble-row ${isUser ? "user" : "assistant"}`}>
      {!isUser ? <BubbleAvatar role="assistant" /> : null}

      <div className="bubble-stack">
        <span className="bubble-name">{isUser ? "你" : "旅行顾问"}</span>
        <div className={`bubble ${isUser ? "user" : "assistant"}`}>
          {isUser ? (
            message.content
          ) : (
            <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          )}
        </div>
      </div>

      {isUser ? <BubbleAvatar role="user" /> : null}

      <style jsx>{`
        .bubble-row {
          display: flex;
          gap: 12px;
          margin-bottom: 22px;
          align-items: flex-start;
        }

        .bubble-row.user {
          justify-content: flex-end;
        }

        .bubble-row.assistant {
          justify-content: flex-start;
        }

        .bubble-stack {
          display: grid;
          gap: 6px;
          max-width: min(600px, 100%);
        }

        .bubble-row.user .bubble-stack {
          justify-items: end;
        }

        .bubble-name {
          font-size: 12px;
          color: #8a94a6;
        }

        .bubble {
          padding: 14px 16px;
          border-radius: 18px;
          line-height: 1.8;
          word-break: break-word;
          overflow-wrap: anywhere;
          box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
        }

        .bubble.user {
          color: #ffffff;
          background: #2f80ed;
          border-top-right-radius: 8px;
          white-space: pre-wrap;
        }

        .bubble.assistant {
          color: #1f2937;
          background: #f4f6f8;
          border: 1px solid #e6ebf2;
          border-top-left-radius: 8px;
          white-space: normal;
        }
      `}</style>
    </div>
  );
}

interface MessageListProps {
  onSend: (text: string) => Promise<void> | void;
}

export default function MessageList({ onSend }: MessageListProps) {
  const { messages, isStreaming, currentStreamText } = useChatStore(
    useShallow((state) => ({
      messages: state.messages,
      isStreaming: state.isStreaming,
      currentStreamText: state.currentStreamText,
    })),
  );

  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, currentStreamText, isStreaming]);

  const isLoading = messages.length === 0 && isStreaming && !currentStreamText;
  const isEmpty = messages.length === 0 && !isStreaming;

  if (isLoading) {
    return (
      <div ref={scrollRef} className="message-scroll loading-state">
        <Skeleton active paragraph={{ rows: 5 }} title={{ width: "30%" }} />

        <style jsx>{`
          .message-scroll {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
          }

          .loading-state {
            padding: 12px;
          }

          .loading-state :global(.ant-skeleton) {
            padding: 18px;
            border-radius: 18px;
            background: #ffffff;
            border: 1px solid #e8edf4;
          }
        `}</style>
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div ref={scrollRef} className="message-scroll empty-state">
        <div className="empty-inner">
          <div className="empty-copy">
            <Text className="eyebrow">AI Travel Assistant</Text>
            <Title level={3} style={{ margin: "8px 0 10px", color: "#111827" }}>
              先告诉我你的旅行需求，我会开始推荐路线。
            </Title>
            <Paragraph style={{ marginBottom: 0, color: "#6b7280" }}>
              可以从目的地、天数、预算、同行人或旅行偏好中的任意一项开始。
            </Paragraph>
          </div>

          <div className="suggestion-list">
            {EMPTY_SUGGESTIONS.map((item) => (
              <Button
                key={item}
                className="suggestion-chip"
                onClick={() => {
                  void onSend(item);
                }}
              >
                {item}
              </Button>
            ))}
          </div>

          <div className="empty-illustration">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="开始对话后，右侧会同步显示推荐路线与候选方案。" />
          </div>
        </div>

        <style jsx>{`
          .message-scroll {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
          }

          .empty-state {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px 16px;
          }

          .empty-inner {
            width: min(760px, 100%);
            display: grid;
            gap: 20px;
          }

          .eyebrow {
            color: #2f80ed;
            font-size: 12px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
          }

          .suggestion-list {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
          }

          .suggestion-chip {
            height: auto;
            padding: 10px 14px;
            border-radius: 999px;
            border-color: #dbe3ee;
            background: #ffffff;
            color: #4b5563;
            text-align: left;
            white-space: normal;
          }

          .empty-illustration {
            padding: 20px;
            border-radius: 18px;
            border: 1px dashed #d6dee9;
            background: #ffffff;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="message-scroll active-state">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {isStreaming && currentStreamText ? (
        <div className="bubble-row assistant">
          <BubbleAvatar role="assistant" />
          <div className="bubble-stack">
            <span className="bubble-name">旅行顾问</span>
            <div className="bubble assistant">
              <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                {currentStreamText}
              </ReactMarkdown>
              <span className="stream-cursor">{STREAM_CURSOR}</span>
            </div>
          </div>
        </div>
      ) : null}

      {isStreaming && !currentStreamText ? (
        <div className="typing-row">
          <div className="typing-pill">
            <Spin indicator={<LoadingOutlined spin />} size="small" />
            正在生成路线建议...
          </div>
        </div>
      ) : null}

      <style jsx>{`
        .message-scroll {
          flex: 1;
          min-height: 0;
          overflow-y: auto;
        }

        .active-state {
          padding: 10px 6px 8px;
        }

        .bubble-row {
          display: flex;
          gap: 12px;
          margin-bottom: 22px;
          align-items: flex-start;
        }

        .bubble-stack {
          display: grid;
          gap: 6px;
          max-width: min(600px, 100%);
        }

        .bubble-name {
          font-size: 12px;
          color: #8a94a6;
        }

        .bubble {
          padding: 14px 16px;
          border-radius: 18px;
          line-height: 1.8;
          box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
        }

        .bubble.assistant {
          color: #1f2937;
          background: #f4f6f8;
          border: 1px solid #e6ebf2;
          border-top-left-radius: 8px;
        }

        .typing-row {
          display: flex;
          justify-content: flex-start;
          padding-left: 46px;
        }

        .typing-pill {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 10px 14px;
          border-radius: 999px;
          background: #ffffff;
          border: 1px solid #dce4ef;
          color: #6b7280;
        }

        .stream-cursor {
          display: inline-block;
          margin-left: 2px;
          animation: blink 1s infinite;
        }

        @keyframes blink {
          0%,
          49% {
            opacity: 1;
          }
          50%,
          100% {
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
}
