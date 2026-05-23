'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { FileText, Lightbulb, AlertCircle, Upload } from 'lucide-react';
import { workflowApi } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Textarea';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import type { PatentType } from '@/types';

const patentTypes: { value: PatentType; label: string; description: string }[] = [
  {
    value: 'invention',
    label: '发明专利',
    description: '针对产品、方法或其改进提出的新技术方案，保护期限20年',
  },
  {
    value: 'utility',
    label: '实用新型',
    description: '针对产品的形状、构造或其结合提出的实用新技术方案，保护期限10年',
  },
  {
    value: 'design',
    label: '外观设计',
    description: '针对产品的形状、图案或其结合以及色彩与形状、图案的结合作出的富有美感并适于工业应用的新设计，保护期限15年',
  },
];

export default function SubmitPage() {
  const router = useRouter();
  const [techDescription, setTechDescription] = useState('');
  const [selectedType, setSelectedType] = useState<PatentType | undefined>();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const description = techDescription.trim();
    if (!description) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const workflow = await workflowApi.create(description, 'default_user', selectedType);
      await workflowApi.start(workflow.task_id);
      router.push(`/workflow/${encodeURIComponent(workflow.task_id)}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '创建专利申请流程失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleExampleLoad = () => {
    setTechDescription(`本发明涉及一种基于人工智能的智能对话系统，主要创新点包括：

1. 多模态上下文理解：结合文本、语音、图像等多种输入方式，实现跨模态的语义理解和上下文关联。

2. 动态知识图谱构建：系统能够根据对话内容实时构建和更新领域知识图谱，提高回答的准确性和专业性。

3. 个性化对话策略：基于用户画像和历史对话数据，动态调整对话风格、回答深度和推荐策略。

4. 实时情感分析与反馈：集成情感分析引擎，能够识别用户情绪状态并作出相应的共情回应。

技术原理：采用 Transformer 架构的大语言模型作为核心，结合向量数据库实现高效的语义检索，通过强化学习优化对话策略。

应用场景：智能客服、个人助理、教育辅导、医疗咨询等领域。`);
  };

  return (
    <div className="py-section-lg bg-canvas">
      <div className="container mx-auto px-md">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="text-center mb-xxl">
            <h1 className="text-heading-2 font-euclid font-medium text-ink mb-md">
              提交您的技术发明
            </h1>
            <p className="text-subtitle text-steel max-w-2xl mx-auto">
              描述您的技术创新，我们的 AI Agent 将为您完成专业的专利申请文件
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-xl">
            {/* Main Form */}
            <div className="md:col-span-2">
              <form onSubmit={handleSubmit}>
                {error && (
                  <Card className="mb-lg border border-semantic-error-text bg-semantic-error-bg">
                    <CardContent className="py-md">
                      <p className="text-body-sm text-semantic-error-text">{error}</p>
                    </CardContent>
                  </Card>
                )}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="w-5 h-5 text-brand-green-dark" />
                      技术描述
                    </CardTitle>
                    <CardDescription>
                      请详细描述您的发明内容、技术方案和创新点
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-lg">
                    <Textarea
                      placeholder="请在此描述您的技术发明，包括但不限于：
• 发明的技术领域
• 背景技术与现有问题
• 核心技术方案与原理
• 关键创新点与技术特征
• 具体应用场景
• 有益效果与优势..."
                      value={techDescription}
                      onChange={(e) => setTechDescription(e.target.value)}
                      rows={16}
                      className="resize-none"
                    />
                    <div className="flex items-start gap-2 p-md rounded-md bg-semantic-warning-bg">
                      <Lightbulb className="w-5 h-5 text-semantic-warning-text flex-shrink-0 mt-0.5" />
                      <div className="text-body-sm text-semantic-warning-text">
                        <p className="font-medium mb-1">填写提示</p>
                        <ul className="list-disc list-inside space-y-0.5">
                          <li>尽可能详细描述技术方案，便于 AI 理解创新点</li>
                          <li>列出与现有技术的区别和优势</li>
                          <li>说明具体的技术实现方式</li>
                        </ul>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={handleExampleLoad}
                      className="text-body-sm text-brand-green-dark hover:underline font-medium"
                    >
                      加载示例技术描述 →
                    </button>

                    {/* File Upload Placeholder */}
                    <div className="border-2 border-dashed border-hairline rounded-lg p-xl text-center hover:border-brand-green/50 transition-colors cursor-pointer">
                      <Upload className="w-8 h-8 text-muted mx-auto mb-md" />
                      <p className="text-body-md text-steel mb-xs">
                        拖拽文件到此处或点击上传
                      </p>
                      <p className="text-body-sm text-muted">
                        支持 PDF、Word、图片等格式，用于补充技术文档、图纸等
                      </p>
                    </div>
                  </CardContent>
                </Card>

                {/* Patent Type Selection */}
                <Card className="mt-xl">
                  <CardHeader>
                    <CardTitle>专利类型选择</CardTitle>
                    <CardDescription>
                      选择您希望申请的专利类型，系统会据此调整撰写策略
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-md">
                      {patentTypes.map((type) => (
                        <label
                          key={type.value}
                          className={`flex items-start p-md rounded-lg border cursor-pointer transition-all ${
                            selectedType === type.value
                              ? 'border-brand-green bg-surface-feature'
                              : 'border-hairline hover:border-stone bg-canvas'
                          }`}
                        >
                          <input
                            type="radio"
                            name="patentType"
                            value={type.value}
                            checked={selectedType === type.value}
                            onChange={() => setSelectedType(type.value)}
                            className="mt-1 mr-md text-brand-green"
                          />
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-xs">
                              <span className="text-body-md-medium text-ink font-medium">
                                {type.label}
                              </span>
                              {selectedType === type.value && (
                                <Badge variant="green-soft">已选择</Badge>
                              )}
                            </div>
                            <p className="text-body-sm text-steel">
                              {type.description}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                    <p className="mt-md text-body-sm text-muted flex items-center gap-1">
                      <AlertCircle className="w-4 h-4" />
                      不确定选哪种？系统会在需求分析阶段自动推荐最合适的专利类型
                    </p>
                  </CardContent>
                  <CardFooter className="flex justify-end border-t border-hairline pt-lg">
                    <Button
                      type="submit"
                      size="lg"
                      isLoading={isSubmitting}
                      disabled={!techDescription.trim()}
                    >
                      开始专利申请流程
                    </Button>
                  </CardFooter>
                </Card>
              </form>
            </div>

            {/* Sidebar Help */}
            <div className="space-y-lg">
              <Card variant="feature">
                <CardHeader>
                  <CardTitle className="text-heading-5">填写指南</CardTitle>
                </CardHeader>
                <CardContent className="space-y-md">
                  <div>
                    <h4 className="text-body-sm-medium text-ink font-medium mb-xs">
                      1. 技术领域
                    </h4>
                    <p className="text-body-sm text-steel">
                      说明发明所属的技术领域，例如：人工智能、生物医药、电子通信等
                    </p>
                  </div>
                  <div>
                    <h4 className="text-body-sm-medium text-ink font-medium mb-xs">
                      2. 背景技术
                    </h4>
                    <p className="text-body-sm text-steel">
                      描述现有技术存在的问题和不足，说明您的发明要解决什么痛点
                    </p>
                  </div>
                  <div>
                    <h4 className="text-body-sm-medium text-ink font-medium mb-xs">
                      3. 技术方案
                    </h4>
                    <p className="text-body-sm text-steel">
                      详细阐述您的技术实现原理、方法、流程、系统架构等
                    </p>
                  </div>
                  <div>
                    <h4 className="text-body-sm-medium text-ink font-medium mb-xs">
                      4. 创新点
                    </h4>
                    <p className="text-body-sm text-steel">
                      明确列出与现有技术相比的区别特征和技术优势
                    </p>
                  </div>
                  <div>
                    <h4 className="text-body-sm-medium text-ink font-medium mb-xs">
                      5. 有益效果
                    </h4>
                    <p className="text-body-sm text-steel">
                      说明技术方案带来的技术效果、经济效益或社会价值
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-heading-5">预计流程</CardTitle>
                </CardHeader>
                <CardContent>
                  <ol className="space-y-md">
                    {[
                      { step: 1, title: '需求分析', time: '~2 分钟' },
                      { step: 2, title: '专利性检索评估', time: '~3 分钟' },
                      { step: 3, title: '申请文件撰写', time: '~5 分钟' },
                      { step: 4, title: '质量审查优化', time: '~2 分钟' },
                    ].map((item) => (
                      <li key={item.step} className="flex items-center gap-md">
                        <span className="w-6 h-6 rounded-full bg-surface-feature text-brand-green-dark text-caption-bold flex items-center justify-center flex-shrink-0">
                          {item.step}
                        </span>
                        <div className="flex-1">
                          <p className="text-body-sm-medium text-ink">{item.title}</p>
                          <p className="text-caption text-muted">{item.time}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                  <div className="mt-lg pt-md border-t border-hairline">
                    <p className="text-body-sm text-muted text-center">
                      总预计耗时：约 12 分钟
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
