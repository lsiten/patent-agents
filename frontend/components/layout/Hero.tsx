'use client';

import { ArrowRight, Sparkles, Shield, Zap, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import Link from 'next/link';

const features = [
  {
    icon: Sparkles,
    title: '智能需求分析',
    description: '深度理解技术描述，提取关键创新点，自动识别专利类型建议',
  },
  {
    icon: Shield,
    title: '专利性评估',
    description: '智能检索现有技术，评估新颖性、创造性、实用性，降低驳回风险',
  },
  {
    icon: Zap,
    title: '专业文件生成',
    description: '自动生成权利要求书、说明书全套文档，符合专利局规范要求',
  },
  {
    icon: CheckCircle2,
    title: '质量审查',
    description: '多维度合规性校验，预判审查意见，确保申请文件质量',
  },
];

export function Hero() {
  return (
    <>
      {/* Hero Band */}
      <section className="bg-brand-teal-deep text-on-dark py-hero">
        <div className="container mx-auto px-md">
          <div className="max-w-4xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-body-sm mb-lg">
              <Sparkles className="w-4 h-4 text-brand-green" />
              <span>多智能体协同工作，让专利申请更简单</span>
            </div>
            <h1 className="text-hero-display font-euclid font-medium leading-[1.1] tracking-tighter mb-lg">
              专利申请
              <span className="text-brand-green">智能助手</span>
            </h1>
            <p className="text-subtitle text-on-dark-muted max-w-2xl mx-auto mb-xl">
              CEO Agent 统筹全流程，4 个专业 Agent 协同工作，
              将技术发明转化为专业、合规的专利申请文件
            </p>
            <div className="flex flex-col sm:flex-row gap-md justify-center">
              <Link href="/submit">
                <Button size="lg" className="w-full sm:w-auto">
                  开始专利申请
                  <ArrowRight className="ml-2 w-5 h-5" />
                </Button>
              </Link>
              <Button variant="secondary-on-dark" size="lg">
                查看演示案例
              </Button>
            </div>
          </div>

          {/* Stats */}
          <div className="max-w-4xl mx-auto mt-xxl grid grid-cols-2 md:grid-cols-4 gap-lg">
            {[
              { value: '4+', label: '专业 Agent' },
              { value: '98%', label: '文档合规率' },
              { value: '50%', label: '效率提升' },
              { value: '1000+', label: '专利申请' },
            ].map((stat) => (
              <div key={stat.label} className="text-center p-lg rounded-xl bg-white/5">
                <div className="text-display-lg font-euclid font-medium text-brand-green mb-xs">
                  {stat.value}
                </div>
                <div className="text-body-sm text-on-dark-muted">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-section-lg bg-canvas">
        <div className="container mx-auto px-md">
          <div className="max-w-3xl mx-auto text-center mb-xxl">
            <h2 className="text-heading-2 font-euclid font-medium text-ink mb-md">
              多智能体协同工作
            </h2>
            <p className="text-subtitle text-steel">
              从技术描述到专利文件，全流程 AI 驱动，专业且高效
            </p>
          </div>

          <div className="max-w-5xl mx-auto grid md:grid-cols-2 gap-xl">
            {features.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <div
                  key={index}
                  className="p-xxl rounded-xl border border-hairline bg-canvas hover:shadow-card transition-all duration-300"
                >
                  <div className="w-12 h-12 rounded-lg bg-surface-feature flex items-center justify-center mb-lg">
                    <Icon className="w-6 h-6 text-brand-green-dark" />
                  </div>
                  <h3 className="text-heading-4 font-euclid font-medium text-ink mb-md">
                    {feature.title}
                  </h3>
                  <p className="text-body-md text-steel">
                    {feature.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-section-lg bg-surface">
        <div className="container mx-auto px-md">
          <div className="max-w-3xl mx-auto text-center mb-xxl">
            <h2 className="text-heading-2 font-euclid font-medium text-ink mb-md">
              工作流程
            </h2>
            <p className="text-subtitle text-steel">
              简单三步，完成专利申请全流程
            </p>
          </div>

          <div className="max-w-5xl mx-auto">
            <div className="relative">
              {/* Connection Line */}
              <div className="absolute top-16 left-0 right-0 h-0.5 bg-hairline hidden md:block" />

              <div className="grid md:grid-cols-4 gap-xl">
                {[
                  {
                    step: '01',
                    title: '提交技术描述',
                    description: '描述您的发明创新点、技术方案和应用场景',
                  },
                  {
                    step: '02',
                    title: '智能分析检索',
                    description: '需求分析 Agent 结构化处理，检索 Agent 评估专利性',
                  },
                  {
                    step: '03',
                    title: '生成申请文件',
                    description: '撰写 Agent 生成全套专利申请文件',
                  },
                  {
                    step: '04',
                    title: '质量审查交付',
                    description: '审查 Agent 完成合规校验，交付最终成果',
                  },
                ].map((item, index) => (
                  <div key={index} className="relative">
                    <div className="relative z-10 w-12 h-12 rounded-full bg-brand-green text-ink font-euclid font-semibold flex items-center justify-center mb-md mx-auto">
                      {item.step}
                    </div>
                    <div className="text-center">
                      <h3 className="text-heading-5 font-euclid font-medium text-ink mb-md">
                        {item.title}
                      </h3>
                      <p className="text-body-sm text-steel">
                        {item.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
