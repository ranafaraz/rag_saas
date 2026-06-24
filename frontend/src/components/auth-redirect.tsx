'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-store';

export function AuthRedirect() {
  const { session, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && session) {
      router.replace(`/w/${session.workspace.slug}/chat`);
    }
  }, [session, loading, router]);

  return null;
}
