// src/app/layout.tsx — the shell: fonts, theme before first paint, rail + top bar.
import type { Metadata } from 'next'
import { Instrument_Sans, Instrument_Serif } from 'next/font/google'
import './globals.css'
import { Rail } from '@/components/shell/Rail'
import { TopBar } from '@/components/shell/TopBar'

const sans = Instrument_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-instrument-sans',
  display: 'swap',
})

const serif = Instrument_Serif({
  subsets: ['latin'],
  weight: '400',
  style: ['normal', 'italic'],
  variable: '--font-instrument-serif',
  display: 'swap',
})

export const metadata: Metadata = {
  title: { default: 'Global Atlas', template: '%s — Global Atlas' },
  description: 'An adviser’s instrument for the US ETF universe and the S&P 500',
  robots: 'noindex, nofollow',
}

// Runs before paint: the remembered theme, else the system preference, else light.
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem('atlas-global-theme');if(t!=='dark'&&t!=='light'){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.setAttribute('data-theme',t)}catch(e){document.documentElement.setAttribute('data-theme','light')}})()`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${serif.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="bg-ground font-sans text-ink">
        <a href="#main" className="skip-link text-body">
          Skip to content
        </a>
        <Rail />
        <TopBar />
        <main id="main" className="main">
          {children}
        </main>
      </body>
    </html>
  )
}
