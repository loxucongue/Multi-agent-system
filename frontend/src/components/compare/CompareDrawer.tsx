"use client";

import { Button, Drawer, Empty, Space, Tag, Typography } from "antd";
import { useState } from "react";
import type { ReactNode } from "react";
import { useShallow } from "zustand/react/shallow";

import { useSSE } from "@/hooks/useSSE";
import { useChatStore } from "@/stores/sessionStore";
import type { CompareData, CompareRouteItem } from "@/types";

const { Paragraph, Text } = Typography;

interface CompareDrawerProps {
  open: boolean;
  data: CompareData | null;
  onClose: () => void;
}

interface RowDef {
  key: string;
  label: string;
  render: (item: CompareRouteItem) => ReactNode;
}

const rowDefs: RowDef[] = [
  {
    key: "days",
    label: "天数",
    render: (item) => <Text>{item.days} 天</Text>,
  },
  {
    key: "highlights",
    label: "亮点",
    render: (item) => (
      <Space wrap>
        {item.highlights.map((highlight) => (
          <Tag key={`${item.route_id}-${highlight}`}>{highlight}</Tag>
        ))}
      </Space>
    ),
  },
  {
    key: "itinerary_style",
    label: "行程风格",
    render: (item) => <Text>{item.itinerary_style}</Text>,
  },
  {
    key: "price_range",
    label: "价格区间",
    render: (item) => (
      <Text>{`${item.price_range.min} - ${item.price_range.max} ${item.price_range.currency}`}</Text>
    ),
  },
  {
    key: "next_schedule",
    label: "最近团期",
    render: (item) => <Text>{item.next_schedule.date ?? "暂无"}</Text>,
  },
  {
    key: "suitable_for",
    label: "适合人群",
    render: (item) => (
      <Space wrap>
        {item.suitable_for.length > 0 ? (
          item.suitable_for.map((v) => <Tag key={`${item.route_id}-${v}`}>{v}</Tag>)
        ) : (
          <Text type="secondary">暂无</Text>
        )}
      </Space>
    ),
  },
  {
    key: "included_summary",
    label: "费用包含摘要",
    render: (item) => (
      <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 3, tooltip: item.included_summary }}>
        {item.included_summary}
      </Paragraph>
    ),
  },
  {
    key: "notice_summary",
    label: "注意事项摘要",
    render: (item) => (
      <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 3, tooltip: item.notice_summary }}>
        {item.notice_summary}
      </Paragraph>
    ),
  },
];

export default function CompareDrawer({ open, data, onClose }: CompareDrawerProps) {
  const [pendingRouteId, setPendingRouteId] = useState<number | null>(null);
  const { connect } = useSSE();
  const { sendMessage, isStreaming } = useChatStore(
    useShallow((state) => ({
      sendMessage: state.sendMessage,
      isStreaming: state.isStreaming,
    })),
  );

  const routes = data?.routes ?? [];

  const handleInterest = async (item: CompareRouteItem) => {
    if (isStreaming || pendingRouteId !== null) {
      return;
    }
    setPendingRouteId(item.route_id);
    try {
      const runId = await sendMessage(`我对 ${item.name} 感兴趣，想进一步了解`);
      if (runId) {
        connect(runId);
      }
    } finally {
      setPendingRouteId(null);
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={720}
      placement="right"
      title="线路对比"
      styles={{ body: { paddingBottom: 96 } }}
    >
      {routes.length === 0 ? (
        <Empty description="暂无对比数据" />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
            <thead>
              <tr>
                <th
                  style={{
                    textAlign: "left",
                    borderBottom: "1px solid #f0f0f0",
                    padding: "10px 8px",
                    background: "#fafafa",
                    minWidth: 130,
                  }}
                >
                  对比维度
                </th>
                {routes.map((item) => (
                  <th
                    key={item.route_id}
                    style={{
                      textAlign: "left",
                      borderBottom: "1px solid #f0f0f0",
                      padding: "10px 8px",
                      minWidth: 190,
                    }}
                  >
                    {item.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rowDefs.map((row) => (
                <tr key={row.key}>
                  <td
                    style={{
                      borderBottom: "1px solid #f5f5f5",
                      padding: "10px 8px",
                      verticalAlign: "top",
                      color: "#595959",
                      background: "#fafafa",
                    }}
                  >
                    {row.label}
                  </td>
                  {routes.map((item) => (
                    <td
                      key={`${row.key}-${item.route_id}`}
                      style={{
                        borderBottom: "1px solid #f5f5f5",
                        padding: "10px 8px",
                        verticalAlign: "top",
                      }}
                    >
                      {row.render(item)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <div
            style={{
              marginTop: 14,
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              justifyContent: "flex-end",
            }}
          >
            {routes.map((item) => (
              <Button
                key={`interest-${item.route_id}`}
                type="primary"
                ghost
                loading={pendingRouteId === item.route_id}
                disabled={isStreaming || (pendingRouteId !== null && pendingRouteId !== item.route_id)}
                onClick={() => {
                  void handleInterest(item);
                }}
              >
                我对 {item.name} 感兴趣
              </Button>
            ))}
          </div>
        </div>
      )}
    </Drawer>
  );
}
