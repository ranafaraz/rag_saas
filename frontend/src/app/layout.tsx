import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'RAG SaaS | Knowledge Platform',
  description: 'Multi-tenant, role-aware retrieval-augmented generation SaaS platform.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
