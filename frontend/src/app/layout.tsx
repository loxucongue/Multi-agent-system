import type { Metadata } from "next";
import "antd/dist/reset.css";
import "./globals.css";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "凯撒旅游智能顾问",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
