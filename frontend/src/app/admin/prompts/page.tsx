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
      const active = await authedFetch<PromptVersion[]>("/admin/prompts");
      const names = Array.from(new Set(active.map((item) => item.node_name))).sort();
      setNodeNames(names);
      if (!selectedNode && names.length > 0) {
        setSelectedNode(names[0]);
      }
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
    } catch (error) {
      handleAuthError(error);
      setVersions([]);
    } finally {
      setLoadingVersions(false);
    }
  };

  useEffect(() => {
    void loadNodes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedNode) {
      void loadVersions(selectedNode);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode]);

  const columns: ColumnsType<PromptVersion> = useMemo(
    () => [
      { title: "版本", dataIndex: "version", key: "version", width: 90 },
      {
        title: "状态",
        dataIndex: "is_active",
        key: "is_active",
        width: 120,
        render: (active: boolean) => (active ? <Tag color="green">active</Tag> : <Tag>inactive</Tag>),
      },
      {
        title: "内容预览",
        dataIndex: "content",
        key: "content",
        ellipsis: true,
        render: (value: string) => <Text>{value.slice(0, 80)}</Text>,
      },
      {
        title: "创建时间",
        dataIndex: "created_at",
        key: "created_at",
        width: 190,
        render: (value: string) => new Date(value).toLocaleString("zh-CN"),
      },
      {
        title: "操作",
        key: "actions",
        width: 130,
        render: (_, row) => (
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
        ),
      },
    ],
    [authedFetch, message],
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 12, minHeight: "calc(100vh - 120px)" }}>
      <Card
        title="节点列表"
        loading={loadingNodes}
        extra={
          <Button
            size="small"
            onClick={() => {
              void loadNodes();
            }}
          >
            刷新
          </Button>
        }
      >
        <List
          dataSource={nodeNames}
          locale={{ emptyText: "暂无节点" }}
          renderItem={(name) => (
            <List.Item style={{ paddingInline: 0 }}>
              <Button
                type={selectedNode === name ? "primary" : "default"}
                block
                onClick={() => {
                  setSelectedNode(name);
                }}
              >
                {name}
              </Button>
            </List.Item>
          )}
        />
      </Card>

      <Card
        title={selectedNode ? `版本列表 · ${selectedNode}` : "版本列表"}
        extra={
          <Space>
            <Button
              disabled={!selectedNode}
              onClick={() => {
                if (selectedNode) {
                  void loadVersions(selectedNode);
                }
              }}
            >
              刷新
            </Button>
            <Button
              type="primary"
              disabled={!selectedNode}
              onClick={() => {
                setCreateOpen(true);
              }}
            >
              新建版本
            </Button>
          </Space>
        }
      >
        <Table
          rowKey={(row) => `${row.node_name}-${row.version}`}
          columns={columns}
          dataSource={versions}
          loading={loadingVersions}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 900 }}
        />
      </Card>

      <Modal
        title={`新建版本${selectedNode ? ` · ${selectedNode}` : ""}`}
        open={createOpen}
        onCancel={() => {
          if (!submitting) {
            setCreateOpen(false);
            setNewContent("");
          }
        }}
        onOk={() => {
          if (!selectedNode || !newContent.trim()) {
            message.warning("请输入内容");
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
        destroyOnClose
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
