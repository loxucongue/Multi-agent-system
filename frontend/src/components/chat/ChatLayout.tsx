"use client";

import type { ReactNode } from "react";
import { Button, Layout, Space, Typography } from "antd";
import { UserOutlined } from "@ant-design/icons";

import SessionList from "@/components/chat/SessionList";

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

interface ChatLayoutProps {
  children: ReactNode;
}

export default function ChatLayout({ children }: ChatLayoutProps) {
  return (
    <Layout style={{ height: "100vh", background: "#f3f5f8" }}>
      <Header
        style={{
          height: 64,
          lineHeight: "64px",
          background: "#ffffff",
          borderBottom: "1px solid #e5e8ef",
          padding: "0 20px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Space size={10} align="center">
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: "#1f5eff",
              color: "#fff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
            }}
          >
            K
          </div>
          <Text style={{ fontSize: 28, fontWeight: 700, color: "#1f5eff", lineHeight: 1.1 }}>凯撒旅游</Text>
        </Space>

        <Space size={18} align="center">
          <Text type="secondary" style={{ cursor: "pointer" }}>
            企业版
          </Text>
          <Text type="secondary" style={{ cursor: "pointer" }}>
            关于我们
          </Text>
          <Button shape="round" icon={<UserOutlined />}>
            登录 / 注册
          </Button>
        </Space>
      </Header>

      <Layout style={{ minHeight: 0, background: "#f3f5f8" }}>
        <Sider
          width={256}
          collapsible
          breakpoint="md"
          collapsedWidth={0}
          trigger={null}
          style={{
            background: "#f5f7fb",
            borderRight: "1px solid #e5e8ef",
            overflow: "hidden",
          }}
        >
          <SessionList />
        </Sider>
        <Content style={{ padding: 12, overflow: "hidden" }}>{children}</Content>
      </Layout>
    </Layout>
  );
}
