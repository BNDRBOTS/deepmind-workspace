import { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
}

function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`rounded-lg border p-6 ${className}`}>
      {children}
    </div>
  )
}

export default Card