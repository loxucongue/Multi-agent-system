"use client";

import type { ReactNode } from "react";
import { Layout } from "antd";

const { Sider, Content } = Layout;

interface ChatLayoutProps {
  children: ReactNode;
}

export default function ChatLayout({ children }: ChatLayoutProps) {
  return (
    <Layout style={{ height: "100vh" }}>
      <Sider width={240} collapsible breakpoint="md" collapsedWidth={0}>
        <div style={{ color: "#fff", padding: 16 }}>会话列表</div>
      </Sider>
      <Content style={{ padding: 16, overflow: "auto" }}>{children}</Content>
    </Layout>
  );
}
