'use client';

import { createContext, useContext, useState, HTMLAttributes } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface TabsContextValue {
  activeTab: string;
  setActiveTab: (id: string) => void;
}

const TabsContext = createContext<TabsContextValue | undefined>(undefined);

interface TabsProps extends HTMLAttributes<HTMLDivElement> {
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
}

export function Tabs({
  defaultValue,
  value,
  onValueChange,
  children,
  className,
  ...props
}: TabsProps) {
  const [internalValue, setInternalValue] = useState<string>(defaultValue ?? '');
  const activeTab = value ?? internalValue;

  const setActiveTab = (newValue: string) => {
    if (value === undefined) {
      setInternalValue(newValue);
    }
    onValueChange?.(newValue);
  };

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className={twMerge(clsx('font-euclid', className))} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

interface TabsListProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'pill' | 'segmented';
}

export function TabsList({
  variant = 'segmented',
  children,
  className,
  ...props
}: TabsListProps) {
  return (
    <div
      className={twMerge(
        clsx(
          'flex gap-2',
          variant === 'segmented' && 'border-b border-hairline pb-0',
          className
        )
      )}
      role="tablist"
      {...props}
    >
      {children}
    </div>
  );
}

interface TabsTriggerProps extends HTMLAttributes<HTMLButtonElement> {
  value: string;
  variant?: 'pill' | 'segmented';
  disabled?: boolean;
}

export function TabsTrigger({
  value,
  variant = 'segmented',
  children,
  className,
  disabled = false,
  ...props
}: TabsTriggerProps) {
  const context = useContext(TabsContext);
  if (!context) throw new Error('TabsTrigger must be used within Tabs');

  const isActive = context.activeTab === value;

  const variantStyles =
    variant === 'pill'
      ? clsx(
          'rounded-full px-md py-xs border',
          isActive
            ? 'bg-ink text-on-dark border-ink'
            : 'bg-transparent text-steel border-hairline hover:border-stone',
          disabled && 'opacity-50 cursor-not-allowed hover:border-hairline'
        )
      : clsx(
          'border-b-2 border-transparent pb-2 mb-[-2px]',
          isActive
            ? 'text-brand-green-dark border-brand-green-dark'
            : 'text-steel hover:text-slate',
          disabled && 'opacity-50 cursor-not-allowed hover:text-steel'
        );

  return (
    <button
      role="tab"
      aria-selected={isActive}
      disabled={disabled}
      onClick={() => !disabled && context.setActiveTab(value)}
      className={twMerge(
        clsx(
          'font-euclid text-body-sm-medium transition-all duration-150',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green/30 focus-visible:rounded-md',
          variantStyles,
          className
        )
      )}
      {...props}
    >
      {children}
    </button>
  );
}

interface TabsContentProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
}

export function TabsContent({
  value,
  children,
  className,
  ...props
}: TabsContentProps) {
  const context = useContext(TabsContext);
  if (!context) throw new Error('TabsContent must be used within Tabs');

  const isActive = context.activeTab === value;

  if (!isActive) return null;

  return (
    <div
      role="tabpanel"
      className={twMerge(clsx('pt-lg', className))}
      {...props}
    >
      {children}
    </div>
  );
}
