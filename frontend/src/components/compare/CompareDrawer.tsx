"use client";

import { CloseOutlined, RobotOutlined, SwapOutlined } from "@ant-design/icons";
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

const formatPrice = (item: CompareRouteItem) =>
  `¥${item.price_range.min} - ¥${item.price_range.max} ${item.price_range.currency}`.trim();

const rowDefs: RowDef[] = [
  { key: "days", label: "行程天数", render: (item) => <Text>{item.days} 天</Text> },
  {
    key: "highlights",
    label: "核心亮点",
    render: (item) => (
      <Space wrap>
        {item.highlights.map((highlight) => (
          <Tag key={`${item.route_id}-${highlight}`} style={{ borderRadius: 999 }}>
            {highlight}
          </Tag>
        ))}
      </Space>
    ),
  },
  { key: "itinerary_style", label: "行程风格", render: (item) => <Text>{item.itinerary_style}</Text> },
  { key: "price_range", label: "价格区间", render: (item) => <Text>{formatPrice(item)}</Text> },
  { key: "next_schedule", label: "最近团期", render: (item) => <Text>{item.next_schedule.date ?? "暂无"}</Text> },
  {
    key: "suitable_for",
    label: "适合人群",
    render: (item) =>
      item.suitable_for.length > 0 ? (
        <Space wrap>
          {item.suitable_for.map((value) => (
            <Tag key={`${item.route_id}-${value}`} color="blue" style={{ borderRadius: 999 }}>
              {value}
            </Tag>
          ))}
        </Space>
      ) : (
        <Text type="secondary">暂无</Text>
      ),
  },
  {
    key: "included_summary",
    label: "费用包含",
    render: (item) => (
      <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 3, tooltip: item.included_summary }}>
        {item.included_summary}
      </Paragraph>
    ),
  },
  {
    key: "notice_summary",
    label: "注意事项",
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
      const runId = await sendMessage(`我对 ${item.name} 更感兴趣，请继续介绍这条路线并给出报名建议。`);
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
    <div role="dialog" aria-modal="true" onClick={onClose} className="compare-mask">
      <div onClick={(event) => event.stopPropagation()} className="compare-shell">
        <div className="compare-header">
          <div>
            <Text type="secondary">路线对比</Text>
            <Title level={4} style={{ margin: "4px 0 0" }}>
              同屏比较不同路线的价格、亮点和适配人群
            </Title>
          </div>
          <Button type="text" icon={<CloseOutlined />} onClick={onClose} aria-label="关闭对比弹层" />
        </div>

        <div className="compare-body">
          {routes.length === 0 ? (
            <Empty description="暂无对比数据" />
          ) : (
            <>
              <div className="route-overview">
                {routes.map((item, index) => (
                  <div key={item.route_id} className="overview-card">
                    <Space wrap size={[8, 8]}>
                      <Tag color={index === 0 ? "blue" : "default"}>{index === 0 ? "优先关注" : "参与对比"}</Tag>
                      <Tag>{item.days} 天</Tag>
                    </Space>
                    <Title level={5} style={{ margin: "12px 0 6px" }}>
                      {item.name}
                    </Title>
                    <div className="overview-metric">{formatPrice(item)}</div>
                    <Text type="secondary">最近团期：{item.next_schedule.date ?? "暂无"}</Text>
                  </div>
                ))}
              </div>

              <div className="compare-table-wrap">
                <table className="compare-table">
                  <thead>
                    <tr>
                      <th>对比维度</th>
                      {routes.map((item) => (
                        <th key={item.route_id}>{item.name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rowDefs.map((row) => (
                      <tr key={row.key}>
                        <td className="row-label">{row.label}</td>
                        {routes.map((item) => (
                          <td key={`${row.key}-${item.route_id}`}>{row.render(item)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div className="compare-footer">
          <Button
            type="primary"
            size="large"
            icon={<RobotOutlined />}
            loading={aiCompareLoading}
            disabled={isStreaming}
            onClick={onAICompare}
            style={{ borderRadius: 12, fontWeight: 600 }}
          >
            AI 生成对比分析
          </Button>

          <Space wrap>
            {routes.map((item) => (
              <Button
                key={`interest-${item.route_id}`}
                size="large"
                icon={<SwapOutlined />}
                loading={pendingRouteId === item.route_id}
                disabled={isStreaming || (pendingRouteId !== null && pendingRouteId !== item.route_id)}
                onClick={() => {
                  void handleInterest(item);
                }}
                style={{ borderRadius: 12 }}
              >
                深入了解 {item.name}
              </Button>
            ))}
          </Space>
        </div>
      </div>

      <style jsx>{`
        .compare-mask {
          position: fixed;
          inset: 0;
          z-index: 1450;
          padding: 20px;
          background: rgba(15, 23, 42, 0.45);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .compare-shell {
          width: min(1100px, 100%);
          max-height: 90vh;
          border-radius: 24px;
          border: 1px solid #e6ebf2;
          background: #f8fafc;
          box-shadow: 0 24px 80px rgba(15, 23, 42, 0.18);
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }

        .compare-header,
        .compare-footer {
          padding: 18px 22px;
          background: #ffffff;
          border-bottom: 1px solid #e6ebf2;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          flex-wrap: wrap;
        }

        .compare-footer {
          border-top: 1px solid #e6ebf2;
          border-bottom: 0;
        }

        .compare-body {
          min-height: 0;
          overflow: auto;
          padding: 20px 22px;
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        .route-overview {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 12px;
        }

        .overview-card {
          padding: 16px;
          border-radius: 18px;
          border: 1px solid #e6ebf2;
          background: #ffffff;
        }

        .overview-metric {
          margin-bottom: 6px;
          font-weight: 700;
          color: #111827;
        }

        .compare-table-wrap {
          overflow-x: auto;
          border-radius: 18px;
          border: 1px solid #e6ebf2;
          background: #ffffff;
        }

        .compare-table {
          width: 100%;
          min-width: 760px;
          border-collapse: collapse;
        }

        .compare-table th,
        .compare-table td {
          padding: 14px 16px;
          text-align: left;
          vertical-align: top;
          border-bottom: 1px solid #eef2f7;
        }

        .compare-table thead th {
          position: sticky;
          top: 0;
          z-index: 1;
          background: #f8fafc;
          color: #111827;
        }

        .row-label {
          width: 148px;
          color: #64748b;
          font-weight: 600;
        }

        @media (max-width: 768px) {
          .compare-mask {
            padding: 10px;
          }

          .compare-shell {
            max-height: 94vh;
            border-radius: 20px;
          }

          .compare-header,
          .compare-footer,
          .compare-body {
            padding: 16px;
          }
        }
      `}</style>
    </div>
  );
}
