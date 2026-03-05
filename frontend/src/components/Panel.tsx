'use client'
import type { CSSProperties, ReactNode } from 'react'

interface PanelProps {
  title: string
  children: ReactNode
  style?: CSSProperties
  rightHeader?: ReactNode
}

export default function Panel({ title, children, style, rightHeader }: PanelProps) {
  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', ...style }}>
      <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>{title}</span>
        {rightHeader}
      </div>
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        {children}
      </div>
    </div>
  )
}
