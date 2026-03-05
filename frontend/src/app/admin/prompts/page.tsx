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
    const text = error instanceof Error ? error.message : "璇锋眰澶辫触";
    if (text.includes("鐧诲綍宸茶繃鏈?)) {
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
      { title: "鐗堟湰", dataIndex: "version", key: "version", width: 90 },
      {
        title: "鐘舵€?,
        dataIndex: "is_active",
        key: "is_active",
        width: 120,
        render: (active: boolean) => (active ? <Tag color="green">active</Tag> : <Tag>inactive</Tag>),
      },
      {
        title: "鍐呭棰勮",
        dataIndex: "content",
        key: "content",
        ellipsis: true,
        render: (value: string) => <Text>{value.slice(0, 80)}</Text>,
      },
      {
        title: "鍒涘缓鏃堕棿",
        dataIndex: "created_at",
        key: "created_at",
        width: 190,
        render: (value: string) => new Date(value).toLocaleString("zh-CN"),
      },
      {
        title: "鎿嶄綔",
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
                  message.success("鐗堟湰宸叉縺娲?);
                  await loadVersions(row.node_name);
                  await loadNodes();
                } catch (error) {
                  handleAuthError(error);
                }
              })();
            }}
          >
            婵€娲?          </Button>
        ),
      },
    ],
    [authedFetch, message],
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 12, minHeight: "calc(100vh - 120px)" }}>
      <Card
        title="鑺傜偣鍒楄〃"
        loading={loadingNodes}
        extra={
          <Button
            size="small"
            onClick={() => {
              void loadNodes();
            }}
          >
            鍒锋柊
          </Button>
        }
      >
        <List
          dataSource={nodeNames}
          locale={{ emptyText: "鏆傛棤鑺傜偣" }}
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
        title={selectedNode ? `鐗堟湰鍒楄〃 路 ${selectedNode}` : "鐗堟湰鍒楄〃"}
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
              鍒锋柊
            </Button>
            <Button
              type="primary"
              disabled={!selectedNode}
              onClick={() => {
                setCreateOpen(true);
              }}
            >
              鏂板缓鐗堟湰
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
        title={`鏂板缓鐗堟湰${selectedNode ? ` 路 ${selectedNode}` : ""}`}
        open={createOpen}
        onCancel={() => {
          if (!submitting) {
            setCreateOpen(false);
            setNewContent("");
          }
        }}
        onOk={() => {
          if (!selectedNode || !newContent.trim()) {
            message.warning("璇疯緭鍏ュ唴瀹?);
            return;
          }
          void (async () => {
            setSubmitting(true);
            try {
              await authedFetch(`/admin/prompts/${encodeURIComponent(selectedNode)}`, {
                method: "POST",
                body: JSON.stringify({ content: newContent }),
              });
              message.success("鏂扮増鏈凡鍒涘缓");
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
          placeholder="璇疯緭鍏?Prompt 鍐呭"
        />
      </Modal>
    </div>
  );
}

