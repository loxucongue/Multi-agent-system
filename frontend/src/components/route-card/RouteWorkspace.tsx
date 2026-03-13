"use client";

import { BarChartOutlined, CompassOutlined, ProfileOutlined } from "@ant-design/icons";
import { Button, Empty, Tabs, Tag, Typography } from "antd";
import { useMemo, useState } from "react";

import type { CompareData, RouteCard } from "@/types";
import ActiveRouteCard, { type ActiveRouteCardData } from "./ActiveRouteCard";
import CandidateCards from "./CandidateCards";

const { Paragraph, Text, Title } = Typography;

interface RouteWorkspaceProps {
  activeRouteId: number | null;
  activeRoute: ActiveRouteCardData | null;
  activeCheckedForCompare: boolean;
  onActiveCheckedForCompareChange: (checked: boolean) => void;
  candidateCards: RouteCard[];
  candidateCheckedRouteIds: number[];
  onCandidateCheckedRouteIdsChange: (routeIds: number[]) => void;
  compareSelectedCount: number;
  compareData: CompareData | null;
  aiCompareLoading: boolean;
  onOpenRouteDetail: (routeId: number, scrollToPrice?: boolean) => void;
  onGuideRematch: () => void;
  onCompare: (routeIds: number[]) => void;
  onOpenCompareDrawer: () => void;
  onAICompare: () => void;
}

export default function RouteWorkspace({
  activeRouteId,
  activeRoute,
  activeCheckedForCompare,
  onActiveCheckedForCompareChange,
  candidateCards,
  candidateCheckedRouteIds,
  onCandidateCheckedRouteIdsChange,
  compareSelectedCount,
  compareData,
  aiCompareLoading,
  onOpenRouteDetail,
  onGuideRematch,
  onCompare,
  onOpenCompareDrawer,
  onAICompare,
}: RouteWorkspaceProps) {
  const [activeTab, setActiveTab] = useState("featured");

  const compareRoutes = useMemo(() => compareData?.routes ?? [], [compareData]);

  return (
    <div className="workspace-shell">
      <div className="workspace-head">
        <Text type="secondary">路线工作区</Text>
        <Title level={5} style={{ margin: "4px 0", color: "#111827" }}>
          主推、候选、对比三段式浏览
        </Title>
        <Paragraph style={{ margin: 0, color: "#6b7280" }}>
          当前共展示 {Number(Boolean(activeRoute)) + candidateCards.length} 条路线，已选 {compareSelectedCount} 条进入对比池。
        </Paragraph>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "featured",
            label: (
              <span className="tab-label">
                <CompassOutlined />
                主推路线
              </span>
            ),
            children: (
              <ActiveRouteCard
                activeRouteId={activeRouteId}
                route={activeRoute}
                compareChecked={activeCheckedForCompare}
                onCompareCheckedChange={onActiveCheckedForCompareChange}
                onViewItinerary={(route) => {
                  onOpenRouteDetail(route.id);
                }}
              />
            ),
          },
          {
            key: "candidates",
            label: (
              <span className="tab-label">
                <ProfileOutlined />
                候选方案
              </span>
            ),
            children: (
              <CandidateCards
                cards={candidateCards}
                selectedRouteIds={candidateCheckedRouteIds}
                onSelectedRouteIdsChange={onCandidateCheckedRouteIdsChange}
                extraSelectedCount={activeCheckedForCompare && activeRouteId !== null ? 1 : 0}
                onGuideRematch={onGuideRematch}
                onSelect={(routeId) => onOpenRouteDetail(routeId)}
                onCompare={onCompare}
              />
            ),
          },
          {
            key: "compare",
            label: (
              <span className="tab-label">
                <BarChartOutlined />
                对比分析
              </span>
            ),
            children: (
              <div className="compare-tab">
                {compareRoutes.length < 2 ? (
                  <div className="compare-empty">
                    <Empty
                      description={
                        compareSelectedCount >= 2
                          ? "已满足对比数量，请在候选方案中点击“开始对比”。"
                          : "至少选择 2 条路线后，系统会在这里展示对比结果。"
                      }
                    />
                  </div>
                ) : (
                  <>
                    <div className="compare-preview">
                      {compareRoutes.map((route) => (
                        <div key={route.route_id} className="preview-card">
                          <div className="preview-top">
                            <Title level={5} style={{ margin: 0, color: "#111827" }}>
                              {route.name}
                            </Title>
                            <Tag>{route.days} 天</Tag>
                          </div>

                          <Text type="secondary">
                            ¥{route.price_range.min} - ¥{route.price_range.max} {route.price_range.currency}
                          </Text>

                          <div className="preview-tags">
                            {route.suitable_for.slice(0, 3).map((item) => (
                              <Tag key={`${route.route_id}-${item}`}>{item}</Tag>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="compare-actions">
                      <Button type="primary" onClick={onOpenCompareDrawer} className="action-button">
                        查看完整对比
                      </Button>
                      <Button loading={aiCompareLoading} onClick={onAICompare} className="action-button">
                        AI 生成分析
                      </Button>
                    </div>
                  </>
                )}
              </div>
            ),
          },
        ]}
        className="workspace-tabs"
      />

      <style jsx>{`
        .workspace-shell {
          height: 100%;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .workspace-head {
          padding: 2px 2px 0;
        }

        :global(.workspace-tabs .ant-tabs-nav) {
          margin-bottom: 12px;
        }

        :global(.workspace-tabs .ant-tabs-content-holder) {
          min-height: 0;
        }

        :global(.workspace-tabs .ant-tabs-tab) {
          padding: 8px 0;
        }

        .tab-label {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .compare-tab {
          display: grid;
          gap: 12px;
        }

        .compare-empty {
          padding: 28px 16px;
          border-radius: 18px;
          border: 1px solid #e5ebf3;
          background: #ffffff;
        }

        .compare-preview {
          display: grid;
          gap: 12px;
        }

        .preview-card {
          display: grid;
          gap: 8px;
          padding: 16px;
          border-radius: 18px;
          border: 1px solid #e5ebf3;
          background: #ffffff;
        }

        .preview-top,
        .compare-actions {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
          align-items: center;
        }

        .preview-tags {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .action-button {
          height: 40px;
          border-radius: 12px;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
