import { useState, useEffect, useRef } from 'react'
import { useAuthStore } from '../store/authStore'
import { useChatStore } from '../store/chatStore'
import { apiClient } from '../lib/api'
import Layout from '../components/Layout'
import Button from '../components/Button'
import { Send, Plus } from 'lucide-react'

function Chat() {
  const user = useAuthStore((state) => state.user)
  const { currentConversation, messages, setMessages, addMessage, setLoading, isLoading } = useChatStore()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    const loadMessages = async () => {
      if (currentConversation && user) {
        try {
          const msgs = await apiClient.getMessages(currentConversation.id)
          setMessages(msgs)
        } catch (error) {
          console.error('Error loading messages:', error)
        }
      }
    }
    loadMessages()
  }, [currentConversation])

  const handleSend = async () => {
    if (!input.trim() || !user || !currentConversation) return

    const userMessage = input
    setInput('')
    setLoading(true)

    try {
      // Send user message
      const userMsg = await apiClient.sendMessage(currentConversation.id, user.id, userMessage)
      addMessage(userMsg)

      // Get AI response
      const response = await apiClient.chatCompletion([
        ...messages.map(m => ({ role: m.role, content: m.content })),
        { role: 'user', content: userMessage }
      ])

      const assistantContent = response.choices[0]?.message?.content || 'No response'
      
      // Save AI response
      const assistantMsg = await apiClient.sendMessage(
        currentConversation.id,
        user.id,
        assistantContent,
        'assistant'
      )
      addMessage(assistantMsg)
    } catch (error) {
      console.error('Error sending message:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleNewConversation = async () => {
    if (!user) return
    // Implement new conversation logic
  }

  return (
    <Layout>
      <div className="flex flex-col h-[calc(100vh-8rem)]">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-white">Chat</h1>
          <Button variant="secondary" size="sm" onClick={handleNewConversation}>
            <Plus className="w-4 h-4 mr-2" />
            New Chat
          </Button>
        </div>

        <div className="flex-1 bg-dark-800 rounded-lg border border-dark-700 overflow-hidden flex flex-col">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <p className="text-dark-400">No messages yet. Start a conversation!</p>
              </div>
            ) : (
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[70%] rounded-lg p-3 ${
                      message.role === 'user'
                        ? 'bg-primary-500 text-white'
                        : 'bg-dark-700 text-dark-100'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{message.content}</p>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="p-4 border-t border-dark-700">
            <div className="flex space-x-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
                placeholder="Type your message..."
                className="flex-1 px-4 py-2 bg-dark-700 border border-dark-600 rounded-lg text-white placeholder-dark-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={isLoading}
              />
              <Button
                variant="primary"
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                loading={isLoading}
              >
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  )
}

export default Chat