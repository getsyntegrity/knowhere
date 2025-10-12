"use client"

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api, type APIKey } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { 
  Plus, 
  Search, 
  Copy, 
  RotateCcw, 
  Trash2, 
  Eye, 
  EyeOff,
  Key,
  Calendar,
  Activity
} from 'lucide-react'
import { formatDate, maskApiKey, copyToClipboard } from '@/lib/format'

export default function ApiKeysPage() {
  const { user } = useAuth()
  const toast = useToast()
  const [apiKeys, setApiKeys] = useState<APIKey[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [newApiKey, setNewApiKey] = useState({
    name: '',
    enabled_modules: [] as string[],
    expires_at: '',
  })
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [showCreatedKey, setShowCreatedKey] = useState(false)

  useEffect(() => {
    loadApiKeys()
  }, [])

  const loadApiKeys = async () => {
    try {
      setIsLoading(true)
      const response = await api.listApiKeys()
      setApiKeys(response.api_keys || [])
    } catch (error) {
      console.error('Failed to load API keys:', error)
      toast.error('加载API Keys失败')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateApiKey = async () => {
    try {
      setIsCreating(true)
      const createdKeyData = await api.createApiKey(newApiKey)
      
      if (createdKeyData?.api_key) {
        setCreatedKey(createdKeyData.api_key)
        setShowCreatedKey(true)
        toast.success('API Key创建成功')
        await loadApiKeys()
        setIsCreateDialogOpen(false)
        setNewApiKey({ name: '', enabled_modules: [], expires_at: '' })
      }
    } catch (error) {
      console.error('Failed to create API key:', error)
      toast.error('创建API Key失败')
    } finally {
      setIsCreating(false)
    }
  }

  const handleCopyKey = async (key: string) => {
    const success = await copyToClipboard(key)
    if (success) {
      toast.success('API Key已复制到剪贴板')
    } else {
      toast.error('复制失败')
    }
  }

  const handleRegenerateKey = async (keyId: string) => {
    try {
      await api.regenerateApiKey(keyId)
      toast.success('API Key已重新生成')
      await loadApiKeys()
    } catch (error) {
      console.error('Failed to regenerate API key:', error)
      toast.error('重新生成API Key失败')
    }
  }

  const handleRevokeKey = async (keyId: string) => {
    try {
      await api.revokeApiKey(keyId)
      toast.success('API Key已撤销')
      await loadApiKeys()
    } catch (error) {
      console.error('Failed to revoke API key:', error)
      toast.error('撤销API Key失败')
    }
  }

  const handleToggleKey = async (keyId: string) => {
    try {
      await api.toggleApiKey(keyId)
      toast.success('API Key状态已更新')
      await loadApiKeys()
    } catch (error) {
      console.error('Failed to toggle API key:', error)
      toast.error('更新API Key状态失败')
    }
  }

  const filteredApiKeys = apiKeys.filter(key =>
    key.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 页面标题和操作 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">API Keys</h1>
          <p className="text-muted-foreground">
            管理您的API访问密钥
          </p>
        </div>
        <div className="mt-4 sm:mt-0">
          <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                创建API Key
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>创建新的API Key</DialogTitle>
                <DialogDescription>
                  创建一个新的API访问密钥。请妥善保管您的密钥。
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="name">名称</Label>
                  <Input
                    id="name"
                    placeholder="例如：生产环境"
                    value={newApiKey.name}
                    onChange={(e) => setNewApiKey({ ...newApiKey, name: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="expires_at">过期时间（可选）</Label>
                  <Input
                    id="expires_at"
                    type="datetime-local"
                    value={newApiKey.expires_at}
                    onChange={(e) => setNewApiKey({ ...newApiKey, expires_at: e.target.value })}
                  />
                </div>
                <div className="flex justify-end space-x-2">
                  <Button
                    variant="outline"
                    onClick={() => setIsCreateDialogOpen(false)}
                  >
                    取消
                  </Button>
                  <Button
                    onClick={handleCreateApiKey}
                    disabled={isCreating || !newApiKey.name}
                  >
                    {isCreating ? '创建中...' : '创建'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* 搜索 */}
      <div className="flex items-center space-x-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索API Keys..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* API Keys列表 */}
      {filteredApiKeys.length === 0 ? (
        <EmptyState
          icon={<Key className="h-12 w-12 text-muted-foreground" />}
          title={searchTerm ? "未找到匹配的API Keys" : "还没有API Keys"}
          description={searchTerm ? "尝试调整搜索条件" : "创建您的第一个API Key开始使用"}
          action={!searchTerm ? {
            label: "创建API Key",
            onClick: () => setIsCreateDialogOpen(true)
          } : undefined}
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>API Keys ({filteredApiKeys.length})</CardTitle>
            <CardDescription>
              管理您的API访问密钥
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>API Key</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead>最后使用</TableHead>
                  <TableHead>过期时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredApiKeys.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">{key.name}</TableCell>
                    <TableCell>
                      <div className="flex items-center space-x-2">
                        <code className="text-sm bg-muted px-2 py-1 rounded">
                          {maskApiKey(`sk-${key.id}`)}
                        </code>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleCopyKey(`sk-${key.id}`)}
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center space-x-2">
                        <Switch
                          checked={key.is_active}
                          onCheckedChange={() => handleToggleKey(key.id)}
                        />
                        <Badge variant={key.is_active ? 'default' : 'secondary'}>
                          {key.is_active ? '活跃' : '禁用'}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>{formatDate(key.created_at, 'short')}</TableCell>
                    <TableCell>
                      {key.last_used_at ? formatDate(key.last_used_at, 'relative') : '从未使用'}
                    </TableCell>
                    <TableCell>
                      {key.expires_at ? formatDate(key.expires_at, 'short') : '永不过期'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end space-x-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRegenerateKey(key.id)}
                        >
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRevokeKey(key.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* 创建成功的对话框 */}
      <Dialog open={showCreatedKey} onOpenChange={setShowCreatedKey}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>API Key创建成功</DialogTitle>
            <DialogDescription>
              请复制并安全保存您的API Key。出于安全考虑，我们不会再次显示完整密钥。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>您的API Key</Label>
              <div className="flex items-center space-x-2">
                <Textarea
                  value={createdKey || ''}
                  readOnly
                  className="font-mono text-sm"
                  rows={3}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => createdKey && handleCopyKey(createdKey)}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-md">
              <p className="text-sm text-yellow-800 dark:text-yellow-200">
                ⚠️ 请立即复制并安全保存此API Key，关闭此对话框后将无法再次查看完整密钥。
              </p>
            </div>
            <div className="flex justify-end">
              <Button onClick={() => setShowCreatedKey(false)}>
                我已保存
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
