import type { Metadata } from "next";
import { Fira_Code, Noto_Sans_SC } from "next/font/google";
import "antd/dist/reset.css";
import "./globals.css";
import Providers from "./providers";

const notoSansSc = Noto_Sans_SC({
  variable: "--font-ui",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const firaCode = Fira_Code({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "凯撒旅游顾问",
  description: "凯撒旅游智能顾问，帮助用户对话式规划路线、比较方案并查看行程细节。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={`${notoSansSc.variable} ${firaCode.variable} antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
