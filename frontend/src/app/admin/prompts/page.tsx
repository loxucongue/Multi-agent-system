"use client";

import { App, Button, Card, Input, List, Modal, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";

const { TextArea } = Input;
const { Text } = Typography;

interface PromptVersion {
  node_name: string;
  version: number;
  content: string;
  is_active: boolean;
  created_at: string;
}

const NODE_DESCRIPTIONS: Record<string, string> = {
  intent_classification: "意图分类：识别推荐/追问/签证/价格/对比等意图。",
  requirement_collection: "需求收集：补齐目的地、天数、预算等槽位。",
  response_generation: "回复生成：基于工具结果产出最终回复文本。",
  chitchat: "闲聊处理：礼貌回复并引导回旅游咨询。",
  compare_style: "对比风格：推断行程节奏（紧凑/轻松/自由）。",
  kb_query_gen: "检索词生成：为路线知识库生成高质量 query。",
  kb_result_eval: "路线评估：判断路线检索结果是否相关。",
  visa_result_eval: "签证评估：判断签证检索结果是否相关。",
  route_select: "候选筛选：从候选线路中语义筛选最匹配的 1~3 条。",
};

const getNodeDescription = (nodeName: string): string =>
  NODE_DESCRIPTIONS[nodeName] ?? "该节点用于特定 LLM 任务，请结合业务链路查看。";

export default function AdminPromptsPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, logout } = useAdminStore(
    useShallow((state) => ({
      authedFetch: state.authedFetch,
      logout: state.logout,
    })),
  );

  const [loadingNodes, setLoadingNodes] = useState(false);
  const [nodeNames, setNodeNames] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [previewVersion, setPreviewVersion] = useState<PromptVersion | null>(null);
  const [loadingVersions, setLoadingVersions] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleAuthError = (error: unknown) => {
    const text = error instanceof Error ? error.message : "请求失败";
    if (text.includes("登录已过期")) {
      logout();
      router.replace("/admin/login");
      return;
    }
    message.error(text);
  };

  const loadNodes = async () => {
    setLoadingNodes(true);
    try {
      let names: string[] = [];
      try {
        names = await authedFetch<string[]>("/admin/prompts/nodes");
      } catch {
        const active = await authedFetch<PromptVersion[]>("/admin/prompts");
        names = Array.from(new Set(active.map((item) => item.node_name))).sort();
      }
      setNodeNames(names);
      if (selectedNode && names.includes(selectedNode)) {
        return;
      }
      setSelectedNode(names[0] ?? null);
    } catch (error) {
      handleAuthError(error);
    } finally {
      setLoadingNodes(false);
    }
  };

  const loadVersions = async (nodeName: string) => {
    setLoadingVersions(true);
    try {
      const rows = await authedFetch<PromptVersion[]>(`/admin/prompts/${encodeURIComponent(nodeName)}`);
      setVersions(rows);
      const active = rows.find((item) => item.is_active) ?? null;
      setPreviewVersion(active ?? rows[0] ?? null);
    } catch (error) {
      handleAuthError(error);
      setVersions([]);
      setPreviewVersion(null);
    } finally {
      setLoadingVersions(false);
    }
  };

  useEffect(() => {
    void loadNodes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedNode) {
      setVersions([]);
      setPreviewVersion(null);
      return;
    }
    void loadVersions(selectedNode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode]);

  const columns: ColumnsType<PromptVersion> = useMemo(
    () => [
      {
        title: "版本",
        dataIndex: "version",
        key: "version",
        width: 90,
      },
      {
        title: "状态",
        dataIndex: "is_active",
        key: "is_active",
        width: 110,
        render: (active: boolean) => (active ? <Tag color="green">active</Tag> : <Tag>inactive</Tag>),
      },
      {
        title: "内容预览",
        dataIndex: "content",
        key: "content",
        ellipsis: true,
        render: (value: string) => <Text>{value.slice(0, 120)}</Text>,
      },
      {
        title: "创建时间",
        dataIndex: "created_at",
        key: "created_at",
        width: 200,
        render: (value: string) => new Date(value).toLocaleString("zh-CN"),
      },
      {
        title: "操作",
        key: "actions",
        width: 180,
        render: (_, row) => (
          <Space>
            <Button size="small" onClick={() => setPreviewVersion(row)}>
              预览
            </Button>
            <Button
              size="small"
              type="primary"
              ghost
              disabled={row.is_active}
              onClick={() => {
                void (async () => {
                  try {
                    await authedFetch(`/admin/prompts/${encodeURIComponent(row.node_name)}/${row.version}/activate`, {
                      method: "PUT",
                    });
                    message.success("版本已激活");
                    await loadVersions(row.node_name);
                    await loadNodes();
                  } catch (error) {
                    handleAuthError(error);
                  }
                })();
              }}
            >
              激活
            </Button>
          </Space>
        ),
      },
    ],
    [authedFetch, message],
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 12, minHeight: "calc(100vh - 120px)" }}>
      <Card
        title="节点列表"
        loading={loadingNodes}
        extra={
          <Button size="small" onClick={() => void loadNodes()}>
            刷新
          </Button>
        }
      >
        <List
          dataSource={nodeNames}
          locale={{ emptyText: "暂无节点" }}
          renderItem={(name) => {
            const active = selectedNode === name;
            return (
              <List.Item style={{ paddingInline: 0 }}>
                <Button
                  type={active ? "primary" : "default"}
                  block
                  onClick={() => setSelectedNode(name)}
                  style={{ height: "auto", textAlign: "left", paddingBlock: 10 }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
                    <span style={{ fontWeight: 600 }}>{name}</span>
                    <span style={{ fontSize: 12, opacity: active ? 0.9 : 0.75, whiteSpace: "normal", lineHeight: 1.35 }}>
                      {getNodeDescription(name)}
                    </span>
                  </div>
                </Button>
              </List.Item>
            );
          }}
        />
      </Card>

      <Card
        title={selectedNode ? `版本列表 · ${selectedNode}` : "版本列表"}
        extra={
          <Space>
            <Button
              disabled={!versions.length}
              onClick={() => {
                const active = versions.find((item) => item.is_active) ?? null;
                setPreviewVersion(active ?? versions[0] ?? null);
              }}
            >
              预览当前激活
            </Button>
            <Button disabled={!selectedNode} onClick={() => selectedNode && void loadVersions(selectedNode)}>
              刷新
            </Button>
            <Button type="primary" disabled={!selectedNode} onClick={() => setCreateOpen(true)}>
              新建版本
            </Button>
          </Space>
        }
      >
        {selectedNode ? (
          <Card size="small" style={{ marginBottom: 12 }}>
            <Text strong>节点作用：</Text>
            <Text style={{ marginLeft: 8 }}>{getNodeDescription(selectedNode)}</Text>
          </Card>
        ) : null}

        <Table
          rowKey={(row) => `${row.node_name}-${row.version}`}
          columns={columns}
          dataSource={versions}
          loading={loadingVersions}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 900 }}
          onRow={(record) => ({
            onClick: () => setPreviewVersion(record),
          })}
        />

        <Card
          size="small"
          style={{ marginTop: 12 }}
          title={
            previewVersion
              ? `提示词预览 · v${previewVersion.version}${previewVersion.is_active ? "（active）" : ""}`
              : "提示词预览"
          }
        >
          {previewVersion ? (
            <TextArea readOnly value={previewVersion.content} autoSize={{ minRows: 12, maxRows: 24 }} />
          ) : (
            <Text type="secondary">当前节点暂无可预览内容</Text>
          )}
        </Card>
      </Card>

      <Modal
        title={selectedNode ? `新建版本 · ${selectedNode}` : "新建版本"}
        open={createOpen}
        onCancel={() => {
          if (!submitting) {
            setCreateOpen(false);
            setNewContent("");
          }
        }}
        onOk={() => {
          if (!selectedNode || !newContent.trim()) {
            message.warning("请输入 Prompt 内容");
            return;
          }
          void (async () => {
            setSubmitting(true);
            try {
              await authedFetch(`/admin/prompts/${encodeURIComponent(selectedNode)}`, {
                method: "POST",
                body: JSON.stringify({ content: newContent }),
              });
              message.success("新版本已创建");
              setCreateOpen(false);
              setNewContent("");
              await loadVersions(selectedNode);
              await loadNodes();
            } catch (error) {
              handleAuthError(error);
            } finally {
              setSubmitting(false);
            }
          })();
        }}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <TextArea
          value={newContent}
          onChange={(event) => setNewContent(event.target.value)}
          rows={10}
          placeholder="请输入 Prompt 内容"
        />
      </Modal>
    </div>
  );
}

