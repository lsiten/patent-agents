'use client';

import { HTMLAttributes, useState } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps extends HTMLAttributes<HTMLPreElement> {
  language?: string;
  showLineNumbers?: boolean;
}

export const CodeBlock = ({
  children,
  language,
  className,
  ...props
}: CodeBlockProps) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (typeof children === 'string') {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="relative group font-source-code">
      <div className="absolute top-3 right-3 flex items-center gap-2">
        {language && (
          <span className="text-micro text-muted uppercase">{language}</span>
        )}
        <button
          onClick={handleCopy}
          className="p-1.5 rounded-md bg-white/5 text-muted hover:text-on-dark transition-colors opacity-0 group-hover:opacity-100"
          title="复制代码"
        >
          {copied ? (
            <Check className="w-4 h-4 text-brand-green" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
        </button>
      </div>
      <pre
        className={twMerge(
          clsx(
            'bg-canvas-dark text-on-dark rounded-md p-lg overflow-x-auto text-code-md font-source-code',
            className
          )
        )}
        {...props}
      >
        <code>{children}</code>
      </pre>
    </div>
  );
};
