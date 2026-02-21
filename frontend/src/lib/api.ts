import axios, { AxiosInstance } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Request interceptor for auth token
    this.client.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('access_token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  // Auth endpoints
  async register(email: string, username: string, password: string) {
    const response = await this.client.post('/auth/register', { email, username, password })
    return response.data
  }

  async login(email: string, password: string) {
    const response = await this.client.post('/auth/login', { email, password })
    return response.data
  }

  async getCurrentUser() {
    const response = await this.client.get('/auth/me')
    return response.data
  }

  // Chat endpoints
  async getConversations(userId: string) {
    const response = await this.client.get(`/chat/conversations/${userId}`)
    return response.data
  }

  async createConversation(userId: string, title?: string) {
    const response = await this.client.post('/chat/conversations', { user_id: userId, title })
    return response.data
  }

  async getMessages(conversationId: string) {
    const response = await this.client.get(`/chat/messages/${conversationId}`)
    return response.data
  }

  async sendMessage(conversationId: string, userId: string, content: string, role: string = 'user') {
    const response = await this.client.post('/chat/messages', {
      conversation_id: conversationId,
      user_id: userId,
      content,
      role,
    })
    return response.data
  }

  // API/LLM endpoints
  async chatCompletion(messages: Array<{ role: string; content: string }>, stream: boolean = false) {
    const response = await this.client.post('/api/chat/completions', {
      messages,
      stream,
      model: 'deepseek-reasoner',
    })
    return response.data
  }

  // Memory endpoints
  async storeMemory(userId: string, content: string, metadata?: Record<string, any>) {
    const response = await this.client.post('/memory/store', {
      user_id: userId,
      content,
      metadata,
    })
    return response.data
  }

  async queryMemory(userId: string, query: string, topK: number = 5) {
    const response = await this.client.post('/memory/query', {
      user_id: userId,
      query,
      top_k: topK,
    })
    return response.data
  }

  async getMemoryStats(userId: string) {
    const response = await this.client.get(`/memory/stats/${userId}`)
    return response.data
  }
}

export const apiClient = new ApiClient()
export default apiClient