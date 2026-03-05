"use client";

import { Button, Card, Empty, Skeleton, Space, Tag, Typography } from "antd";

import type { RouteCard } from "@/types";

const { Paragraph, Text, Title } = Typography;

export interface ActiveRouteCardData extends Pick<RouteCard, "id" | "name" | "tags" | "summary"> {
  supplier: string;
  days: number;
  highlights: string[];
}

interface ActiveRouteCardProps {
  activeRouteId: number | null;
  route: ActiveRouteCardData | null;
  loading?: boolean;
  onViewPriceSchedule?: (route: ActiveRouteCardData) => void;
  onViewItinerary?: (route: ActiveRouteCardData) => void;
  onAddCompare?: (route: ActiveRouteCardData) => void;
}

export default function ActiveRouteCard({
  activeRouteId,
  route,
  loading = false,
  onViewPriceSchedule,
  onViewItinerary,
  onAddCompare,
}: ActiveRouteCardProps) {
  if (loading) {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (!activeRouteId || !route) {
    return (
      <Card>
        <Empty description="还没有推荐线路，试试告诉我您想去哪里？" />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space direction="vertical" size={2}>
          <Title level={5} style={{ margin: 0 }}>
            {route.name}
          </Title>
          <Text type="secondary">
            供应商：{route.supplier} · 天数：{route.days}天
          </Text>
        </Space>
      }
      extra={<Tag color="blue">当前推荐</Tag>}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <div>
          <Text strong>亮点</Text>
          <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
            {route.highlights.slice(0, 5).map((highlight) => (
              <li key={highlight} style={{ marginBottom: 4 }}>
                {highlight}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <Text strong>标签</Text>
          <div style={{ marginTop: 8 }}>
            {route.tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>
        </div>

        <div>
          <Text strong>摘要</Text>
          <Paragraph style={{ marginBottom: 0, marginTop: 8 }}>{route.summary}</Paragraph>
        </div>

        <Space wrap>
          <Button
            type="primary"
            onClick={() => {
              onViewPriceSchedule?.(route);
            }}
          >
            查看价格&团期
          </Button>
          <Button
            onClick={() => {
              onViewItinerary?.(route);
            }}
          >
            查看详细行程
          </Button>
          <Button
            onClick={() => {
              onAddCompare?.(route);
            }}
          >
            加入对比
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
