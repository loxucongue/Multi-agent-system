"use client";

import {
  App,
  Button,
  Card,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Upload,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { UploadProps } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useAdminStore } from "@/stores/adminStore";

interface DatasetItem {
  dataset_id: string;
  name?: string;
  status?: number;
  doc_count?: number;
}

interface DocumentItem {
  document_id: string;
  status?: number;
  slice_count?: number;
  name?: string;
}

interface DocumentListResponse {
  document_infos: DocumentItem[];
  total: number;
}

interface ProgressItem {
  document_id?: string;
  status?: number;
  progress?: number;
  status_descript?: string;
}

const statusText = (status?: number): string => {
  if (status === 1) {
    return "完成";
  }
  if (status === 0) {
    return "处理中";
  }
  if (status === 9) {
    return "失败";
  }
  return "-";
};

const toBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result ?? "");
      const payload = value.includes(",") ? value.split(",")[1] : value;
      resolve(payload);
    };
    reader.onerror = () => reject(new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });

export default function AdminKbPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, logout } = useAdminStore((state) => ({
    authedFetch: state.authedFetch,
    logout: state.logout,
  }));

  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState("");
  const [creatingDataset, setCreatingDataset] = useState(false);

  const [selectedDatasetId, setSelectedDatasetId] = useState<string | undefined>(undefined);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [deletingDocIds, setDeletingDocIds] = useState<string[]>([]);
  const [pollingProgress, setPollingProgress] = useState<Record<string, ProgressItem>>({});

  const handleAuthError = (error: unknown) => {
    const text = error instanceof Error ? error.message : "请求失败";
    if (text.includes("登录已过期")) {
      logout();
      router.replace("/admin/login");
      return;
    }
    message.error(text);
  };

  const loadDatasets = async () => {
    setLoadingDatasets(true);
    try {
      const rows = await authedFetch<DatasetItem[]>("/admin/kb/datasets");
      setDatasets(rows);
      if (!selectedDatasetId && rows.length > 0) {
        setSelectedDatasetId(rows[0].dataset_id);
      }
    } catch (error) {
      handleAuthError(error);
    } finally {
      setLoadingDatasets(false);
    }
  };

  const loadDocuments = async (datasetId: string) => {
    setLoadingDocuments(true);
    try {
      const result = await authedFetch<DocumentListResponse>(
        `/admin/kb/datasets/${datasetId}/documents?page=1&size=50`,
      );
      setDocuments(result.document_infos ?? []);
    } catch (error) {
      handleAuthError(error);
      setDocuments([]);
    } finally {
      setLoadingDocuments(false);
    }
  };

  useEffect(() => {
    void loadDatasets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedDatasetId) {
      void loadDocuments(selectedDatasetId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDatasetId]);

  const datasetColumns: ColumnsType<DatasetItem> = useMemo(
    () => [
      { title: "dataset_id", dataIndex: "dataset_id", key: "dataset_id", width: 260 },
      { title: "名称", dataIndex: "name", key: "name" },
      { title: "文档数", dataIndex: "doc_count", key: "doc_count", width: 100 },
      { title: "状态", dataIndex: "status", key: "status", width: 120, render: (v) => statusText(v) },
      {
        title: "操作",
        key: "actions",
        width: 120,
        render: (_, row) => (
          <Popconfirm
            title="确认删除该知识库？"
            onConfirm={() => {
              void (async () => {
                try {
                  await authedFetch(`/admin/kb/datasets/${row.dataset_id}`, { method: "DELETE" });
                  message.success("已删除");
                  if (selectedDatasetId === row.dataset_id) {
                    setSelectedDatasetId(undefined);
                  }
                  await loadDatasets();
                } catch (error) {
                  handleAuthError(error);
                }
              })();
            }}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        ),
      },
    ],
    [authedFetch, message, selectedDatasetId],
  );

  const documentColumns: ColumnsType<DocumentItem> = useMemo(
    () => [
      { title: "document_id", dataIndex: "document_id", key: "document_id", width: 260 },
      { title: "名称", dataIndex: "name", key: "name" },
      { title: "分片数", dataIndex: "slice_count", key: "slice_count", width: 90 },
      { title: "状态", dataIndex: "status", key: "status", width: 100, render: (v) => statusText(v) },
      {
        title: "进度",
        key: "progress",
        width: 180,
        render: (_, row) => {
          const progress = pollingProgress[row.document_id];
          if (!progress) {
            return "-";
          }
          return (
            <Progress
              percent={Math.min(100, Math.max(0, progress.progress ?? 0))}
              size="small"
              status={progress.status === 9 ? "exception" : progress.status === 1 ? "success" : "active"}
            />
          );
        },
      },
      {
        title: "操作",
        key: "actions",
        width: 120,
        render: (_, row) => (
          <Popconfirm
            title="确认删除该文档？"
            onConfirm={() => {
              void (async () => {
                setDeletingDocIds((prev) => [...prev, row.document_id]);
                try {
                  await authedFetch("/admin/kb/documents", {
                    method: "DELETE",
                    body: JSON.stringify({ document_ids: [row.document_id] }),
                  });
                  message.success("文档已删除");
                  if (selectedDatasetId) {
                    await loadDocuments(selectedDatasetId);
                  }
                } catch (error) {
                  handleAuthError(error);
                } finally {
                  setDeletingDocIds((prev) => prev.filter((id) => id !== row.document_id));
                }
              })();
            }}
          >
            <Button size="small" danger loading={deletingDocIds.includes(row.document_id)}>
              删除
            </Button>
          </Popconfirm>
        ),
      },
    ],
    [authedFetch, deletingDocIds, message, pollingProgress, selectedDatasetId],
  );

  const uploadProps: UploadProps = {
    multiple: false,
    showUploadList: false,
    customRequest: async ({ file, onError, onSuccess }) => {
      if (!selectedDatasetId) {
        message.warning("请先选择知识库");
        onError?.(new Error("missing dataset"));
        return;
      }

      try {
        const f = file as File;
        const base64 = await toBase64(f);
        const ext = f.name.split(".").pop()?.toLowerCase() ?? "pdf";

        const created = await authedFetch<DocumentItem[]>(
          `/admin/kb/datasets/${selectedDatasetId}/documents`,
          {
            method: "POST",
            body: JSON.stringify({
              document_bases: [
                {
                  name: f.name,
                  source_info: {
                    file_base64: base64,
                    file_type: ext,
                    document_source: 0,
                  },
                },
              ],
              chunk_strategy: {
                chunk_type: 0,
              },
              format_type: 0,
            }),
          },
        );

        const documentIds = (created ?? []).map((item) => item.document_id).filter(Boolean);
        if (documentIds.length > 0) {
          const timer = window.setInterval(async () => {
            try {
              const progress = await authedFetch<ProgressItem[]>(
                `/admin/kb/datasets/${selectedDatasetId}/progress`,
                {
                  method: "POST",
                  body: JSON.stringify({ document_ids: documentIds }),
                },
              );

              setPollingProgress((prev) => {
                const next = { ...prev };
                progress.forEach((item) => {
                  if (item.document_id) {
                    next[item.document_id] = item;
                  }
                });
                return next;
              });

              const allDone = progress.every((item) => item.status === 1 || item.status === 9);
              if (allDone) {
                window.clearInterval(timer);
                if (selectedDatasetId) {
                  await loadDocuments(selectedDatasetId);
                }
              }
            } catch {
              window.clearInterval(timer);
            }
          }, 2000);
        }

        message.success("上传成功，正在处理文档");
        if (selectedDatasetId) {
          await loadDocuments(selectedDatasetId);
        }
        onSuccess?.({}, file);
      } catch (error) {
        handleAuthError(error);
        onError?.(new Error("upload failed"));
      }
    },
  };

  return (
    <>
      <Tabs
        defaultActiveKey="datasets"
        items={[
          {
            key: "datasets",
            label: "Datasets",
            children: (
              <Card
                title="知识库列表"
                extra={
                  <Space>
                    <Button onClick={() => void loadDatasets()}>刷新</Button>
                    <Button type="primary" onClick={() => setCreateOpen(true)}>
                      新建知识库
                    </Button>
                  </Space>
                }
              >
                <Table
                  rowKey={(row) => row.dataset_id}
                  loading={loadingDatasets}
                  columns={datasetColumns}
                  dataSource={datasets}
                  pagination={{ pageSize: 8 }}
                />
              </Card>
            ),
          },
          {
            key: "documents",
            label: "Documents",
            children: (
              <Card
                title="文档管理"
                extra={
                  <Space>
                    <Select
                      style={{ width: 280 }}
                      value={selectedDatasetId}
                      options={datasets.map((item) => ({
                        label: item.name ?? item.dataset_id,
                        value: item.dataset_id,
                      }))}
                      placeholder="选择知识库"
                      onChange={(value) => setSelectedDatasetId(value)}
                    />
                    <Upload {...uploadProps}>
                      <Button type="primary" disabled={!selectedDatasetId}>
                        上传文档
                      </Button>
                    </Upload>
                    <Button
                      onClick={() => selectedDatasetId && void loadDocuments(selectedDatasetId)}
                      disabled={!selectedDatasetId}
                    >
                      刷新
                    </Button>
                  </Space>
                }
              >
                <Table
                  rowKey={(row) => row.document_id}
                  loading={loadingDocuments}
                  columns={documentColumns}
                  dataSource={documents}
                  pagination={{ pageSize: 8 }}
                />
              </Card>
            ),
          },
        ]}
      />

      <Modal
        title="新建知识库"
        open={createOpen}
        onCancel={() => {
          if (!creatingDataset) {
            setCreateOpen(false);
            setNewDatasetName("");
          }
        }}
        onOk={() => {
          if (!newDatasetName.trim()) {
            message.warning("请输入名称");
            return;
          }
          void (async () => {
            setCreatingDataset(true);
            try {
              await authedFetch("/admin/kb/datasets", {
                method: "POST",
                body: JSON.stringify({
                  name: newDatasetName.trim(),
                  format_type: 0,
                  description: "",
                }),
              });
              message.success("知识库已创建");
              setCreateOpen(false);
              setNewDatasetName("");
              await loadDatasets();
            } catch (error) {
              handleAuthError(error);
            } finally {
              setCreatingDataset(false);
            }
          })();
        }}
        confirmLoading={creatingDataset}
      >
        <input
          style={{ width: "100%", border: "1px solid #d9d9d9", borderRadius: 8, padding: "8px 10px" }}
          placeholder="请输入知识库名称"
          value={newDatasetName}
          onChange={(event) => setNewDatasetName(event.target.value)}
        />
      </Modal>
    </>
  );
}
