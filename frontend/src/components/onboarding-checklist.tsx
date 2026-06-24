'use client';

import Link from 'next/link';
import { useWorkspace } from '@/lib/workspace-context';

type ChecklistStep = {
  id: string;
  label: string;
  href?: string;
  done: boolean;
};

export function OnboardingChecklist({ slug }: { slug: string }) {
  const { data } = useWorkspace();

  const steps: ChecklistStep[] = [
    {
      id: 'workspace',
      label: 'Create your workspace',
      done: true,
    },
    {
      id: 'source',
      label: 'Add a knowledge source',
      href: `/w/${slug}/sources`,
      done: data.sources.length > 0,
    },
    {
      id: 'chat',
      label: 'Ask your first question',
      href: `/w/${slug}/chat`,
      done: data.traces.length > 0,
    },
    {
      id: 'member',
      label: 'Invite a team member',
      href: `/w/${slug}/members`,
      done: data.users.length > 1,
    },
  ];

  const done = steps.filter(s => s.done).length;
  const allDone = done === steps.length;

  if (allDone) return null;

  return (
    <div className="sidebar-card mt-3">
      <div className="sidebar-card-label">
        Getting started ({done}/{steps.length})
      </div>
      <div className="mt-2 space-y-1.5">
        {steps.map(step => (
          <div key={step.id} className={`checklist-item ${step.done ? 'done' : ''}`}>
            <div className={`check-circle ${step.done ? 'done' : ''}`}>
              {step.done ? '✓' : ''}
            </div>
            {step.href && !step.done ? (
              <Link href={step.href} className="text-xs text-slate-700 font-medium hover:underline">
                {step.label}
              </Link>
            ) : (
              <span className={`text-xs font-medium ${step.done ? 'line-through text-slate-400' : 'text-slate-700'}`}>
                {step.label}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
