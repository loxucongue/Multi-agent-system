"use client";

import { CompassOutlined, LoadingOutlined, RobotOutlined, UserOutlined, WarningOutlined } from "@ant-design/icons";
import { Empty, Skeleton, Space, Spin } from "antd";
import { useEffect, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import ReactMarkdown from "react-markdown";

import { useChatStore } from "@/stores/sessionStore";
import type { ChatMessage } from "@/types";

const STREAM_CURSOR = "▍";

const markdownComponents = {
  p: (props: React.HTMLAttributes<HTMLParagraphElement>) => <p style={{ margin: "0 0 8px 0" }} {...props} />,
  ul: (props: React.HTMLAttributes<HTMLUListElement>) => <ul style={{ margin: "0 0 8px 18px" }} {...props} />,
  ol: (props: React.HTMLAttributes<HTMLOListElement>) => <ol style={{ margin: "0 0 8px 18px" }} {...props} />,
  li: (props: React.LiHTMLAttributes<HTMLLIElement>) => <li style={{ marginBottom: 4 }} {...props} />,
};

const isSessionExpiredMessage = (message: ChatMessage): boolean => {
  return message.role === "system" && message.content.includes("会话已过期");
};

const renderBubble = (message: ChatMessage) => {
  if (message.role === "user") {
    return (
      <div key={message.id} style={{ display: "flex", justifyContent: "flex-end", marginBottom: 14 }}>
        <div style={{ maxWidth: "78%", display: "flex", alignItems: "flex-start", gap: 8 }}>
          <div
            style={{
              background: "linear-gradient(135deg, #1f5eff 0%, #2b6cff 100%)",
              color: "#fff",
              borderRadius: 16,
              padding: "12px 16px",
              lineHeight: 1.75,
              whiteSpace: "pre-wrap",
              boxShadow: "0 8px 20px rgba(31, 94, 255, 0.18)",
            }}
          >
            {message.content}
          </div>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 15,
              background: "#eef2fb",
              border: "1px solid #dde5f5",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#5f7297",
            }}
          >
            <UserOutlined />
          </div>
        </div>
      </div>
    );
  }

  if (message.role === "assistant") {
    return (
      <div key={message.id} style={{ display: "flex", justifyContent: "flex-start", marginBottom: 14 }}>
        <div style={{ maxWidth: "82%", display: "flex", alignItems: "flex-start", gap: 8 }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 15,
              background: "#1f7fd6",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#fff",
            }}
          >
            <RobotOutlined />
          </div>
          <div
            style={{
              background: "#ffffff",
              border: "1px solid #e6ebf5",
              borderRadius: 16,
              padding: "12px 16px",
              lineHeight: 1.75,
              boxShadow: "0 8px 18px rgba(30, 53, 90, 0.06)",
            }}
          >
            <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
          </div>
        </div>
      </div>
    );
  }

  if (isSessionExpiredMessage(message)) {
    return (
      <div key={message.id} style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
        <div
          style={{
            display: "inline-flex",
            gap: 6,
            alignItems: "center",
            color: "#cf1322",
            background: "#fff1f0",
            border: "1px solid #ffa39e",
            borderRadius: 999,
            padding: "4px 10px",
            fontSize: 12,
          }}
        >
          <WarningOutlined />
          <span>{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div key={message.id} style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
      <div
        style={{
          color: "#6c7894",
          background: "#f6f8fc",
          border: "1px solid #e8edf7",
          borderRadius: 999,
          padding: "5px 12px",
          fontSize: 12,
        }}
      >
        {message.content}
      </div>
    </div>
  );
};

export default function MessageList() {
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
      <div ref={scrollRef} style={{ overflowY: "auto", flex: 1, padding: "8px 4px" }}>
        <Skeleton active paragraph={{ rows: 4 }} title={{ width: "35%" }} style={{ background: "#fff", borderRadius: 14, padding: 16 }} />
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div
        ref={scrollRef}
        style={{
          overflowY: "auto",
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
        }}
      >
        <Empty image={<CompassOutlined style={{ fontSize: 48, color: "#1f5eff" }} />} description="您好！我是您的专属旅游顾问，请告诉我您想去哪里。" />
      </div>
    );
  }

  return (
    <div ref={scrollRef} style={{ overflowY: "auto", flex: 1, padding: "8px 4px" }}>
      {messages.map(renderBubble)}

      {isStreaming && currentStreamText ? (
        <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 12 }}>
          <div style={{ maxWidth: "82%", display: "flex", alignItems: "flex-start", gap: 8 }}>
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: 15,
                background: "#1f7fd6",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
              }}
            >
              <RobotOutlined />
            </div>
            <div
              style={{
                background: "#ffffff",
                border: "1px solid #e6ebf5",
                borderRadius: 16,
                padding: "12px 16px",
                lineHeight: 1.75,
              }}
            >
              <ReactMarkdown components={markdownComponents}>{currentStreamText}</ReactMarkdown>
              <span className="stream-cursor">{STREAM_CURSOR}</span>
            </div>
          </div>
        </div>
      ) : null}

      {isStreaming && !currentStreamText ? (
        <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 12 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: "#fff",
              border: "1px solid #e6ebf5",
              borderRadius: 14,
              padding: "10px 14px",
              color: "#4d5d79",
            }}
          >
            <Spin indicator={<LoadingOutlined spin />} size="small" />
            <span>正在思考...</span>
          </div>
        </div>
      ) : null}

      <style jsx>{`
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
