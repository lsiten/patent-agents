'use client';

import { ButtonHTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { Loader2 } from 'lucide-react';

export type ButtonVariant =
  | 'default'
  | 'primary'
  | 'secondary'
  | 'ghost'
  | 'on-dark'
  | 'secondary-on-dark'
  | 'link';

export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  fullWidth?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  default: 'bg-brand-green text-ink hover:opacity-90 focus:ring-2 focus:ring-brand-green/50',
  primary: 'bg-brand-green text-ink hover:opacity-90 focus:ring-2 focus:ring-brand-green/50',
  secondary: 'bg-transparent text-ink border border-hairline-strong hover:bg-surface',
  ghost: 'bg-transparent text-ink hover:bg-surface rounded-md',
  'on-dark': 'bg-brand-green text-ink hover:opacity-90',
  'secondary-on-dark': 'bg-transparent text-on-dark border border-hairline-dark hover:bg-white/5',
  link: 'bg-transparent text-brand-green-dark hover:underline p-0 h-auto',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-4 py-2 text-body-sm-medium',
  md: 'px-[22px] py-[10px] text-button-md',
  lg: 'px-8 py-4 text-body-md-medium',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      variant = 'primary',
      size = 'md',
      isLoading = false,
      fullWidth = false,
      className,
      disabled,
      ...props
    },
    ref
  ) => {
    const isPillShape = variant !== 'ghost' && variant !== 'link';

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={twMerge(
          clsx(
            'relative inline-flex items-center justify-center font-euclid font-medium transition-all duration-150',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            isPillShape ? 'rounded-full' : 'rounded-md',
            variantStyles[variant],
            sizeStyles[size],
            fullWidth && 'w-full',
            className
          )
        )}
        {...props}
      >
        {isLoading && (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
