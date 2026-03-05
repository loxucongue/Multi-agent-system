"use client";

import { Button, Space } from "antd";

import { useChatStore } from "@/stores/sessionStore";

interface QuickButtonsProps {
  onSend: (text: string) => Promise<void> | void;
}

const QUICK_ITEMS = [
  "推荐旅游线路",
  "签证咨询",
  "查看价格和团期",
];

export default function QuickButtons({ onSend }: QuickButtonsProps) {
  const { messages, stage, isStreaming } = useChatStore((state) => ({
    messages: state.messages,
    stage: state.stage,
    isStreaming: state.isStreaming,
  }));

  const shouldShow = messages.length === 0 || stage === "init";
  if (!shouldShow) {
    return null;
  }

  return (
    <div style={{ marginTop: 10 }}>
      <Space wrap size={[8, 8]}>
        {QUICK_ITEMS.map((text) => (
          <Button
            key={text}
            disabled={isStreaming}
            onClick={() => {
              void onSend(text);
            }}
          >
            {text}
          </Button>
        ))}
      </Space>
    </div>
  );
}
