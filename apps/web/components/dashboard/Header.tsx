"use client"

import { Menu, Bell, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { ThemeToggle } from '@/components/theme-toggle'
import { useAuth } from '@/hooks/useAuth'
import { formatCredits } from '@/lib/format'

interface HeaderProps {
  onMenuClick: () => void
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user } = useAuth()

  return (
    <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b bg-background px-4 shadow-sm sm:gap-x-6 sm:px-6 lg:px-8">
      {/* 移动端菜单按钮 */}
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={onMenuClick}
      >
        <Menu className="h-6 w-6" />
        <span className="sr-only">打开侧边栏</span>
      </Button>

      {/* 分隔线 */}
      <div className="h-6 w-px bg-border lg:hidden" />

      {/* 搜索框 */}
      <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
        <div className="relative flex flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索..."
            className="pl-10"
          />
        </div>
      </div>

      {/* 右侧操作区 */}
      <div className="flex items-center gap-x-4 lg:gap-x-6">
        {/* Credits余额 */}
        <div className="hidden sm:flex items-center space-x-2">
          <Badge variant="secondary" className="text-sm">
            {formatCredits(user?.credits_balance || 0)} Credits
          </Badge>
        </div>

        {/* 通知 */}
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          <span className="sr-only">查看通知</span>
          {/* 通知红点 */}
          <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-destructive"></span>
        </Button>

        {/* 主题切换 */}
        <ThemeToggle />

        {/* 用户头像 */}
        <div className="flex items-center space-x-3">
          <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
            <span className="text-sm font-medium">
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}
