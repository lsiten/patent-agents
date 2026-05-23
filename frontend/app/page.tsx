'use client';

import Link from 'next/link';
import { BrainCircuit, MessageSquare, FileText, Sparkles, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/Button';

export default function Home() {
  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col">
      {/* Hero Section */}
      <section className="flex-1 flex items-center justify-center px-6 py-20">
        <div className="max-w-3xl mx-auto text-center space-y-8">
          <div className="flex justify-center">
            <div className="w-20 h-20 rounded-2xl bg-brand-green/10 flex items-center justify-center">
              <BrainCircuit className="w-10 h-10 text-brand-green-dark" />
            </div>
          </div>

          <h1 className="text-5xl sm:text-6xl font-bold text-ink tracking-tight">
            专利智脑
          </h1>

          <p className="text-xl text-slate max-w-2xl mx-auto leading-relaxed">
            AI 驱动的智能专利撰写助手。通过与 AI 专利代理人对话，快速完成技术方案梳理、
            现有技术检索、专利文件撰写与质量审查。
          </p>

          <div className="flex items-center justify-center gap-4 pt-4">
            <Link href="/chat">
              <Button size="lg" className="text-base px-8 py-3 shadow-lg">
                <MessageSquare className="w-5 h-5 mr-2" />
                开始对话
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
            <Link href="/patents">
              <Button variant="secondary" size="lg" className="text-base px-8 py-3">
                <FileText className="w-5 h-5 mr-2" />
                查看专利
              </Button>
            </Link>
          </div>

          {/* Feature highlights */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 pt-16 text-left">
            <div className="p-5 rounded-xl bg-surface border border-hairline space-y-2">
              <div className="w-10 h-10 rounded-lg bg-brand-green/10 flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-brand-green-dark" />
              </div>
              <h3 className="font-semibold text-ink">对话式创作</h3>
              <p className="text-sm text-slate leading-relaxed">
                通过自然对话描述您的发明创造，AI 专利代理人引导您完善技术方案。
              </p>
            </div>
            <div className="p-5 rounded-xl bg-surface border border-hairline space-y-2">
              <div className="w-10 h-10 rounded-lg bg-brand-green/10 flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-brand-green-dark" />
              </div>
              <h3 className="font-semibold text-ink">多智能体协作</h3>
              <p className="text-sm text-slate leading-relaxed">
                需求分析、检索评估、专利撰写、质量审查，四个专业 Agent 协同工作。
              </p>
            </div>
            <div className="p-5 rounded-xl bg-surface border border-hairline space-y-2">
              <div className="w-10 h-10 rounded-lg bg-brand-green/10 flex items-center justify-center">
                <FileText className="w-5 h-5 text-brand-green-dark" />
              </div>
              <h3 className="font-semibold text-ink">专业级输出</h3>
              <p className="text-sm text-slate leading-relaxed">
                自动生成符合专利法要求的权利要求书、说明书及摘要等完整申请文件。
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
