import type { Metadata } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'Heybassh - British English Teacher',
  icons: { icon: '/pipecat.svg' },
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
