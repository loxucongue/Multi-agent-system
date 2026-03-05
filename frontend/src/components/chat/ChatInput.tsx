"use client";

import {
  DeploymentUnitOutlined,
  DollarOutlined,
  EnvironmentOutlined,
  PhoneOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
} from "@ant-design/icons";
import { Button, Input, Skeleton, Space, Spin, Typography } from "antd";
import type { KeyboardEvent, ReactNode } from "react";
import { useMemo, useState } from "react";

import { useSSE } from "@/hooks/useSSE";
import { useChatStore } from "@/stores/sessionStore";

const { Text } = Typography;

interface QuickAction {
  key: string;
  label: string;
  message: string;
  icon: ReactNode;
  disabled: boolean;
}

export default function ChatInput() {
  const [text, setText] = useState("");
  const { connect } = useSSE();

  const { sendMessage, isStreaming, activeRouteId, candidateRouteIds, leadStatus, messages } =
    useChatStore((state) => ({
      sendMessage: state.sendMessage,
      isStreaming: state.isStreaming,
      activeRouteId: state.activeRouteId,
      candidateRouteIds: state.candidateRouteIds,
      leadStatus: state.leadStatus,
      messages: state.messages,
    }));

  const quickActions = useMemo<QuickAction[]>(
    () => [
      {
        key: "compare",
        label: "对比方案",
        message: "帮我对比这几条方案",
        icon: <DeploymentUnitOutlined />,
        disabled: candidateRouteIds.length < 2 || isStreaming,
      },
      {
        key: "price",
        label: "查价格团期",
        message: "帮我查一下这条线路的价格和团期",
        icon: <DollarOutlined />,
        disabled: activeRouteId === null || isStreaming,
      },
      {
        key: "rematch",
        label: "重新推荐",
        message: "请重新推荐几条线路",
        icon: <ReloadOutlined />,
        disabled: (activeRouteId === null && candidateRouteIds.length === 0) || isStreaming,
      },
      {
        key: "visa",
        label: "签证咨询",
        message: "我想咨询签证办理",
        icon: <SafetyCertificateOutlined />,
        disabled: isStreaming,
      },
      {
        key: "external",
        label: "天气交通航班",
        message: "帮我查一下目的地天气、交通和航班信息",
        icon: <EnvironmentOutlined />,
        disabled: isStreaming,
      },
      {
        key: "lead",
        label: leadStatus === "captured" ? "已提交" : "联系顾问",
        message: "我想联系顾问",
        icon: <PhoneOutlined />,
        disabled: isStreaming || leadStatus === "captured",
      },
    ],
    [activeRouteId, candidateRouteIds.length, isStreaming, leadStatus],
  );

  const doSend = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || isStreaming) {
      return;
    }

    setText("");
    const runId = await sendMessage(trimmed);
    if (runId) {
      connect(runId);
    }
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

      <Space wrap size={[8, 8]} style={{ marginBottom: 10 }}>
        {quickActions.map((action) => (
          <Button
            key={action.key}
            icon={action.icon}
            size="small"
            disabled={action.disabled}
            onClick={() => {
              void doSend(action.message);
            }}
          >
            {action.label}
          </Button>
        ))}
      </Space>

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
