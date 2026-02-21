import { useState, useEffect } from 'react'
import { useAuthStore } from '../store/authStore'
import { apiClient } from '../lib/api'
import Layout from '../components/Layout'
import Button from '../components/Button'
import Input from '../components/Input'
import Card from '../components/Card'
import { Search, Plus, Trash2 } from 'lucide-react'

interface Memory {
  id: string
  content: string
  score: number
  timestamp: string
}

function Memory() {
  const user = useAuthStore((state) => state.user)
  const [query, setQuery] = useState('')
  const [newMemory, setNewMemory] = useState('')
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState({ total_vectors: 0, dimension: 0 })

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    if (!user) return
    try {
      const data = await apiClient.getMemoryStats(user.id)
      setStats(data)
    } catch (error) {
      console.error('Error loading stats:', error)
    }
  }

  const handleSearch = async () => {
    if (!query.trim() || !user) return
    
    setLoading(true)
    try {
      const result = await apiClient.queryMemory(user.id, query)
      setMemories(result.memories)
    } catch (error) {
      console.error('Error searching memories:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleStore = async () => {
    if (!newMemory.trim() || !user) return
    
    setLoading(true)
    try {
      await apiClient.storeMemory(user.id, newMemory)
      setNewMemory('')
      loadStats()
      alert('Memory stored successfully!')
    } catch (error) {
      console.error('Error storing memory:', error)
      alert('Failed to store memory')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-white">Memory</h1>
          <p className="text-dark-400 mt-2">Your AI knowledge base</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card className="bg-dark-800 border-dark-700">
            <p className="text-dark-400 text-sm">Total Memories</p>
            <p className="text-3xl font-bold text-white">{stats.total_vectors}</p>
          </Card>
          <Card className="bg-dark-800 border-dark-700">
            <p className="text-dark-400 text-sm">Embedding Dimension</p>
            <p className="text-3xl font-bold text-white">{stats.dimension}</p>
          </Card>
        </div>

        <Card className="bg-dark-800 border-dark-700">
          <h2 className="text-xl font-semibold text-white mb-4">Store New Memory</h2>
          <div className="space-y-3">
            <textarea
              value={newMemory}
              onChange={(e) => setNewMemory(e.target.value)}
              placeholder="Enter information to store..."
              className="w-full px-4 py-2 bg-dark-700 border border-dark-600 rounded-lg text-white placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-primary-500 min-h-[100px]"
            />
            <Button variant="primary" onClick={handleStore} loading={loading}>
              <Plus className="w-4 h-4 mr-2" />
              Store Memory
            </Button>
          </div>
        </Card>

        <Card className="bg-dark-800 border-dark-700">
          <h2 className="text-xl font-semibold text-white mb-4">Search Memories</h2>
          <div className="space-y-4">
            <div className="flex space-x-2">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search your memories..."
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              />
              <Button variant="primary" onClick={handleSearch} loading={loading}>
                <Search className="w-4 h-4" />
              </Button>
            </div>

            {memories.length > 0 && (
              <div className="space-y-3">
                {memories.map((memory) => (
                  <div key={memory.id} className="p-4 bg-dark-700 rounded-lg">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-xs text-dark-400">
                        {new Date(memory.timestamp).toLocaleString()}
                      </span>
                      <span className="text-xs text-primary-400">
                        Score: {(memory.score * 100).toFixed(1)}%
                      </span>
                    </div>
                    <p className="text-white">{memory.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>
    </Layout>
  )
}

export default Memory