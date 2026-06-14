'use client';

import Link from 'next/link';
import { 
  BrainCircuit, 
  MessageSquare, 
  FileText, 
  Sparkles, 
  ArrowRight, 
  Shield, 
  Zap, 
  Users, 
  TrendingUp,
  Search,
  PenTool,
  CheckCircle2,
  Building2,
  Lightbulb,
  Target,
  ChevronRight,
  Server,
  Code2,
  Globe
} from 'lucide-react';
import { Button } from '@/components/ui/Button';

export default function Home() {
  return (
    <div className="min-h-screen bg-canvas">
      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-to-b from-brand-teal-deep via-brand-teal to-brand-teal text-white min-h-screen flex items-center">
        {/* Grid Background */}
        <div className="absolute inset-0 grid-bg-dark"></div>

        {/* Particle Effects */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          {[...Array(60)].map((_, i) => (
            <div
              key={i}
              className="particle"
              style={{
                left: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 12}s`,
                animationDuration: `${8 + Math.random() * 6}s`,
                width: `${3 + Math.random() * 4}px`,
                height: `${3 + Math.random() * 4}px`,
                opacity: `${0.4 + Math.random() * 0.6}`,
              }}
            />
          ))}
        </div>

        {/* Glow Orbs */}
        <div className="absolute inset-0">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-cyan/15 rounded-full blur-3xl animate-pulse"></div>
          <div
            className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-accent-purple/15 rounded-full blur-3xl animate-pulse"
            style={{ animationDelay: '1s' }}
          ></div>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand-cyan/10 rounded-full blur-3xl"></div>
        </div>

        {/* Scan Line */}
        <div className="absolute inset-0 scan-line pointer-events-none"></div>

        <div className="relative max-w-7xl mx-auto px-6 py-24 lg:py-32 w-full">
          <div className="text-center space-y-8">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 animate-slideUp">
              <Sparkles className="w-4 h-4 text-brand-cyan animate-glowPulse" />
              <span className="text-sm font-medium">新一代 AI 专利撰写平台</span>
            </div>

            {/* Main Heading */}
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight max-w-4xl mx-auto animate-slideUp" style={{ animationDelay: '0.1s' }}>
              让 AI 成为您的
              <span className="block mt-2 text-tech-gradient neon-glow">专利撰写专家</span>
            </h1>

            {/* Subtitle */}
            <p className="text-lg sm:text-xl text-white/80 max-w-2xl mx-auto leading-relaxed animate-slideUp" style={{ animationDelay: '0.2s' }}>
              基于多智能体协作架构，将技术创新转化为专业、合规的专利申请文件。 缩短撰写周期 70%，提升授权率 40%。
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4 animate-slideUp" style={{ animationDelay: '0.3s' }}>
              <Link href="/chat">
                <Button size="lg" className="text-base px-8 py-4 shadow-xl hover:opacity-90 btn-neon">
                  <MessageSquare className="w-5 h-5 mr-2" />
                  立即体验
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
              <Link href="/patents">
                <Button variant="secondary-on-dark" size="lg" className="text-base px-8 py-4 border-white/30 hover:bg-white/10 transition-medium">
                  <FileText className="w-5 h-5 mr-2" />
                  查看案例
                </Button>
              </Link>
            </div>

            {/* Trust Badges */}
            <div className="pt-12 flex flex-wrap items-center justify-center gap-8 text-white/60 text-sm animate-slideUp" style={{ animationDelay: '0.4s' }}>
              <div className="flex items-center gap-2 group hover:text-white transition-colors">
                <Shield className="w-5 h-5 group-hover:text-brand-cyan transition-colors" />
                <span>数据安全加密</span>
              </div>
              <div className="flex items-center gap-2 group hover:text-white transition-colors">
                <CheckCircle2 className="w-5 h-5 group-hover:text-brand-cyan transition-colors" />
                <span>符合专利法规范</span>
              </div>
              <div className="flex items-center gap-2 group hover:text-white transition-colors">
                <Users className="w-5 h-5 group-hover:text-brand-cyan transition-colors" />
                <span>500+ 企业信赖</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="bg-surface py-16 border-b border-hairline relative overflow-hidden">
        <div className="absolute inset-0 particles-bg opacity-50"></div>
        <div className="max-w-7xl mx-auto px-6 relative">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 lg:gap-12">
            <div className="text-center group">
              <div className="relative inline-block">
                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-brand-cyan/10 to-brand-cyan/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                  <TrendingUp className="w-8 h-8 text-brand-cyan-dark" />
                </div>
                <div className="absolute inset-0 rounded-2xl bg-brand-cyan/10 blur-xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
              </div>
              <div className="text-4xl lg:text-5xl font-bold text-tech-gradient animate-numberScroll">70%</div>
              <div className="mt-2 text-slate">撰写效率提升</div>
            </div>
            <div className="text-center group">
              <div className="relative inline-block">
                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-cyan-500/10 to-cyan-500/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                  <Target className="w-8 h-8 text-cyan-600" />
                </div>
                <div className="absolute inset-0 rounded-2xl bg-cyan-500/5 blur-xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
              </div>
              <div className="text-4xl lg:text-5xl font-bold text-tech-gradient-2 animate-numberScroll" style={{ animationDelay: '0.1s' }}>
                40%
              </div>
              <div className="mt-2 text-slate">授权率提高</div>
            </div>
            <div className="text-center group">
              <div className="relative inline-block">
                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-accent-purple/10 to-accent-purple/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                  <Building2 className="w-8 h-8 text-accent-purple" />
                </div>
                <div className="absolute inset-0 rounded-2xl bg-accent-purple/5 blur-xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
              </div>
              <div className="text-4xl lg:text-5xl font-bold text-tech-gradient animate-numberScroll" style={{ animationDelay: '0.2s' }}>
                500+
              </div>
              <div className="mt-2 text-slate">企业客户</div>
            </div>
            <div className="text-center group">
              <div className="relative inline-block">
                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-accent-orange/10 to-accent-orange/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                  <FileText className="w-8 h-8 text-accent-orange" />
                </div>
                <div className="absolute inset-0 rounded-2xl bg-accent-orange/5 blur-xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
              </div>
              <div className="text-4xl lg:text-5xl font-bold text-tech-gradient-2 animate-numberScroll" style={{ animationDelay: '0.3s' }}>
                10,000+
              </div>
              <div className="mt-2 text-slate">专利文件生成</div>
            </div>
          </div>
        </div>
      </section>

      {/* Core Values Section */}
      <section className="py-20 lg:py-28 relative overflow-hidden">
        <div className="absolute inset-0 grid-bg opacity-30"></div>
        <div className="max-w-7xl mx-auto px-6 relative">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-cyan/10 text-brand-cyan-dark text-sm font-medium mb-4">
              <Sparkles className="w-4 h-4" />
              核心优势
            </div>
            <h2 className="text-3xl lg:text-4xl font-bold text-ink mb-4">
              为什么选择<span className="text-tech-gradient">专利智脑</span>？
            </h2>
            <p className="text-lg text-slate max-w-2xl mx-auto">我们重新定义了专利撰写的流程，让创新者专注于技术本身</p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float">
              <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-brand-cyan/20 to-brand-cyan/5 flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300">
                <Zap className="w-7 h-7 text-brand-cyan-dark" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">极速撰写</h3>
              <p className="text-slate leading-relaxed text-sm">AI 智能分析技术方案，自动生成完整专利文档，将撰写周期从数周缩短至数天</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.05s' }}>
              <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-cyan-500/20 to-cyan-500/5 flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300">
                <Search className="w-7 h-7 text-cyan-600" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">精准检索</h3>
              <p className="text-slate leading-relaxed text-sm">智能检索全球专利数据库，精准定位现有技术，为专利布局提供数据支撑</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.1s' }}>
              <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-accent-purple/20 to-accent-purple/5 flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300">
                <Shield className="w-7 h-7 text-accent-purple" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">质量保障</h3>
              <p className="text-slate leading-relaxed text-sm">多维度质量审查机制，确保专利文件符合法规要求，显著提升授权成功率</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.15s' }}>
              <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-accent-orange/20 to-accent-orange/5 flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300">
                <Users className="w-7 h-7 text-accent-orange" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">团队协作</h3>
              <p className="text-slate leading-relaxed text-sm">支持多人协作编辑，版本管理清晰，让专利团队高效协同工作</p>
            </div>
          </div>
        </div>
      </section>

      {/* Multi-Agent Architecture Section */}
      <section className="py-20 lg:py-28 bg-gradient-to-b from-surface via-canvas to-surface relative overflow-hidden">
        <div className="absolute inset-0 grid-bg opacity-20"></div>
        <div className="max-w-7xl mx-auto px-6 relative">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-cyan/10 text-brand-cyan-dark text-sm font-medium mb-4">
              <BrainCircuit className="w-4 h-4 animate-glowPulse" />
              核心技术
            </div>
            <h2 className="text-3xl lg:text-4xl font-bold text-ink mb-4">
              <span className="text-tech-gradient">多智能体</span>协作架构
            </h2>
            <p className="text-lg text-slate max-w-2xl mx-auto">四大专业 AI Agent 各司其职，协同完成专利撰写全流程</p>
          </div>

          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Agent Cards */}
            <div className="space-y-4">
              <div className="group p-5 rounded-xl bg-canvas border border-hairline card-glow-border hover:shadow-lg transition-all duration-300 cursor-pointer">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-accent-purple/20 to-accent-purple/5 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                    <Lightbulb className="w-6 h-6 text-accent-purple" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-semibold text-ink">需求分析师</h4>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-accent-purple/10 text-accent-purple">Requirement Analyst</span>
                    </div>
                    <p className="text-sm text-slate">深度对话理解发明人意图，结构化梳理技术方案，识别核心创新点</p>
                  </div>
                  <ChevronRight className="w-5 h-5 text-muted group-hover:text-accent-purple group-hover:translate-x-1 transition-all" />
                </div>
              </div>

              <div
                className="group p-5 rounded-xl bg-canvas border border-hairline card-glow-border hover:shadow-lg transition-all duration-300 cursor-pointer"
                style={{ transitionDelay: '0.05s' }}
              >
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-cyan-500/20 to-cyan-500/5 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                    <Search className="w-6 h-6 text-cyan-600" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-semibold text-ink">检索分析师</h4>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-600">Retrieval Analyst</span>
                    </div>
                    <p className="text-sm text-slate">智能检索全球专利数据库，分析现有技术，评估专利性和授权前景</p>
                  </div>
                  <ChevronRight className="w-5 h-5 text-muted group-hover:text-cyan-600 group-hover:translate-x-1 transition-all" />
                </div>
              </div>

              <div
                className="group p-5 rounded-xl bg-canvas border border-hairline card-glow-border hover:shadow-lg transition-all duration-300 cursor-pointer"
                style={{ transitionDelay: '0.1s' }}
              >
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-brand-cyan/20 to-brand-cyan/5 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                    <PenTool className="w-6 h-6 text-brand-cyan-dark" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-semibold text-ink">专利撰写师</h4>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-brand-cyan/10 text-brand-cyan-dark">Patent Writer</span>
                    </div>
                    <p className="text-sm text-slate">专业撰写权利要求书、说明书、摘要，符合专利法规范要求</p>
                  </div>
                  <ChevronRight className="w-5 h-5 text-muted group-hover:text-brand-cyan-dark group-hover:translate-x-1 transition-all" />
                </div>
              </div>

              <div
                className="group p-5 rounded-xl bg-canvas border border-hairline card-glow-border hover:shadow-lg transition-all duration-300 cursor-pointer"
                style={{ transitionDelay: '0.15s' }}
              >
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-accent-orange/20 to-accent-orange/5 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                    <CheckCircle2 className="w-6 h-6 text-accent-orange" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-semibold text-ink">质量审查师</h4>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-accent-orange/10 text-accent-orange">Quality Reviewer</span>
                    </div>
                    <p className="text-sm text-slate">多维度质量检测，确保专利文件完整性、合规性和授权可能性</p>
                  </div>
                  <ChevronRight className="w-5 h-5 text-muted group-hover:text-accent-orange group-hover:translate-x-1 transition-all" />
                </div>
              </div>
            </div>

            {/* Architecture Diagram */}
            <div className="relative">
              <div className="aspect-square max-w-md mx-auto relative">
                {/* Background Glow */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 rounded-full bg-brand-cyan/15 blur-3xl animate-pulse"></div>

                {/* Center CEO Agent */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-24 h-24 rounded-full bg-gradient-to-br from-brand-teal-deep to-brand-teal flex items-center justify-center shadow-xl z-10 animate-techPulse">
                  <div className="text-center text-white">
                    <BrainCircuit className="w-8 h-8 mx-auto mb-1 animate-spin" style={{ animationDuration: '8s' }} />
                    <span className="text-xs font-medium">CEO Agent</span>
                  </div>
                </div>

                {/* Orbiting Agents */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-16 h-16 rounded-full bg-gradient-to-br from-accent-purple/30 to-accent-purple/10 border-2 border-accent-purple flex items-center justify-center animate-float">
                  <Lightbulb className="w-6 h-6 text-accent-purple" />
                </div>
                <div
                  className="absolute bottom-0 left-1/2 -translate-x-1/2 w-16 h-16 rounded-full bg-gradient-to-br from-brand-cyan/30 to-brand-cyan/10 border-2 border-brand-cyan flex items-center justify-center animate-float"
                  style={{ animationDelay: '0.75s' }}
                >
                  <PenTool className="w-6 h-6 text-brand-cyan-dark" />
                </div>
                <div
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-16 h-16 rounded-full bg-gradient-to-br from-cyan-500/30 to-cyan-500/10 border-2 border-cyan-500 flex items-center justify-center animate-float"
                  style={{ animationDelay: '1.5s' }}
                >
                  <Search className="w-6 h-6 text-cyan-600" />
                </div>
                <div
                  className="absolute right-0 top-1/2 -translate-y-1/2 w-16 h-16 rounded-full bg-gradient-to-br from-accent-orange/30 to-accent-orange/10 border-2 border-accent-orange flex items-center justify-center animate-float"
                  style={{ animationDelay: '2.25s' }}
                >
                  <CheckCircle2 className="w-6 h-6 text-accent-orange" />
                </div>

                {/* Connection Lines */}
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 400">
                  <circle cx="200" cy="200" r="120" fill="none" stroke="url(#gradient)" strokeWidth="2" strokeDasharray="8 4" opacity="0.3">
                    <animate attributeName="stroke-dashoffset" from="0" to="-48" dur="4s" repeatCount="indefinite" />
                  </circle>
                  <defs>
                    <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#00ed64" />
                      <stop offset="50%" stopColor="#06b6d4" />
                      <stop offset="100%" stopColor="#7b3ff2" />
                    </linearGradient>
                  </defs>
                  {/* Connection lines from center */}
                  <line x1="200" y1="200" x2="200" y2="80" stroke="url(#gradient)" strokeWidth="1.5" opacity="0.4" />
                  <line x1="200" y1="200" x2="200" y2="320" stroke="url(#gradient)" strokeWidth="1.5" opacity="0.4" />
                  <line x1="200" y1="200" x2="80" y2="200" stroke="url(#gradient)" strokeWidth="1.5" opacity="0.4" />
                  <line x1="200" y1="200" x2="320" y2="200" stroke="url(#gradient)" strokeWidth="1.5" opacity="0.4" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 lg:py-28 relative overflow-hidden">
        <div className="absolute inset-0 particles-bg opacity-30"></div>
        <div className="max-w-7xl mx-auto px-6 relative">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-cyan/10 text-brand-cyan-dark text-sm font-medium mb-4">
              <Sparkles className="w-4 h-4" />
              产品功能
            </div>
            <h2 className="text-3xl lg:text-4xl font-bold text-ink mb-4">
              强大的<span className="text-tech-gradient">产品功能</span>
            </h2>
            <p className="text-lg text-slate max-w-2xl mx-auto">从技术交底到专利申请，全流程智能化支持</p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float">
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-brand-cyan/20 to-brand-cyan/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <MessageSquare className="w-6 h-6 text-brand-cyan-dark" />
              </div>
              <h3 className="text-lg font-semibold text-ink mb-2">对话式交互</h3>
              <p className="text-slate text-sm leading-relaxed">通过自然语言对话描述发明，AI 智能引导完善技术方案，无需专业背景即可上手</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.05s' }}>
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-cyan-500/20 to-cyan-500/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <Search className="w-6 h-6 text-cyan-600" />
              </div>
              <h3 className="text-lg font-semibold text-ink mb-2">智能检索</h3>
              <p className="text-slate text-sm leading-relaxed">接入全球专利数据库，AI 自动分析对比文件，评估新颖性和创造性</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.1s' }}>
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-accent-purple/20 to-accent-purple/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <PenTool className="w-6 h-6 text-accent-purple" />
              </div>
              <h3 className="text-lg font-semibold text-ink mb-2">自动撰写</h3>
              <p className="text-slate text-sm leading-relaxed">一键生成权利要求书、说明书、摘要等完整申请文件，符合专利法规范</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.15s' }}>
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-accent-orange/20 to-accent-orange/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <CheckCircle2 className="w-6 h-6 text-accent-orange" />
              </div>
              <h3 className="text-lg font-semibold text-ink mb-2">质量审查</h3>
              <p className="text-slate text-sm leading-relaxed">多维度质量检测，识别潜在问题，提供修改建议，提升授权成功率</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.2s' }}>
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-accent-blue/20 to-accent-blue/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <TrendingUp className="w-6 h-6 text-accent-blue" />
              </div>
              <h3 className="text-lg font-semibold text-ink mb-2">数据分析</h3>
              <p className="text-slate text-sm leading-relaxed">可视化专利数据统计，追踪撰写进度，分析授权率趋势</p>
            </div>

            <div className="group p-6 rounded-2xl bg-canvas border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.25s' }}>
              <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-brand-teal/20 to-brand-teal/5 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <Building2 className="w-6 h-6 text-brand-teal-deep" />
              </div>
              <h3 className="text-lg font-semibold text-ink mb-2">企业部署</h3>
              <p className="text-slate text-sm leading-relaxed">支持私有化部署，数据安全可控，可定制化开发满足企业特殊需求</p>
            </div>
          </div>
        </div>
      </section>

      {/* Use Cases Section */}
      <section className="py-20 lg:py-28 bg-surface relative overflow-hidden">
        <div className="absolute inset-0 grid-bg-dark opacity-50"></div>
        <div className="max-w-7xl mx-auto px-6 relative">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-cyan/10 text-brand-cyan-dark text-sm font-medium mb-4">
              <Target className="w-4 h-4" />
              适用场景
            </div>
            <h2 className="text-3xl lg:text-4xl font-bold text-ink mb-4">
              <span className="text-tech-gradient">适用场景</span>
            </h2>
            <p className="text-lg text-slate max-w-2xl mx-auto">无论您是个人发明人还是企业研发团队，专利智脑都能为您提供专业支持</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <div className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-purple/20 to-accent-purple/5 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Lightbulb className="w-8 h-8 text-accent-purple" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">个人发明人</h3>
              <p className="text-slate leading-relaxed mb-4">无需专利代理经验，通过对话即可完成专利申请文件的撰写，大幅降低专利申请门槛和成本</p>
              <ul className="space-y-2 text-sm text-slate">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>智能引导式撰写</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>低成本快速申请</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>专业质量保障</span>
                </li>
              </ul>
            </div>

            <div className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.05s' }}>
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-cyan/20 to-brand-cyan/5 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Building2 className="w-8 h-8 text-brand-cyan-dark" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">企业研发团队</h3>
              <p className="text-slate leading-relaxed mb-4">提升专利撰写效率，建立标准化专利产出流程，加速技术创新成果转化</p>
              <ul className="space-y-2 text-sm text-slate">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>团队协作管理</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>标准化产出流程</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>知识产权资产积累</span>
                </li>
              </ul>
            </div>

            <div className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.1s' }}>
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-orange/20 to-accent-orange/5 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Users className="w-8 h-8 text-accent-orange" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">专利代理机构</h3>
              <p className="text-slate leading-relaxed mb-4">提升代理师工作效率，降低重复劳动，专注于高价值的专利策略和布局服务</p>
              <ul className="space-y-2 text-sm text-slate">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>批量案件处理</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>质量一致性保障</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-cyan flex-shrink-0" />
                  <span>客户服务增值</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Private Deployment Section */}
      <section className="py-20 lg:py-28 bg-gradient-to-b from-canvas via-surface to-canvas relative overflow-hidden">
        <div className="absolute inset-0 particles-bg opacity-20"></div>
        <div className="max-w-7xl mx-auto px-6 relative">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-cyan/10 text-brand-cyan-dark text-sm font-medium mb-4">
              <Server className="w-4 h-4" />
              企业部署
            </div>
            <h2 className="text-3xl lg:text-4xl font-bold text-ink mb-4">
              <span className="text-tech-gradient">私有部署</span>
            </h2>
            <p className="text-lg text-slate max-w-2xl mx-auto">支持科研企业、代理机构和其他行业低成本购买并实现私有部署</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <div className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-cyan/20 to-brand-cyan/5 flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform">
                <Shield className="w-8 h-8 text-brand-cyan-dark" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">数据绝对安全</h3>
              <p className="text-slate text-sm">本地化部署，数据不出城，确保企业核心知识产权安全可控</p>
            </div>

            <div
              className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float text-center"
              style={{ transitionDelay: '0.05s' }}
            >
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-orange/20 to-accent-orange/5 flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform">
                <Zap className="w-8 h-8 text-accent-orange" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">超低成本落地</h3>
              <p className="text-slate text-sm">打破行业高价壁垒，以合理价格获得专业级专利撰写能力</p>
            </div>

            <div className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float text-center" style={{ transitionDelay: '0.1s' }}>
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-purple/20 to-accent-purple/5 flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform">
                <Server className="w-8 h-8 text-accent-purple" />
              </div>
              <h3 className="text-xl font-semibold text-ink mb-3">快速交付使用</h3>
              <p className="text-slate text-sm">标准化流程，即刻启用，快速实现专利申请能力升级</p>
            </div>
          </div>

          <div className="text-center mt-10">
            <Link href="/contact">
              <Button size="lg" className="text-base text-white px-8 py-4 btn-neon animate-techPulse">
                <Server className="w-5 h-5 mr-2" />
                立即部署
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Integration & Extension Section */}
      <section className="py-20 lg:py-28 bg-surface relative overflow-hidden">
        <div className="absolute inset-0 grid-bg opacity-30"></div>
        <div className="max-w-7xl mx-auto px-6 relative">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-cyan/10 text-brand-cyan-dark text-sm font-medium mb-4">
              <Code2 className="w-4 h-4" />
              开发者支持
            </div>
            <h2 className="text-3xl lg:text-4xl font-bold text-ink mb-4">
              <span className="text-tech-gradient">集成与扩展</span>
            </h2>
            <p className="text-lg text-slate max-w-2xl mx-auto">将专利智脑能力融入您的业务系统，两种方式灵活选择</p>
          </div>

          <div className="grid lg:grid-cols-2 gap-8 max-w-4xl mx-auto">
            <div className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent-blue/20 to-accent-blue/5 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <Globe className="w-6 h-6 text-accent-blue" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-ink">网站嵌入</h3>
                  <p className="text-sm text-slate">快速接入您的业务平台</p>
                </div>
              </div>
              <p className="text-slate text-sm mb-4">一行 iframe 代码，将专利智脑服务无缝嵌入您的网站，支持多业务场景自由调度，访客无需注册即可使用。</p>
              <div className="bg-gradient-to-br from-ink to-slate-900 rounded-lg p-4 mb-6 overflow-x-auto border border-hairline">
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-red-500"></div>
                    <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  </div>
                  <span className="text-xs text-white/40">embed.html</span>
                </div>
                <code className="text-xs text-white/80 font-mono">
                  {'<iframe src="https://api.patent-ai.com/embed?key=your_key" width="100%" height="600" frameborder="0"></iframe>'}
                </code>
              </div>
              <Link href="/docs/embed">
                <Button variant="secondary" size="sm">
                  了解嵌入
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
            </div>

            <div className="group bg-canvas rounded-2xl p-8 border border-hairline card-glow-border card-float" style={{ transitionDelay: '0.05s' }}>
              <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-cyan/20 to-brand-cyan/5 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <Code2 className="w-6 h-6 text-brand-cyan-dark" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-ink">API 调用</h3>
                  <p className="text-sm text-slate">深度集成您的业务系统</p>
                </div>
              </div>
              <p className="text-slate text-sm mb-4">
                通过标准 REST API 将专利智脑能力集成到任意系统，支持 SSE 流式和异步轮询两种模式，最长支持 20 分钟工作流执行。
              </p>
              <div className="bg-gradient-to-br from-ink to-slate-900 rounded-lg p-4 mb-6 overflow-x-auto border border-hairline">
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-red-500"></div>
                    <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  </div>
                  <span className="text-xs text-white/40">api.sh</span>
                </div>
                <code className="text-xs text-white/80 font-mono">
                  {'curl -X POST https://api.patent-ai.com/v1/execute \\'}
                  {'<br/>  -H "Authorization: Bearer your_token" \\'}
                  {'<br/>  -H "Content-Type: application/json" \\'}
                  {'<br/>  -d \'{"task": "draft_patent", "input": {...}}\''}
                </code>
              </div>
              <Link href="/docs/api">
                <Button variant="secondary" size="sm">
                  查看接口
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 lg:py-28 bg-gradient-to-br from-brand-teal-deep via-brand-teal to-brand-teal-deep text-white relative overflow-hidden">
        {/* Background Effects */}
        <div className="absolute inset-0 grid-bg-dark"></div>
        <div className="absolute inset-0">
          <div className="absolute top-0 left-1/4 w-96 h-96 bg-brand-cyan/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 right-1/4 w-80 h-80 bg-accent-purple/10 rounded-full blur-3xl"></div>
        </div>

        <div className="max-w-4xl mx-auto px-6 text-center relative">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 mb-6">
            <Sparkles className="w-4 h-4 text-brand-cyan animate-glowPulse" />
            <span className="text-sm font-medium">立即开始您的专利之旅</span>
          </div>

          <h2 className="text-3xl lg:text-5xl font-bold mb-6">
            准备好开始您的<span className="text-tech-gradient neon-glow">创新之旅</span>了吗？
          </h2>
          <p className="text-lg text-white/80 mb-10 max-w-2xl mx-auto">加入专利智脑，体验 AI 驱动的知识产权全流程服务，让创新更快、更准、更高效。</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/chat">
              <Button size="lg" className="text-base px-10 py-4 shadow-xl hover:opacity-90 btn-neon animate-techPulse">
                免费注册
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <Link href="/contact">
              <Button variant="secondary-on-dark" size="lg" className="text-base px-10 py-4 border-white/30 hover:bg-white/10 transition-medium">
                联系销售
              </Button>
            </Link>
          </div>

          {/* Contact Info */}
          <div className="mt-16 pt-10 border-t border-white/10 flex flex-wrap items-center justify-center gap-10 text-sm text-white/60">
            <div className="flex items-center gap-3 group">
              <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center group-hover:bg-white/20 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                  />
                </svg>
              </div>
              <span>contact@patent-ai.com</span>
            </div>
            <div className="flex items-center gap-3 group">
              <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center group-hover:bg-white/20 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"
                  />
                </svg>
              </div>
              <span>400-888-8888</span>
            </div>
            <div className="flex items-center gap-3 group">
              <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center group-hover:bg-white/20 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                  />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <span>北京市海淀区中关村科技园</span>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-brand-teal-deep text-white/60 py-10">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-cyan/10 flex items-center justify-center">
                <BrainCircuit className="w-6 h-6 text-brand-cyan" />
              </div>
              <div>
                <span className="font-semibold text-white">专利智脑</span>
                <p className="text-xs text-white/40">AI-Powered Patent Platform</p>
              </div>
            </div>
            <div className="text-sm text-center md:text-left">
              <p className="text-xs text-white/40 mb-1">Copyright 2024 PatentAI. All rights reserved.</p>
              <p>津ICP备2026001119号 | 津公网安备12010402002416号</p>
            </div>
            <div className="flex items-center gap-6 text-sm">
              <a href="#" className="hover:text-white transition-colors">
                用户协议
              </a>
              <a href="#" className="hover:text-white transition-colors">
                隐私政策
              </a>
              <a href="#" className="hover:text-white transition-colors">
                联系我们
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}