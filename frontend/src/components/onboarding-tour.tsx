'use client';

import { useEffect } from 'react';

const TOUR_KEY = (slug: string) => `rag_tour_done_v2_${slug}`;

export function OnboardingTour({ slug }: { slug: string }) {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (localStorage.getItem(TOUR_KEY(slug))) return;

    let cancelled = false;

    const startTour = async () => {
      const { driver } = await import('driver.js');
      if (cancelled) return;

      const driverObj = driver({
        animate: true,
        showProgress: true,
        showButtons: ['next', 'previous', 'close'],
        steps: [
          {
            popover: {
              title: 'Welcome to RAG SaaS',
              description:
                'This quick tour shows you how to set up your workspace and start getting grounded AI answers from your knowledge base.',
            },
          },
          {
            element: '#chat-panel',
            popover: {
              title: 'Chat with your knowledge base',
              description:
                'Ask any question here. Answers are grounded in your sources — every reply includes citations so you can verify the response.',
              side: 'top',
            },
          },
          {
            element: '[href$="/sources"]',
            popover: {
              title: 'Add knowledge sources',
              description:
                'Go to Sources to add a website URL. The ingestion pipeline crawls it and builds the vector index automatically.',
              side: 'right',
            },
          },
          {
            element: '[href$="/models"]',
            popover: {
              title: 'Bring your own LLM key (optional)',
              description:
                'By default we use Groq\'s free Llama tier. You can swap to OpenAI, Claude, or DeepSeek by pasting your API key in AI Models.',
              side: 'right',
            },
          },
          {
            element: '[href$="/usage"]',
            popover: {
              title: 'Track usage & savings',
              description:
                'See how much you\'re saving by running on Groq vs a GPT-4-class provider. Estimates are transparent and auditable.',
              side: 'right',
            },
          },
        ],
        onDestroyed: () => {
          localStorage.setItem(TOUR_KEY(slug), '1');
        },
      });

      driverObj.drive();
    };

    const timeout = setTimeout(() => { void startTour(); }, 600);
    return () => { cancelled = true; clearTimeout(timeout); };
  }, [slug]);

  return null;
}
