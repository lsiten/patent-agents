'use client';

import { Loader2, Bot, Sparkles, Search, FileText } from 'lucide-react';
import { Card } from './Card';
import { clsx } from 'clsx';

export interface LoadingStateProps {
  type?: 'spinner' | 'pulse' | 'dots' | 'agent-working';
  size?: 'sm' | 'md' | 'lg';
  text?: string;
  subText?: string;
  agentName?: string;
  className?: string;
}

export function LoadingState({
  type = 'spinner',
  size = 'md',
  text = '加载中...',
  subText,
  agentName,
  className,
}: LoadingStateProps) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  };

  if (type === 'agent-working') {
    return (
      <div className={clsx('flex flex-col items-center justify-center py-8', className)}>
        <div className="relative mb-4">
          <div className="w-16 h-16 rounded-full bg-brand-green/20 flex items-center justify-center animate-pulse">
            <Bot className="w-8 h-8 text-brand-green-dark" />
          </div>
          <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-white flex items-center justify-center shadow">
            <Sparkles className="w-4 h-4 text-yellow-500 animate-pulse" />
          </div>
        </div>
        <p className="font-medium text-ink">{text}</p>
        {agentName && (
          <p className="text-sm text-brand-green-dark mt-1">{agentName} 正在工作</p>
        )}
        {subText && (
          <p className="text-sm text-slate mt-2">{subText}</p>
        )}
      </div>
    );
  }

  if (type === 'dots') {
    return (
      <div className={clsx('flex items-center gap-1.5', className)}>
        <span className="w-2 h-2 rounded-full bg-brand-green animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-2 h-2 rounded-full bg-brand-green animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-2 h-2 rounded-full bg-brand-green animate-bounce" style={{ animationDelay: '300ms' }} />
        {text && <span className="text-sm text-slate ml-2">{text}</span>}
      </div>
    );
  }

  if (type === 'pulse') {
    return (
      <div className={clsx('flex items-center gap-2', className)}>
        <div className={clsx(sizeClasses[size], 'rounded-full bg-brand-green/50 animate-pulse')} />
        {text && <span className="text-sm text-slate">{text}</span>}
      </div>
    );
  }

  return (
    <div className={clsx('flex items-center gap-2', className)}>
      <Loader2 className={clsx(sizeClasses[size], 'animate-spin text-brand-green-dark')} />
      {text && <span className="text-sm text-slate">{text}</span>}
    </div>
  );
}

// 工作流阶段加载动画
export function WorkflowProgressAnimation({
  currentStage,
  stages,
}: {
  currentStage: number;
  stages: { name: string; description: string; icon: React.ReactNode }[];
}) {
  return (
    <Card className="p-6">
      <div className="space-y-4">
        {stages.map((stage, index) => {
          const isCompleted = index < currentStage;
          const isActive = index === currentStage;

          return (
            <div key={stage.name} className="flex items-start gap-4">
              <div
                className={clsx(
                  'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300',
                  isCompleted
                    ? 'bg-green-100 text-green-600'
                    : isActive
                    ? 'bg-brand-green text-ink animate-pulse'
                    : 'bg-slate-100 text-slate-400'
                )}
              >
                {isCompleted ? <FileText className="w-5 h-5" /> : stage.icon}
              </div>
              <div className="flex-1 pt-1">
                <div className="flex items-center gap-2">
                  <span
                    className={clsx(
                      'font-medium transition-colors',
                      isCompleted || isActive ? 'text-ink' : 'text-slate-400'
                    )}
                  >
                    {stage.name}
                  </span>
                  {isActive && (
                    <span className="flex items-center gap-1 text-xs text-brand-green-dark">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      处理中
                    </span>
                  )}
                  {isCompleted && (
                    <span className="text-xs text-green-600">已完成</span>
                  )}
                </div>
                <p
                  className={clsx(
                    'text-sm mt-0.5 transition-colors',
                    isCompleted || isActive ? 'text-slate' : 'text-slate-300'
                  )}
                >
                  {stage.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// 按钮加载状态
export function ButtonLoading({ text = '处理中...' }: { text?: string }) {
  return (
    <span className="flex items-center gap-2">
      <Loader2 className="w-4 h-4 animate-spin" />
      {text}
    </span>
  );
}

// 页面加载遮罩
export function PageLoadingOverlay({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="fixed inset-0 bg-white/80 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="text-center">
        <Loader2 className="w-10 h-10 animate-spin text-brand-green-dark mx-auto mb-3" />
        <p className="text-ink font-medium">{text}</p>
      </div>
    </div>
  );
}
