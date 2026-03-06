"use client";

import { ArrowLeftOutlined, CloseOutlined } from "@ant-design/icons";
import { Button, Card, Collapse, Descriptions, Empty, Skeleton, Space, Tag, Typography } from "antd";

import type { RouteFullDetail } from "@/types";

const { Paragraph, Text, Title } = Typography;

interface RouteDetailPanelProps {
  data: RouteFullDetail | null;
  loading: boolean;
  onClose: () => void;
}

interface DayPlanItem {
  title: string;
  content: string;
}

const toDayPlans = (itinerary: unknown): DayPlanItem[] => {
  if (Array.isArray(itinerary)) {
    return itinerary
      .map((item, index) => {
        if (typeof item === "string") {
          return { title: `第${index + 1}天`, content: item };
        }
        if (typeof item === "object" && item !== null) {
          const obj = item as Record<string, unknown>;
          const title = String(obj.day ?? obj.title ?? `第${index + 1}天`);
          const content = String(obj.content ?? obj.description ?? obj.plan ?? "");
          return { title, content: content.trim() || "暂无行程描述" };
        }
        return null;
      })
      .filter((item): item is DayPlanItem => item !== null);
  }

  if (typeof itinerary === "string" && itinerary.trim()) {
    return [{ title: "行程概览", content: itinerary.trim() }];
  }

  return [];
};

const toScheduleDates = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }

  const dates = value
    .map((item) => {
      if (typeof item === "string") {
        return item.trim();
      }
      if (typeof item === "object" && item !== null) {
        const record = item as Record<string, unknown>;
        return String(record.date ?? record.depart_date ?? "").trim();
      }
      return "";
    })
    .filter((item) => item.length > 0);

  return Array.from(new Set(dates)).slice(0, 5);
};

export default function RouteDetailPanel({ data, loading, onClose }: RouteDetailPanelProps) {
  if (loading) {
    return (
      <Card
        title="路线详情"
        extra={<Button icon={<CloseOutlined />} onClick={onClose} />}
      >
        <Skeleton active paragraph={{ rows: 10 }} />
      </Card>
    );
  }

  if (!data) {
    return (
      <Card
        title="路线详情"
        extra={<Button icon={<CloseOutlined />} onClick={onClose} />}
      >
        <Empty description="暂无路线详情" />
      </Card>
    );
  }

  const { route, pricing, schedule } = data;
  const dayPlans = toDayPlans(route.itinerary_json);
  const scheduleDates = toScheduleDates(schedule?.schedules_json);

  return (
    <Card
      title={
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={onClose}>
            返回
          </Button>
          <Title level={5} style={{ margin: 0 }}>
            路线详情
          </Title>
        </Space>
      }
      extra={<Button icon={<CloseOutlined />} onClick={onClose} />}
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <div>
          <Title level={5} style={{ margin: 0 }}>
            {route.name}
          </Title>
          <Text type="secondary">供应商：{route.supplier}</Text>
        </div>

        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="标签">
            <Space wrap>
              {route.tags.map((tag) => (
                <Tag key={`${route.id}-${String(tag)}`}>{String(tag)}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="摘要">{route.summary}</Descriptions.Item>
          <Descriptions.Item label="亮点摘要">
            <Paragraph style={{ marginBottom: 0 }}>{route.highlights || "暂无"}</Paragraph>
          </Descriptions.Item>
        </Descriptions>

        <div>
          <Title level={5}>每日行程</Title>
          {dayPlans.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无行程信息" />
          ) : (
            <Collapse
              items={dayPlans.map((item, index) => ({
                key: String(index + 1),
                label: item.title,
                children: <Paragraph style={{ marginBottom: 0 }}>{item.content}</Paragraph>,
              }))}
            />
          )}
        </div>

        <div id="route-detail-included">
          <Title level={5}>费用包含 / 不含</Title>
          <Paragraph style={{ marginBottom: 8 }}>
            <Text strong>费用包含：</Text>
            {route.included || "暂无"}
          </Paragraph>
        </div>

        <div>
          <Title level={5}>注意事项</Title>
          <Paragraph style={{ marginBottom: 0 }}>{route.notice || "暂无"}</Paragraph>
        </div>

        <div id="route-detail-price">
          <Title level={5}>价格与团期</Title>
          {pricing ? (
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="价格区间">
                {pricing.price_min} - {pricing.price_max} {pricing.currency}
              </Descriptions.Item>
              <Descriptions.Item label="价格更新时间">
                {pricing.price_updated_at}
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Text type="secondary">暂无价格信息</Text>
          )}

          <div style={{ marginTop: 12 }}>
            <Text strong>最近团期：</Text>
            {scheduleDates.length === 0 ? (
              <Text type="secondary"> 暂无团期信息</Text>
            ) : (
              <Space wrap style={{ marginLeft: 8 }}>
                {scheduleDates.map((date) => (
                  <Tag key={date} color="blue">
                    {date}
                  </Tag>
                ))}
              </Space>
            )}
          </div>
        </div>
      </Space>
    </Card>
  );
}
