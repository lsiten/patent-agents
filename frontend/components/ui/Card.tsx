'use client';

import { HTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export type CardVariant =
  | 'base'
  | 'feature'
  | 'feature-dark'
  | 'pricing'
  | 'pricing-featured'
  | 'course'
  | 'cert';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  hoverable?: boolean;
}

const variantStyles: Record<CardVariant, string> = {
  base: 'bg-canvas border border-hairline rounded-lg p-xl',
  feature: 'bg-canvas border border-hairline rounded-lg p-xxl',
  'feature-dark': 'bg-brand-teal-deep text-on-dark rounded-lg p-xxl',
  pricing: 'bg-canvas border border-hairline rounded-lg p-xxl',
  'pricing-featured': 'bg-surface-feature border-2 border-brand-green rounded-lg p-xxl',
  course: 'bg-canvas border border-hairline rounded-lg p-xl',
  cert: 'bg-canvas border border-hairline rounded-lg p-xl',
};

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ children, variant = 'base', hoverable = false, className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={twMerge(
          clsx(
            'font-euclid',
            variantStyles[variant],
            hoverable && 'transition-all duration-200 hover:shadow-card hover:-translate-y-1',
            className
          )
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {}

export const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ children, className, ...props }, ref) => (
    <div
      ref={ref}
      className={twMerge(clsx('flex flex-col space-y-1.5 pb-md', className))}
      {...props}
    >
      {children}
    </div>
  )
);

CardHeader.displayName = 'CardHeader';

interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {}

export const CardTitle = forwardRef<HTMLHeadingElement, CardTitleProps>(
  ({ children, className, ...props }, ref) => (
    <h3
      ref={ref}
      className={twMerge(clsx('text-heading-5 font-medium leading-none tracking-tight', className))}
      {...props}
    >
      {children}
    </h3>
  )
);

CardTitle.displayName = 'CardTitle';

interface CardDescriptionProps extends HTMLAttributes<HTMLParagraphElement> {}

export const CardDescription = forwardRef<HTMLParagraphElement, CardDescriptionProps>(
  ({ children, className, ...props }, ref) => (
    <p
      ref={ref}
      className={twMerge(clsx('text-body-sm text-steel', className))}
      {...props}
    >
      {children}
    </p>
  )
);

CardDescription.displayName = 'CardDescription';

interface CardContentProps extends HTMLAttributes<HTMLDivElement> {}

export const CardContent = forwardRef<HTMLDivElement, CardContentProps>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={twMerge(clsx('pt-0', className))} {...props}>
      {children}
    </div>
  )
);

CardContent.displayName = 'CardContent';

interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {}

export const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(
  ({ children, className, ...props }, ref) => (
    <div
      ref={ref}
      className={twMerge(clsx('flex items-center pt-md', className))}
      {...props}
    >
      {children}
    </div>
  )
);

CardFooter.displayName = 'CardFooter';
