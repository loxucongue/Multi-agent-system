"use client";

import { CompassOutlined, LoadingOutlined, WarningOutlined } from "@ant-design/icons";
import { Empty, Skeleton, Spin } from "antd";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

import { useChatStore } from "@/stores/sessionStore";
import type { ChatMessage } from "@/types";

const STREAM_CURSOR = "▍";

const markdownComponents = {
  p: (props: React.HTMLAttributes<HTMLParagraphElement>) => (
    <p style={{ margin: "0 0 8px 0" }} {...props} />
  ),
  ul: (props: React.HTMLAttributes<HTMLUListElement>) => (
    <ul style={{ margin: "0 0 8px 18px" }} {...props} />
  ),
  ol: (props: React.HTMLAttributes<HTMLOListElement>) => (
    <ol style={{ margin: "0 0 8px 18px" }} {...props} />
  ),
  li: (props: React.LiHTMLAttributes<HTMLLIElement>) => <li style={{ marginBottom: 4 }} {...props} />,
};

const isSessionExpiredMessage = (message: ChatMessage): boolean => {
  return message.role === "system" && message.content.includes("会话已过期");
};

const renderBubble = (message: ChatMessage) => {
  if (message.role === "user") {
    return (
      <div key={message.id} style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <div
          style={{
            maxWidth: "78%",
            background: "#1677ff",
            color: "#fff",
            borderRadius: 12,
            padding: "10px 14px",
            lineHeight: 1.7,
            whiteSpace: "pre-wrap",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "assistant") {
    return (
      <div key={message.id} style={{ display: "flex", justifyContent: "flex-start", marginBottom: 12 }}>
        <div
          style={{
            maxWidth: "78%",
            background: "#fff",
            border: "1px solid #f0f0f0",
            borderRadius: 12,
            padding: "10px 14px",
            lineHeight: 1.75,
          }}
        >
          <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  if (isSessionExpiredMessage(message)) {
    return (
      <div
        key={message.id}
        style={{
          display: "flex",
          justifyContent: "center",
          marginBottom: 12,
        }}
      >
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
    <div
      key={message.id}
      style={{
        display: "flex",
        justifyContent: "center",
        marginBottom: 12,
      }}
    >
      <div
        style={{
          color: "#8c8c8c",
          background: "#fafafa",
          border: "1px solid #f0f0f0",
          borderRadius: 999,
          padding: "4px 10px",
          fontSize: 12,
        }}
      >
        {message.content}
      </div>
    </div>
  );
};

export default function MessageList() {
  const { messages, isStreaming, currentStreamText } = useChatStore((state) => ({
    messages: state.messages,
    isStreaming: state.isStreaming,
    currentStreamText: state.currentStreamText,
  }));

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
      <div ref={scrollRef} style={{ overflowY: "auto", flex: 1, paddingRight: 4 }}>
        <Skeleton
          active
          avatar={{ shape: "circle" }}
          paragraph={{ rows: 4 }}
          title={{ width: "35%" }}
          style={{ background: "#fff", borderRadius: 12, padding: 16 }}
        />
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
        <Empty
          image={<CompassOutlined style={{ fontSize: 48, color: "#1677ff" }} />}
          description="您好！我是旅游路线顾问，请告诉我您想去哪里旅游？"
        />
      </div>
    );
  }

  return (
    <div ref={scrollRef} style={{ overflowY: "auto", flex: 1, paddingRight: 4 }}>
      {messages.map(renderBubble)}

      {isStreaming && currentStreamText ? (
        <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 12 }}>
          <div
            style={{
              maxWidth: "78%",
              background: "#fff",
              border: "1px solid #f0f0f0",
              borderRadius: 12,
              padding: "10px 14px",
              lineHeight: 1.75,
              whiteSpace: "pre-wrap",
            }}
          >
            <ReactMarkdown components={markdownComponents}>{currentStreamText}</ReactMarkdown>
            <span className="stream-cursor">{STREAM_CURSOR}</span>
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
              border: "1px solid #f0f0f0",
              borderRadius: 12,
              padding: "10px 14px",
              color: "#595959",
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
