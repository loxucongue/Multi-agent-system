"use client";

import { SendOutlined } from "@ant-design/icons";
import { Button, Input, Skeleton, Space, Spin, Typography } from "antd";
import type { KeyboardEvent } from "react";
import { useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { useChatStore } from "@/stores/sessionStore";

const { Text } = Typography;

interface ChatInputProps {
  onSend: (text: string) => Promise<void> | void;
}

export default function ChatInput({ onSend }: ChatInputProps) {
  const [text, setText] = useState("");

  const { isStreaming, messages } = useChatStore(
    useShallow((state) => ({
      isStreaming: state.isStreaming,
      messages: state.messages,
    })),
  );

  const doSend = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || isStreaming) {
      return;
    }

    setText("");
    await onSend(trimmed);
  };

  const handlePressEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.shiftKey) {
      return;
    }
    event.preventDefault();
    void doSend(text);
  };

  const isEmptyState = messages.length === 0 && !isStreaming;
  const isLoadingState = isStreaming;

  return (
    <div
      style={{
        borderTop: "1px solid #f0f0f0",
        paddingTop: 12,
        marginTop: 12,
        background: "#fff",
      }}
    >
      {isLoadingState ? (
        <div style={{ marginBottom: 8 }}>
          <Skeleton
            active
            title={false}
            paragraph={{ rows: 1, width: ["45%"] }}
            style={{ marginBottom: 6 }}
          />
          <Space size={8}>
            <Spin size="small" />
            <Text type="secondary">正在生成回复...</Text>
          </Space>
        </div>
      ) : null}

      {isEmptyState ? (
        <div style={{ marginBottom: 8 }}>
          <Text type="secondary">发送消息开始咨询</Text>
        </div>
      ) : null}

      {!isLoadingState && !isEmptyState ? (
        <div style={{ marginBottom: 8 }}>
          <Text type="secondary">继续提问或使用快捷功能</Text>
        </div>
      ) : null}

      <div style={{ display: "flex", gap: 8 }}>
        <Input.TextArea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onPressEnter={handlePressEnter}
          placeholder="请输入您的需求，Enter 发送，Shift+Enter 换行"
          autoSize={{ minRows: 2, maxRows: 6 }}
          disabled={isStreaming}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          loading={isStreaming}
          disabled={!text.trim() || isStreaming}
          onClick={() => {
            void doSend(text);
          }}
        >
          发送
        </Button>
      </div>
    </div>
  );
}
