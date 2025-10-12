"use client"

import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api, type User } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { 
  User as UserIcon, 
  Shield, 
  Settings as SettingsIcon,
  Bell,
  Globe,
  Palette,
  Save
} from 'lucide-react'
import { formatDate } from '@/lib/format'

const profileSchema = z.object({
  username: z.string().min(2, '用户名至少需要2个字符'),
  email: z.string().email('请输入有效的邮箱地址'),
  phone: z.string().optional(),
})

const passwordSchema = z.object({
  currentPassword: z.string().min(6, '当前密码至少需要6个字符'),
  newPassword: z.string().min(8, '新密码至少需要8个字符'),
  confirmPassword: z.string(),
}).refine((data) => data.newPassword === data.confirmPassword, {
  message: '密码不匹配',
  path: ['confirmPassword'],
})

type ProfileForm = z.infer<typeof profileSchema>
type PasswordForm = z.infer<typeof passwordSchema>

export default function SettingsPage() {
  const { user, refreshUser } = useAuth()
  const toast = useToast()
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [userProfile, setUserProfile] = useState<User | null>(null)

  const profileForm = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
  })

  const passwordForm = useForm<PasswordForm>({
    resolver: zodResolver(passwordSchema),
  })

  useEffect(() => {
    loadUserProfile()
  }, [])

  const loadUserProfile = async () => {
    try {
      setIsLoading(true)
      const profile = await api.getUserProfile()
      setUserProfile(profile)
      
      // 填充表单
      profileForm.reset({
        username: profile?.username || '',
        email: profile?.email || '',
        phone: profile?.phone || '',
      })
    } catch (error) {
      console.error('Failed to load user profile:', error)
      toast.error('加载用户资料失败')
    } finally {
      setIsLoading(false)
    }
  }

  const handleUpdateProfile = async (data: ProfileForm) => {
    try {
      setIsSaving(true)
      await api.updateUserProfile(data)
      await refreshUser()
      toast.success('个人资料已更新')
    } catch (error) {
      console.error('Failed to update profile:', error)
      toast.error('更新个人资料失败')
    } finally {
      setIsSaving(false)
    }
  }

  const handleUpdatePassword = async (data: PasswordForm) => {
    try {
      setIsSaving(true)
      // 这里应该调用更新密码的API
      toast.success('密码已更新')
      passwordForm.reset()
    } catch (error) {
      console.error('Failed to update password:', error)
      toast.error('更新密码失败')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">设置</h1>
        <p className="text-muted-foreground">
          管理您的账户设置和偏好
        </p>
      </div>

      <Tabs defaultValue="profile" className="space-y-4">
        <TabsList>
          <TabsTrigger value="profile">个人资料</TabsTrigger>
          <TabsTrigger value="security">安全设置</TabsTrigger>
          <TabsTrigger value="preferences">偏好设置</TabsTrigger>
        </TabsList>

        {/* 个人资料标签页 */}
        <TabsContent value="profile" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <UserIcon className="mr-2 h-5 w-5" />
                个人资料
              </CardTitle>
              <CardDescription>
                更新您的个人信息
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={profileForm.handleSubmit(handleUpdateProfile)} className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="username">用户名</Label>
                    <Input
                      id="username"
                      {...profileForm.register('username')}
                      disabled={isSaving}
                    />
                    {profileForm.formState.errors.username && (
                      <p className="text-sm text-destructive">
                        {profileForm.formState.errors.username.message}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email">邮箱</Label>
                    <Input
                      id="email"
                      type="email"
                      {...profileForm.register('email')}
                      disabled={isSaving}
                    />
                    {profileForm.formState.errors.email && (
                      <p className="text-sm text-destructive">
                        {profileForm.formState.errors.email.message}
                      </p>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="phone">手机号码</Label>
                  <Input
                    id="phone"
                    type="tel"
                    {...profileForm.register('phone')}
                    disabled={isSaving}
                  />
                  {profileForm.formState.errors.phone && (
                    <p className="text-sm text-destructive">
                      {profileForm.formState.errors.phone.message}
                    </p>
                  )}
                </div>

                <div className="flex justify-end">
                  <Button type="submit" disabled={isSaving}>
                    <Save className="mr-2 h-4 w-4" />
                    {isSaving ? '保存中...' : '保存更改'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {/* 账户信息 */}
          <Card>
            <CardHeader>
              <CardTitle>账户信息</CardTitle>
              <CardDescription>
                您的账户详细信息
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label className="text-sm text-muted-foreground">用户ID</Label>
                  <p className="font-mono text-sm">{user?.id}</p>
                </div>
                <div>
                  <Label className="text-sm text-muted-foreground">账户类型</Label>
                  <p className="text-sm">{user?.user_type || 'Standard'}</p>
                </div>
                <div>
                  <Label className="text-sm text-muted-foreground">注册时间</Label>
                  <p className="text-sm">{formatDate(user?.create_time || '', 'long')}</p>
                </div>
                <div>
                  <Label className="text-sm text-muted-foreground">账户状态</Label>
                  <p className="text-sm">
                    {user?.is_active ? '活跃' : '已禁用'}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* 安全设置标签页 */}
        <TabsContent value="security" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <Shield className="mr-2 h-5 w-5" />
                密码设置
              </CardTitle>
              <CardDescription>
                更新您的登录密码
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={passwordForm.handleSubmit(handleUpdatePassword)} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="currentPassword">当前密码</Label>
                  <Input
                    id="currentPassword"
                    type="password"
                    {...passwordForm.register('currentPassword')}
                    disabled={isSaving}
                  />
                  {passwordForm.formState.errors.currentPassword && (
                    <p className="text-sm text-destructive">
                      {passwordForm.formState.errors.currentPassword.message}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="newPassword">新密码</Label>
                  <Input
                    id="newPassword"
                    type="password"
                    {...passwordForm.register('newPassword')}
                    disabled={isSaving}
                  />
                  {passwordForm.formState.errors.newPassword && (
                    <p className="text-sm text-destructive">
                      {passwordForm.formState.errors.newPassword.message}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirmPassword">确认新密码</Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    {...passwordForm.register('confirmPassword')}
                    disabled={isSaving}
                  />
                  {passwordForm.formState.errors.confirmPassword && (
                    <p className="text-sm text-destructive">
                      {passwordForm.formState.errors.confirmPassword.message}
                    </p>
                  )}
                </div>

                <div className="flex justify-end">
                  <Button type="submit" disabled={isSaving}>
                    <Save className="mr-2 h-4 w-4" />
                    {isSaving ? '更新中...' : '更新密码'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {/* 双因素认证 */}
          <Card>
            <CardHeader>
              <CardTitle>双因素认证</CardTitle>
              <CardDescription>
                为您的账户添加额外的安全保护
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">双因素认证</p>
                  <p className="text-sm text-muted-foreground">
                    使用手机应用生成验证码
                  </p>
                </div>
                <Switch disabled />
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                此功能即将推出
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* 偏好设置标签页 */}
        <TabsContent value="preferences" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <SettingsIcon className="mr-2 h-5 w-5" />
                界面设置
              </CardTitle>
              <CardDescription>
                自定义您的界面体验
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label>深色模式</Label>
                  <p className="text-sm text-muted-foreground">
                    使用深色主题界面
                  </p>
                </div>
                <Switch disabled />
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>语言</Label>
                <Select defaultValue="zh-CN" disabled>
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="zh-CN">简体中文</SelectItem>
                    <SelectItem value="en-US">English</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>时区</Label>
                <Select defaultValue="Asia/Shanghai" disabled>
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Asia/Shanghai">北京时间</SelectItem>
                    <SelectItem value="UTC">UTC</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <Bell className="mr-2 h-5 w-5" />
                通知设置
              </CardTitle>
              <CardDescription>
                管理您接收的通知类型
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label>邮件通知</Label>
                  <p className="text-sm text-muted-foreground">
                    接收重要更新和通知
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>Credits余额提醒</Label>
                  <p className="text-sm text-muted-foreground">
                    当Credits余额不足时提醒
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>API使用报告</Label>
                  <p className="text-sm text-muted-foreground">
                    定期发送API使用情况报告
                  </p>
                </div>
                <Switch />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
