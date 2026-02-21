import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MessageSquare, Brain, Settings, LayoutDashboard } from 'lucide-react'

interface LayoutProps {
  children: ReactNode
}

function Layout({ children }: LayoutProps) {
  const location = useLocation()

  const navigation = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Chat', href: '/chat', icon: MessageSquare },
    { name: 'Memory', href: '/memory', icon: Brain },
    { name: 'Settings', href: '/settings', icon: Settings },
  ]

  return (
    <div className="flex h-screen bg-dark-900">
      <div className="w-64 bg-dark-800 border-r border-dark-700 flex flex-col">
        <div className="p-6">
          <h1 className="text-2xl font-bold text-white">BNDR::ON</h1>
          <p className="text-dark-400 text-sm mt-1">Enterprise AI</p>
        </div>

        <nav className="flex-1 px-4 space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.href
            
            return (
              <Link
                key={item.name}
                to={item.href}
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-primary-500 text-white'
                    : 'text-dark-300 hover:bg-dark-700 hover:text-white'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="font-medium">{item.name}</span>
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-dark-700">
          <p className="text-dark-400 text-xs text-center">© 2026 BNDR BOTS</p>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="p-8">
          {children}
        </div>
      </div>
    </div>
  )
}

export default Layout