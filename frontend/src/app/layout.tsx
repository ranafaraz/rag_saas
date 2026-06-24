import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-store';

export const metadata: Metadata = {
  title: 'RAG SaaS | Knowledge Platform',
  description: 'Multi-tenant, role-aware retrieval-augmented generation platform.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
