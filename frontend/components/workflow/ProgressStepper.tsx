'use client';

import { Check, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';

type StepState = 'pending' | 'active' | 'completed' | 'error';

interface Step {
  id: string;
  label: string;
  description?: string;
  state: StepState;
}

interface ProgressStepperProps {
  steps: Step[];
}

const stateStyles: Record<StepState, string> = {
  pending: 'bg-slate-200 text-slate-500',
  active: 'bg-brand-green text-ink animate-pulse',
  completed: 'bg-brand-green text-ink',
  error: 'bg-red-500 text-white',
};

export function ProgressStepper({ steps }: ProgressStepperProps) {
  return (
    <div className="w-full">
      <div className="flex items-start justify-between">
        {steps.map((step, index) => (
          <div key={step.id} className="flex flex-col items-center flex-1">
            <div className="flex items-center w-full">
              {/* Step Circle */}
              <div
                className={clsx(
                  'w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm transition-all duration-300',
                  stateStyles[step.state]
                )}
              >
                {step.state === 'completed' ? (
                  <Check className="w-5 h-5" />
                ) : step.state === 'active' ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  index + 1
                )}
              </div>

              {/* Connector Line */}
              {index < steps.length - 1 && (
                <div className="flex-1 mx-2 h-0.5 bg-hairline relative overflow-hidden">
                  {(step.state === 'completed' || step.state === 'active') && (
                    <div
                      className={clsx(
                        'absolute inset-y-0 left-0 transition-all duration-500',
                        step.state === 'completed' ? 'w-full bg-brand-green' : 'w-1/2 bg-brand-green'
                      )}
                    />
                  )}
                </div>
              )}
            </div>

            {/* Label */}
            <div className="mt-3 text-center">
              <p
                className={clsx(
                  'text-sm font-medium transition-colors',
                  step.state === 'completed' || step.state === 'active'
                    ? 'text-ink'
                    : 'text-slate-400'
                )}
              >
                {step.label}
              </p>
              {step.description && (
                <p className="text-xs text-muted mt-1 max-w-24">
                  {step.description}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
