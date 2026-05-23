'use client';

import { InputHTMLAttributes, ReactNode, forwardRef } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, className, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="w-full font-euclid">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-body-sm-medium text-ink mb-xs"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <span className="absolute left-md top-1/2 -translate-y-1/2 text-muted">
              {icon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            className={twMerge(
              clsx(
                'w-full px-md py-sm text-body-md bg-canvas text-ink rounded-md border',
                icon && 'pl-10',
                'transition-all duration-150 placeholder:text-muted',
                'focus:outline-none focus:ring-2 focus:ring-brand-green/30 focus:border-brand-green-dark',
                error
                  ? 'border-red-500 focus:border-red-500 focus:ring-red-500/30'
                  : 'border-hairline-strong hover:border-stone',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                className
              )
            )}
            {...props}
          />
        </div>
        {error && (
          <p className="mt-xs text-body-sm text-red-500">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
