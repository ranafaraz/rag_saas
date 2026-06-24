import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-store';

export const metadata: Metadata = {
  title: 'Lumora — Open-Source RAG SaaS Platform',
  description:
    'Lumora is a free, open-source, multi-tenant Retrieval-Augmented Generation (RAG) platform. Ground your AI in real documents, cite every answer, and deploy anywhere.',
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
