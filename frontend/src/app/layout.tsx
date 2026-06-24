// src/app/layout.tsx
import type { Metadata } from 'next'
import { Source_Serif_4, Inter, JetBrains_Mono } from 'next/font/google'
import { Suspense } from 'react'
import './globals.css'
import { TopNav } from '@/components/nav/TopNav'
import { HealthDot } from '@/components/nav/HealthDot'
import { LENS_V4_ENABLED } from '@/lib/feature-flags'

const sourceSerif4 = Source_Serif_4({
  subsets: ['latin'],
  variable: '--font-source-serif-4',
  display: 'swap',
  weight: ['400', '600'],
})

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
  weight: ['400', '500'],
})

export const metadata: Metadata = {
  title: 'Atlas-OS',
  description: 'Fund manager research tool — Javeri Securities',
  robots: 'noindex, nofollow',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sourceSerif4.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body className={`${LENS_V4_ENABLED ? 'bg-surface-base' : 'bg-paper'} min-h-screen`}>
        {LENS_V4_ENABLED && (
          // Set day/night before paint to avoid a flash; default light. Flipped by the nav toggle.
          <script
            dangerouslySetInnerHTML={{
              __html: `(function(){try{var t=localStorage.getItem('atlas-theme')||'light';document.documentElement.setAttribute('data-theme',t)}catch(e){document.documentElement.setAttribute('data-theme','light')}})()`,
            }}
          />
        )}
        <TopNav healthDot={
          <Suspense fallback={<span className="inline-block w-2 h-2 rounded-full bg-paper-rule" />}>
            <HealthDot />
          </Suspense>
        } />
        <main className={LENS_V4_ENABLED ? 'pt-12' : 'pt-20'}>{children}</main>
      </body>
    </html>
  )
}
