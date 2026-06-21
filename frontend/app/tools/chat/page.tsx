'use client';

import { Suspense } from 'react';
import ToolChatWorkspace from '@/components/tools/ToolChatWorkspace';

export default function ToolChatPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-canvas flex items-center justify-center"><div className="text-slate">加载中...</div></div>}>
      <ToolChatWorkspace />
    </Suspense>
  );
}