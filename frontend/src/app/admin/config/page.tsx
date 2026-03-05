"use client";

import { App, Button, Card, Form, Input, Modal, Popconfirm, Space, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useAdminStore } from "@/stores/adminStore";

interface ConfigItem {
  key: string;
  value: string;
  description?: string | null;
  updated_at?: string;
}

interface ConfigForm {
  key: string;
  value: string;
  description?: string;
}

export default function AdminConfigPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const { authedFetch, logout } = useAdminStore((state) => ({
    authedFetch: state.authedFetch,
    logout: state.logout,
  }));

  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<ConfigItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ConfigItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<ConfigForm>();

  const handleAuthError = (error: unknown) => {
    const text = error instanceof Error ? error.message : "请求失败";
    if (text.includes("登录已过期")) {
      logout();
      router.replace("/admin/login");
      return;
    }
    message.error(text);
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const result = await authedFetch<ConfigItem[]>("/admin/config");
      setRows(result ?? []);
    } catch (error) {
      handleAuthError(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: ColumnsType<ConfigItem> = useMemo(
    () => [
      { title: "Key", dataIndex: "key", key: "key", width: 260 },
      { title: "Value", dataIndex: "value", key: "value", ellipsis: true },
      { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
      {
        title: "Updated At",
        dataIndex: "updated_at",
        key: "updated_at",
        width: 180,
        render: (value: string | undefined) => (value ? new Date(value).toLocaleString("zh-CN") : "-"),
      },
      {
        title: "操作",
        key: "actions",
        width: 170,
        render: (_, row) => (
          <Space>
            <Button
              size="small"
              onClick={() => {
                setEditing(row);
                form.setFieldsValue({
                  key: row.key,
                  value: row.value,
                  description: row.description ?? "",
                });
                setOpen(true);
              }}
            >
              编辑
            </Button>
            <Popconfirm
              title={`确认删除 ${row.key} ?`}
              onConfirm={() => {
                void (async () => {
                  try {
                    await authedFetch(`/admin/config/${encodeURIComponent(row.key)}`, { method: "DELETE" });
                    message.success("已删除");
                    await loadData();
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
          </Space>
        ),
      },
    ],
    [authedFetch, form, message],
  );

  return (
    <Card
      title="系统配置"
      extra={
        <Space>
          <Button onClick={() => void loadData()}>刷新</Button>
          <Button
            type="primary"
            onClick={() => {
              setEditing(null);
              form.resetFields();
              setOpen(true);
            }}
          >
            新增
          </Button>
        </Space>
      }
    >
      <Table
        rowKey={(row) => row.key}
        columns={columns}
        dataSource={rows}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editing ? `编辑配置 · ${editing.key}` : "新增配置"}
        open={open}
        onCancel={() => {
          if (!submitting) {
            setOpen(false);
            form.resetFields();
          }
        }}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            setSubmitting(true);
            try {
              await authedFetch(`/admin/config/${encodeURIComponent(values.key)}`, {
                method: "PUT",
                body: JSON.stringify({
                  value: values.value,
                  description: values.description ?? null,
                }),
              });
              message.success("保存成功");
              setOpen(false);
              form.resetFields();
              await loadData();
            } catch (error) {
              handleAuthError(error);
            } finally {
              setSubmitting(false);
            }
          });
        }}
        confirmLoading={submitting}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="Key"
            name="key"
            rules={[{ required: true, message: "请输入 key" }]}
          >
            <Input disabled={Boolean(editing)} placeholder="SESSION_CONTEXT_TURNS" />
          </Form.Item>
          <Form.Item
            label="Value"
            name="value"
            rules={[{ required: true, message: "请输入 value" }]}
          >
            <Input placeholder="8" />
          </Form.Item>
          <Form.Item label="Description" name="description">
            <Input placeholder="配置说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
