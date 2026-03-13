"use client";

import { ArrowUpOutlined } from "@ant-design/icons";
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

  const helperText =
    messages.length === 0 && !isStreaming
      ? "先输入你的第一条旅行需求。"
      : "可以继续补充预算、天数、同行人、出发地或偏好。";

  const doSend = async (value: string) => {
    const trimmed = value.trim();
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

  return (
    <div className="input-shell">
      <div className="input-meta">
        <Text type="secondary">{helperText}</Text>
        <Text type="secondary">Enter 发送，Shift + Enter 换行</Text>
      </div>

      <div className="input-row">
        <Input.TextArea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onPressEnter={handlePressEnter}
          placeholder="例如：我想从北京出发去云南 6 天，预算 1.2 万，两位成人，节奏轻松一些"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={isStreaming}
          className="chat-textarea"
        />

        <Button
          type="primary"
          shape="circle"
          icon={<ArrowUpOutlined />}
          loading={isStreaming}
          disabled={!text.trim() || isStreaming}
          onClick={() => {
            void doSend(text);
          }}
          className="send-button"
        />
      </div>

      <style jsx>{`
        .input-shell {
          display: grid;
          gap: 10px;
          padding: 14px;
          border-radius: 20px;
          border: 1px solid #e2e8f0;
          background: #ffffff;
          box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06);
        }

        .input-meta {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
          font-size: 12px;
        }

        .input-row {
          display: flex;
          align-items: flex-end;
          gap: 10px;
        }

        .input-row :global(.chat-textarea textarea) {
          min-height: 56px !important;
          padding: 16px 18px;
          border-radius: 16px;
          border-color: #d9e2ec;
          background: #fbfcfd;
          resize: none;
          line-height: 1.7;
        }

        .send-button {
          width: 48px;
          min-width: 48px;
          height: 48px;
          box-shadow: none;
        }

        @media (max-width: 768px) {
          .input-shell {
            padding: 12px;
          }

          .input-meta {
            justify-content: flex-start;
          }
        }
      `}</style>
    </div>
  );
}
