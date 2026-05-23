'use client';

import { FileText, MessageSquare, Bot, FolderOpen, GitBranch, Plus } from 'lucide-react';
import { Button } from './Button';
import { Card } from './Card';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
}: EmptyStateProps) {
  return (
    <Card className="p-12 text-center">
      <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4">
        {icon || <FileText className="w-8 h-8 text-slate-400" />}
      </div>
      <h3 className="text-lg font-medium text-ink mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-slate mb-6 max-w-sm mx-auto">{description}</p>
      )}
      <div className="flex items-center justify-center gap-3">
        {action && (
          <Button onClick={action.onClick}>
            <Plus className="w-4 h-4 mr-1.5" />
            {action.label}
          </Button>
        )}
        {secondaryAction && (
          <Button variant="ghost" onClick={secondaryAction.onClick}>
            {secondaryAction.label}
          </Button>
        )}
      </div>
    </Card>
  );
}

// 预设的空状态组件
export function EmptyPatentList({ onCreate }: { onCreate?: () => void }) {
  return (
    <EmptyState
      icon={<FolderOpen className="w-8 h-8 text-slate-400" />}
      title="暂无专利申请"
      description="开始您的第一个专利申请吧，多智能体系统将协助您完成整个流程"
      action={
        onCreate
          ? {
              label: '新建专利申请',
              onClick: onCreate,
            }
          : undefined
      }
    />
  );
}

export function EmptyChat({ onStart }: { onStart?: () => void }) {
  return (
    <EmptyState
      icon={<MessageSquare className="w-8 h-8 text-slate-400" />}
      title="开始对话"
      description="描述您的发明创造，专业专利助理将协助您进行头脑风暴"
      action={
        onStart
          ? {
              label: '开始描述',
              onClick: onStart,
            }
          : undefined
      }
    />
  );
}

export function EmptyAgentList({ onAdd }: { onAdd?: () => void }) {
  return (
    <EmptyState
      icon={<Bot className="w-8 h-8 text-slate-400" />}
      title="暂无Agent"
      description="创建您的第一个专利Agent，开始智能化的专利申请流程"
      action={
        onAdd
          ? {
              label: '添加Agent',
              onClick: onAdd,
            }
          : undefined
      }
    />
  );
}

export function EmptyOrganization() {
  return (
    <EmptyState
      icon={<GitBranch className="w-8 h-8 text-slate-400" />}
      title="组织架构为空"
      description="创建您的第一个团队或Agent，构建智能化的专利申请组织"
    />
  );
}

// 搜索无结果状态
export function SearchEmpty({ query }: { query: string }) {
  return (
    <Card className="p-8 text-center">
      <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3">
        <FileText className="w-6 h-6 text-slate-400" />
      </div>
      <h3 className="font-medium text-ink mb-1">未找到匹配结果</h3>
      <p className="text-sm text-slate mb-4">
        未找到与 "{query}" 相关的内容，请尝试其他关键词
      </p>
    </Card>
  );
}

// 错误状态
export function ErrorState({
  title = '加载失败',
  message = '抱歉，出现了一些问题',
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="p-12 text-center">
      <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
        <svg
          className="w-8 h-8 text-red-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>
      <h3 className="text-lg font-medium text-ink mb-2">{title}</h3>
      <p className="text-sm text-slate mb-6 max-w-sm mx-auto">{message}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          重试
        </Button>
      )}
    </Card>
  );
}
