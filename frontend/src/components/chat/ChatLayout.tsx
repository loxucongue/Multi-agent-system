"use client";

import { CompassOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Layout } from "antd";
import type { ReactNode } from "react";

import SessionList from "@/components/chat/SessionList";

const { Header, Sider, Content } = Layout;

interface ChatLayoutProps {
  children: ReactNode;
}

export default function ChatLayout({ children }: ChatLayoutProps) {
  return (
    <Layout
      className="chat-shell"
      style={{
        height: "100dvh",
        minHeight: "100dvh",
        background: "#f7f8fa",
      }}
    >
      <Header
        className="chat-header"
        style={{
          height: 64,
          lineHeight: "64px",
          padding: "0 20px",
          background: "#ffffff",
          borderBottom: "1px solid #e9edf3",
          boxShadow: "0 1px 0 rgba(15, 23, 42, 0.03)",
        }}
      >
        <div className="brand">
          <div className="brand-mark">
            <CompassOutlined />
          </div>

          <div className="brand-copy">
            <div className="brand-title">凯撒旅游智能顾问</div>
          </div>
        </div>

        <Button className="login-button" shape="round" icon={<UserOutlined />}>
          登录 / 注册
        </Button>
      </Header>

      <Layout
        className="chat-main"
        style={{
          flex: 1,
          minHeight: 0,
          height: "calc(100dvh - 64px)",
          background: "#f7f8fa",
        }}
      >
        <Sider
          width={260}
          breakpoint="lg"
          collapsedWidth={0}
          trigger={null}
          className="history-sider"
          style={{
            background: "#f7f8fa",
            borderRight: "1px solid #e9edf3",
          }}
        >
          <SessionList />
        </Sider>

        <Content
          className="chat-content"
          style={{
            display: "flex",
            minHeight: 0,
            minWidth: 0,
            overflow: "hidden",
            background: "#f7f8fa",
          }}
        >
          {children}
        </Content>
      </Layout>

      <style jsx>{`
        .chat-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          position: relative;
          z-index: 2;
        }

        .brand {
          display: flex;
          align-items: center;
          gap: 12px;
          min-width: 0;
        }

        .brand-mark {
          width: 42px;
          height: 42px;
          border-radius: 14px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, #2563eb, #3b82f6);
          color: #fff;
          font-size: 20px;
          box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
        }

        .brand-copy {
          min-width: 0;
        }

        .brand-title {
          font-size: 18px;
          line-height: 1.1;
          font-weight: 700;
          color: #0f172a;
        }

        .login-button {
          border-color: #d7deea;
          color: #4b5563;
          background: #ffffff;
        }

        .history-sider :global(.ant-layout-sider-children) {
          height: 100%;
          background: #f7f8fa;
        }

        @media (max-width: 991px) {
          .chat-header {
            padding: 0 14px !important;
          }

          .brand-title {
            font-size: 16px;
          }
        }
      `}</style>
    </Layout>
  );
}
