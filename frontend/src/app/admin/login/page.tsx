"use client";

import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { App, Button, Card, Form, Input, Typography } from "antd";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

import { useAdminStore } from "@/stores/adminStore";

const { Title, Text } = Typography;

interface LoginForm {
  username: string;
  password: string;
}

export default function AdminLoginPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);

  const { login, token } = useAdminStore(
    useShallow((state) => ({
      login: state.login,
      token: state.token,
    })),
  );

  useEffect(() => {
    if (token) {
      router.replace("/admin/prompts");
    }
  }, [router, token]);

  const handleSubmit = async (values: LoginForm) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success("登录成功");
      router.replace("/admin/prompts");
    } catch (error) {
      const text = error instanceof Error ? error.message : "登录失败";
      message.error(text);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background:
          "radial-gradient(circle at 20% 20%, rgba(22,119,255,0.16), transparent 45%), #f5f7fa",
        padding: 16,
      }}
    >
      <Card style={{ width: 380, borderRadius: 14 }}>
        <Title level={4} style={{ marginBottom: 6 }}>
          管理后台登录
        </Title>
        <Text type="secondary">请输入管理员账号和密码</Text>

        <Form<LoginForm>
          layout="vertical"
          style={{ marginTop: 20 }}
          onFinish={(values) => {
            void handleSubmit(values);
          }}
          initialValues={{ username: "", password: "" }}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input prefix={<UserOutlined />} placeholder="admin" />
          </Form.Item>

          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" />
          </Form.Item>

          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
