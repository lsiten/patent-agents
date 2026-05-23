'use client';

import { HTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export type BadgeVariant =
  | 'green'
  | 'green-soft'
  | 'purple'
  | 'orange'
  | 'popular'
  | 'gray'
  | 'soft';

export type BadgeColor = 'green' | 'blue' | 'purple' | 'orange' | 'slate' | 'gray';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  color?: BadgeColor;
}

const variantStyles: Record<BadgeVariant, string> = {
  green: 'bg-brand-green text-ink rounded-sm px-2 py-0.5',
  'green-soft': 'bg-brand-green-soft text-brand-green-dark rounded-full px-2.5 py-1',
  purple: 'bg-accent-purple text-on-dark rounded-sm px-2 py-0.5',
  orange: 'bg-accent-orange text-on-dark rounded-sm px-2 py-0.5',
  popular: 'bg-brand-teal-deep text-brand-green rounded-full px-2.5 py-1',
  gray: 'bg-hairline-soft text-steel rounded-sm px-2 py-0.5',
  soft: 'rounded-full px-2.5 py-1',
};

const softColorStyles: Record<BadgeColor, string> = {
  green: 'bg-green-100 text-green-700',
  blue: 'bg-blue-100 text-blue-700',
  purple: 'bg-purple-100 text-purple-700',
  orange: 'bg-orange-100 text-orange-700',
  slate: 'bg-slate-100 text-slate-700',
  gray: 'bg-gray-100 text-gray-700',
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ children, variant = 'green-soft', color = 'green', className, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={twMerge(
          clsx(
            'inline-flex items-center font-euclid text-caption-bold uppercase tracking-wide',
            variantStyles[variant],
            variant === 'soft' && softColorStyles[color],
            className
          )
        )}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';
