'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-store';
import { SESSION_KEY } from '@/lib/api';

export default function RootPage() {
  const router = useRouter();
  const { session, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (session) {
      router.replace(`/w/${session.workspace.slug}/chat`);
    } else {
      router.replace('/login');
    }
  }, [session, loading, router]);

  return (
    <main className="app-shell grid place-items-center">
      <div className="status-note">Loading...</div>
    </main>
  );
}
