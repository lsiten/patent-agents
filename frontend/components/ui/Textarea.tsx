'use client';

import { TextareaHTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className, id, rows = 6, ...props }, ref) => {
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
        <textarea
          ref={ref}
          id={inputId}
          rows={rows}
          className={twMerge(
            clsx(
              'w-full px-md py-sm text-body-md bg-canvas text-ink rounded-md border resize-y',
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
        {error && (
          <p className="mt-xs text-body-sm text-red-500">{error}</p>
        )}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';
