"use client";

import { Button, Empty, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { useSSE } from "@/hooks/useSSE";
import { useChatStore } from "@/stores/sessionStore";
import type { CompareData, CompareRouteItem } from "@/types";

const { Paragraph, Text, Title } = Typography;

interface CompareDrawerProps {
  open: boolean;
  data: CompareData | null;
  onClose: () => void;
  onAICompare?: () => void;
  aiCompareLoading?: boolean;
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
    render: (item) => <Text>{`${item.price_range.min} - ${item.price_range.max} ${item.price_range.currency}`}</Text>,
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

export default function CompareDrawer({ open, data, onClose, onAICompare, aiCompareLoading = false }: CompareDrawerProps) {
  const [pendingRouteId, setPendingRouteId] = useState<number | null>(null);
  const { connect } = useSSE();
  const { sendMessage, isStreaming } = useChatStore(
    useShallow((state) => ({
      sendMessage: state.sendMessage,
      isStreaming: state.isStreaming,
    })),
  );

  const routes = useMemo(() => data?.routes ?? [], [data?.routes]);

  const handleInterest = async (item: CompareRouteItem) => {
    if (isStreaming || pendingRouteId !== null) {
      return;
    }
    setPendingRouteId(item.route_id);
    try {
      const runId = await sendMessage(`我对 ${item.name} 感兴趣，想进一步了解。`);
      if (runId) {
        connect(runId);
      }
    } finally {
      setPendingRouteId(null);
    }
  };

  if (!open) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1450,
        background: "rgba(15, 23, 42, 0.35)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        style={{
          width: "min(88vw, 980px)",
          aspectRatio: "1 / 1",
          maxHeight: "88vh",
          background: "#fff",
          borderRadius: 20,
          boxShadow: "0 24px 60px rgba(0, 0, 0, 0.28)",
          border: "1px solid #e5e7eb",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          animation: "compare-pop 180ms ease-out",
        }}
      >
        <div
          style={{
            height: 56,
            borderBottom: "1px solid #eef0f4",
            padding: "0 16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexShrink: 0,
            background: "#fff",
          }}
        >
          <Title level={5} style={{ margin: 0 }}>
            路线对比
          </Title>
          <Button type="text" onClick={onClose}>
            关闭
          </Button>
        </div>

        <div style={{ padding: 16, overflowY: "auto", minHeight: 0, flex: 1 }}>
          {routes.length === 0 ? (
            <Empty description="暂无对比数据" />
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 680 }}>
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
                          minWidth: 200,
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
            </div>
          )}
        </div>

        <div
          style={{
            borderTop: "1px solid #eef0f4",
            padding: "12px 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            flexShrink: 0,
            background: "#fff",
          }}
        >
          <Button type="primary" loading={aiCompareLoading} disabled={isStreaming} onClick={onAICompare}>
            AI 对比分析（2条）
          </Button>

          <Space wrap>
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
          </Space>
        </div>
      </div>

      <style jsx>{`
        @keyframes compare-pop {
          from {
            transform: translateY(6px) scale(0.98);
            opacity: 0;
          }
          to {
            transform: translateY(0) scale(1);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
