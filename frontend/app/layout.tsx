import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import '../styles/animations.css';
import { Navbar } from '@/components/layout/Navbar';
import { ToastProvider } from '@/components/ui/Toast';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: '专利智脑 - AI 驱动的专利申请多智能体系统',
  description: 'CEO Agent 统筹全流程，多智能体协同工作，将技术发明转化为专业、合规的专利申请文件',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <ToastProvider>
          <div className="flex h-dvh min-h-0 flex-col overflow-hidden">
            <Navbar />
            <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
          </div>
        </ToastProvider>
      </body>
    </html>
  );
}
