import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'TRACE-ZERO | Optimal Execution Simulator',
  description: 'Almgren-Chriss optimal execution simulator with Bloomberg terminal UI',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" style={{ height: '100%' }}>
      <body style={{ height: '100%', overflow: 'hidden' }}>
        {children}
      </body>
    </html>
  )
}
