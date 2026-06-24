'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { CORE_API } from '@/lib/api';

function VerifyContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get('token');

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('No verification token provided.');
      return;
    }
    const verify = async () => {
      try {
        const res = await fetch(`${CORE_API}/api/auth/verify-email/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        });
        const data = await res.json();
        if (!res.ok) {
          setMessage(data.error || 'Verification failed. The link may have expired.');
          setStatus('error');
        } else {
          setMessage(data.message || 'Email verified successfully!');
          setStatus('success');
          setTimeout(() => router.push('/login'), 2000);
        }
      } catch {
        setStatus('error');
        setMessage('Unable to reach the verification service.');
      }
    };
    void verify();
  }, [token, router]);

  return (
    <div className="auth-card text-center">
      <div className="auth-logo" style={{ margin: '0 auto 20px' }}>
        {status === 'loading' ? '⟳' : status === 'success' ? '✓' : '✕'}
      </div>
      <h1 className="auth-title">Email verification</h1>
      {status === 'loading' && <p className="auth-sub mt-3">Verifying your email address…</p>}
      {status === 'success' && (
        <>
          <p className="auth-sub mt-3">{message}</p>
          <p className="auth-sub">Redirecting to sign in…</p>
        </>
      )}
      {status === 'error' && (
        <>
          <p className="status-error mt-4">{message}</p>
          <Link href="/signup" className="btn-secondary mt-4 inline-flex">
            Back to sign up
          </Link>
        </>
      )}
    </div>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={
      <div className="auth-card text-center">
        <div className="auth-logo" style={{ margin: '0 auto 20px' }}>⟳</div>
        <h1 className="auth-title">Email verification</h1>
        <p className="auth-sub mt-3">Verifying your email address…</p>
      </div>
    }>
      <VerifyContent />
    </Suspense>
  );
}
