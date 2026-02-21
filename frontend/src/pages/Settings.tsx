import { useAuthStore } from '../store/authStore'
import Layout from '../components/Layout'
import Card from '../components/Card'
import Button from '../components/Button'
import { useNavigate } from 'react-router-dom'

function Settings() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-white">Settings</h1>
          <p className="text-dark-400 mt-2">Manage your account and preferences</p>
        </div>

        <Card className="bg-dark-800 border-dark-700">
          <h2 className="text-xl font-semibold text-white mb-4">Account Information</h2>
          <div className="space-y-4">
            <div>
              <p className="text-dark-400 text-sm">Username</p>
              <p className="text-white font-medium">{user?.username}</p>
            </div>
            <div>
              <p className="text-dark-400 text-sm">Email</p>
              <p className="text-white font-medium">{user?.email}</p>
            </div>
            <div>
              <p className="text-dark-400 text-sm">User ID</p>
              <p className="text-white font-mono text-sm">{user?.id}</p>
            </div>
          </div>
        </Card>

        <Card className="bg-dark-800 border-dark-700">
          <h2 className="text-xl font-semibold text-white mb-4">Preferences</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-white font-medium">Dark Mode</p>
                <p className="text-dark-400 text-sm">Currently enabled</p>
              </div>
              <button className="bg-primary-500 text-white px-4 py-2 rounded-lg">
                Enabled
              </button>
            </div>
          </div>
        </Card>

        <Card className="bg-dark-800 border-dark-700">
          <h2 className="text-xl font-semibold text-white mb-4">Danger Zone</h2>
          <div className="space-y-4">
            <Button variant="secondary" onClick={handleLogout} fullWidth>
              Sign Out
            </Button>
          </div>
        </Card>
      </div>
    </Layout>
  )
}

export default Settings