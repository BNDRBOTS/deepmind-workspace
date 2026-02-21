import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/authStore'
import { apiClient } from '../lib/api'
import Layout from '../components/Layout'
import Card from '../components/Card'
import { MessageSquare, Brain, Activity, Clock } from 'lucide-react'

function Dashboard() {
  const user = useAuthStore((state) => state.user)
  const [stats, setStats] = useState({
    conversations: 0,
    messages: 0,
    memories: 0,
    lastActive: new Date().toISOString()
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadStats = async () => {
      if (!user) return
      
      try {
        const [conversations, memoryStats] = await Promise.all([
          apiClient.getConversations(user.id),
          apiClient.getMemoryStats(user.id)
        ])

        setStats({
          conversations: conversations.length,
          messages: conversations.reduce((sum: number, conv: any) => sum + (conv.message_count || 0), 0),
          memories: memoryStats.total_vectors || 0,
          lastActive: new Date().toISOString()
        })
      } catch (error) {
        console.error('Error loading stats:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStats()
  }, [user])

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          <p className="text-dark-400 mt-2">Welcome back, {user?.username}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card className="bg-dark-800 border-dark-700">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-primary-500/10 rounded-lg">
                <MessageSquare className="w-6 h-6 text-primary-400" />
              </div>
              <div>
                <p className="text-dark-400 text-sm">Conversations</p>
                <p className="text-2xl font-bold text-white">{loading ? '...' : stats.conversations}</p>
              </div>
            </div>
          </Card>

          <Card className="bg-dark-800 border-dark-700">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-green-500/10 rounded-lg">
                <Activity className="w-6 h-6 text-green-400" />
              </div>
              <div>
                <p className="text-dark-400 text-sm">Messages</p>
                <p className="text-2xl font-bold text-white">{loading ? '...' : stats.messages}</p>
              </div>
            </div>
          </Card>

          <Card className="bg-dark-800 border-dark-700">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-purple-500/10 rounded-lg">
                <Brain className="w-6 h-6 text-purple-400" />
              </div>
              <div>
                <p className="text-dark-400 text-sm">Memories</p>
                <p className="text-2xl font-bold text-white">{loading ? '...' : stats.memories}</p>
              </div>
            </div>
          </Card>

          <Card className="bg-dark-800 border-dark-700">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-orange-500/10 rounded-lg">
                <Clock className="w-6 h-6 text-orange-400" />
              </div>
              <div>
                <p className="text-dark-400 text-sm">Last Active</p>
                <p className="text-sm font-medium text-white">
                  {new Date(stats.lastActive).toLocaleDateString()}
                </p>
              </div>
            </div>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="bg-dark-800 border-dark-700">
            <h3 className="text-lg font-semibold text-white mb-4">Quick Actions</h3>
            <div className="space-y-3">
              <button className="w-full text-left p-3 bg-dark-700 hover:bg-dark-600 rounded-lg transition-colors">
                <p className="text-white font-medium">Start New Conversation</p>
                <p className="text-dark-400 text-sm">Begin chatting with AI</p>
              </button>
              <button className="w-full text-left p-3 bg-dark-700 hover:bg-dark-600 rounded-lg transition-colors">
                <p className="text-white font-medium">Search Memories</p>
                <p className="text-dark-400 text-sm">Query your knowledge base</p>
              </button>
            </div>
          </Card>

          <Card className="bg-dark-800 border-dark-700">
            <h3 className="text-lg font-semibold text-white mb-4">System Status</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-dark-400">API Service</span>
                <span className="text-green-400 text-sm font-medium">Operational</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-dark-400">Memory Core</span>
                <span className="text-green-400 text-sm font-medium">Operational</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-dark-400">Chat Service</span>
                <span className="text-green-400 text-sm font-medium">Operational</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </Layout>
  )
}

export default Dashboard