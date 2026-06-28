'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Target,
  Search,
  FileText,
} from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { toolsApi, type Tool } from '@/lib/api';

const toolIcons: Record<string, typeof Target> = {
  'claim-drafting': FileText,
  'patent-mining': Search,
};

const toolColors: Record<string, string> = {
  'claim-drafting': 'bg-gradient-to-br from-purple-500/20 to-purple-500/5 text-purple-600',
  'patent-mining': 'bg-gradient-to-br from-blue-500/20 to-blue-500/5 text-blue-600',
};

const iconBgColors: Record<string, string> = {
  'claim-drafting': 'bg-purple-100 text-purple-600',
  'patent-mining': 'bg-blue-100 text-blue-600',
};

export default function ToolsPage() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    fetchTools();
  }, []);

  async function fetchTools() {
    setLoading(true);
    try {
      const toolsList = await toolsApi.list();
      setTools(toolsList);
    } catch (error) {
      console.error('Failed to fetch tools:', error);
    } finally {
      setLoading(false);
    }
  }

  const displayNameMap: Record<string, string> = {
    'claim-drafting': '权项撰写',
    'patent-mining': '专利挖掘',
  };
  
  const getDisplayName = (tool: Tool) => {
    return displayNameMap[tool.name] || tool.display_name || tool.name.replace(/-/g, ' ');
  };

  return (
    <div className="min-h-screen bg-canvas">
      <section className="py-8 px-6 border-b border-hairline">
        <h1 className="text-2xl font-bold text-ink">工具集</h1>
      </section>

      <section className="py-8 px-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {loading ? (
            Array.from({ length: 2 }).map((_, index) => (
              <Card key={index} className="p-4 bg-surface">
                <div className="w-12 h-12 rounded-full bg-muted/20 mb-3 animate-pulse" />
                <div className="h-5 bg-muted/20 rounded mb-2 animate-pulse" />
                <div className="h-4 bg-muted/20 rounded animate-pulse" />
              </Card>
            ))
          ) : (
            tools.map((tool) => {
              const Icon = toolIcons[tool.name] || Target;
              const colorClass = toolColors[tool.name] || 'bg-gradient-to-br from-blue-500/20 to-blue-500/5 text-blue-600';
              const iconBg = iconBgColors[tool.name] || 'bg-blue-100 text-blue-600';
              const displayName = getDisplayName(tool);

              return (
                <Card
                  key={tool.name}
                  className={`p-6 min-h-[190px] cursor-pointer transition-all duration-300 hover:shadow-lg hover:-translate-y-1 border-2 ${colorClass.replace('text-', 'border-').replace('/5', '/20')} bg-canvas`}
                  onClick={() => router.push(`/tools/chat?name=${tool.name}`)}
                >
                  <div className="flex items-start gap-4">
                    <div className={`w-12 h-12 rounded-full ${iconBg} flex items-center justify-center flex-shrink-0 shadow-sm`}>
                      <Icon className="w-6 h-6" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="font-semibold text-ink text-base">{displayName}</h3>
                        <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full font-medium">官方</span>
                      </div>
                      <p className="text-sm text-slate line-clamp-2 mb-3 leading-relaxed">{tool.description}</p>
                      <div className="flex flex-wrap gap-2">
                        {tool.metadata.user_type?.map((type) => (
                          <span key={type} className="text-sm text-slate bg-surface/80 px-2 py-1 rounded-full border border-hairline">
                            {type}
                          </span>
                        ))}
                        {tool.metadata.category && (
                          <span className="text-sm text-slate bg-surface/80 px-2 py-1 rounded-full border border-hairline">
                            {tool.metadata.category}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </Card>
              );
            })
          )}
        </div>
      </section>
    </div>
  );
}