'use client';

import { clsx } from 'clsx';

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        'animate-pulse rounded-md bg-slate-200',
        className
      )}
      {...props}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-4">
        <Skeleton className="h-12 w-12 rounded-full" />
        <div className="space-y-2 flex-1">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
      <Skeleton className="h-3 w-4/6" />
    </div>
  );
}

export function ChatMessageSkeleton({ isUser = false }: { isUser?: boolean }) {
  return (
    <div className={clsx(
      "flex gap-4",
      isUser ? 'justify-end' : 'justify-start'
    )}>
      {!isUser && (
        <div className="flex-shrink-0">
          <Skeleton className="w-10 h-10 rounded-full" />
        </div>
      )}
      <div className={clsx(
        "max-w-xl",
        isUser ? 'text-right' : 'text-left'
      )}>
        <div className="p-4 rounded-lg bg-white border border-hairline">
          <div className="space-y-2">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-4/6" />
          </div>
        </div>
        <Skeleton className="h-3 w-16 mt-2 mx-1" />
      </div>
      {isUser && (
        <div className="flex-shrink-0">
          <Skeleton className="w-10 h-10 rounded-full" />
        </div>
      )}
    </div>
  );
}

export function PatentListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-5 rounded-xl bg-white border border-hairline">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-6 w-20 rounded-full" />
              </div>
              <Skeleton className="h-4 w-48 mb-3" />
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-3 w-12" />
                </div>
                <Skeleton className="h-2 w-full rounded-full" />
              </div>
              <div className="flex items-center gap-6">
                <Skeleton className="h-3 w-32" />
                <Skeleton className="h-3 w-40" />
                <Skeleton className="h-3 w-36" />
              </div>
            </div>
            <div className="flex flex-col gap-2 ml-6">
              <Skeleton className="h-8 w-24 rounded-lg" />
              <Skeleton className="h-8 w-24 rounded-lg" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function AgentCardSkeleton() {
  return (
    <div className="p-5 rounded-xl bg-white border border-hairline">
      <div className="flex items-start gap-4 mb-4">
        <Skeleton className="w-12 h-12 rounded-xl" />
        <div className="flex-1">
          <Skeleton className="h-5 w-32 mb-2" />
          <Skeleton className="h-4 w-full" />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Skeleton className="h-6 w-16 rounded-full" />
        <Skeleton className="h-6 w-20 rounded-full" />
      </div>
    </div>
  );
}

export function ProgressSkeleton() {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 w-12" />
      </div>
      <Skeleton className="h-2 w-full rounded-full" />
    </div>
  );
}
