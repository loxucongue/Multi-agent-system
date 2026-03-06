"use client";

import { SendOutlined } from "@ant-design/icons";
import { Button, Input, Typography } from "antd";
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

  const helperText = messages.length === 0 && !isStreaming ? "发送消息开始咨询" : "继续提问或使用快捷功能";

  return (
    <div
      style={{
        borderTop: "1px solid #e8edf7",
        paddingTop: 12,
        marginTop: 10,
        background: "#f9fbff",
      }}
    >
      <div style={{ marginBottom: 8 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {helperText}
        </Text>
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
        <Input.TextArea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onPressEnter={handlePressEnter}
          placeholder="输入您的旅游需求，例如：想去三亚5天，预算1万元"
          autoSize={{ minRows: 2, maxRows: 6 }}
          disabled={isStreaming}
          style={{
            borderRadius: 16,
            borderColor: "#dbe3f3",
            background: "#fff",
          }}
        />
        <Button
          type="primary"
          shape="circle"
          icon={<SendOutlined />}
          loading={isStreaming}
          disabled={!text.trim() || isStreaming}
          onClick={() => {
            void doSend(text);
          }}
          style={{ width: 44, height: 44 }}
        />
      </div>
    </div>
  );
}
