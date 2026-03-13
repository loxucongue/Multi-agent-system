"use client";

import { CompassOutlined, ScheduleOutlined, TeamOutlined } from "@ant-design/icons";
import { Button, Space, Typography } from "antd";
import { useShallow } from "zustand/react/shallow";

import { useChatStore } from "@/stores/sessionStore";

const { Text } = Typography;

interface QuickButtonsProps {
  onSend: (text: string) => Promise<void> | void;
}

const QUICK_ITEMS = [
  {
    label: "海岛度假",
    value: "请推荐适合海岛度假的热门路线，节奏轻松一些。",
    icon: <CompassOutlined />,
  },
  {
    label: "亲子出行",
    value: "帮我规划一条适合亲子家庭的旅行路线，优先考虑轻松和安全。",
    icon: <TeamOutlined />,
  },
  {
    label: "先看报价",
    value: "我想先看看热门路线的大致报价和最近团期。",
    icon: <ScheduleOutlined />,
  },
];

export default function QuickButtons({ onSend }: QuickButtonsProps) {
  const { messages, stage, isStreaming } = useChatStore(
    useShallow((state) => ({
      messages: state.messages,
      stage: state.stage,
      isStreaming: state.isStreaming,
    })),
  );

  if (!(messages.length === 0 || stage === "init")) {
    return null;
  }

  return (
    <div className="quick-shell">
      <Text type="secondary" style={{ fontSize: 12 }}>
        也可以这样开始
      </Text>

      <Space wrap size={[10, 10]}>
        {QUICK_ITEMS.map((item) => (
          <Button
            key={item.label}
            icon={item.icon}
            disabled={isStreaming}
            onClick={() => {
              void onSend(item.value);
            }}
            className="quick-button"
          >
            {item.label}
          </Button>
        ))}
      </Space>

      <style jsx>{`
        .quick-shell {
          display: grid;
          gap: 10px;
        }

        .quick-button {
          height: 36px;
          border-radius: 999px;
          border-color: #dce4ef;
          background: #ffffff;
          color: #475569;
          font-weight: 500;
          box-shadow: none;
        }
      `}</style>
    </div>
  );
}
