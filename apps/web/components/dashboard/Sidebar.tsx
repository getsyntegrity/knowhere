"use client"

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet'
import {
  LayoutDashboard,
  Key,
  CreditCard,
  Settings,
  Menu,
  X,
  LogOut,
  BookOpen,
  Search,
  Clock,
  FileText,
  Table,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'

type NavigationItem = {
  name: string
  href: string
  icon: any
}

const navigation: NavigationItem[] = [
  { name: '概览', href: '/dashboard', icon: LayoutDashboard },
  { name: '任务管理', href: '/jobs', icon: Clock },
  { name: 'API Keys', href: '/api-keys', icon: Key },
  { name: '计费', href: '/billing', icon: CreditCard },
  { name: '设置', href: '/settings', icon: Settings },
]

interface SidebarProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function Sidebar({ open, onOpenChange }: SidebarProps) {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const { success, error, warning, info, loading } = useToast()

  const handleLogout = () => {
    logout()
    success('已退出登录')
  }

  const SidebarContent = () => (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex h-16 items-center px-6">
        <Link href="/dashboard" className="flex items-center space-x-2">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-sm">K</span>
          </div>
          <span className="text-xl font-bold">Knowhere</span>
        </Link>
      </div>

      {/* 用户信息 */}
      <div className="px-6 py-4 border-b">
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
            <span className="text-sm font-medium">
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{user?.username}</p>
            <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
          </div>
        </div>
      </div>

      {/* 导航菜单 */}
      <ScrollArea className="flex-1 px-3 py-4">
        <nav className="space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href
            const IconComponent = item.icon
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                )}
                onClick={() => onOpenChange(false)}
              >
                <IconComponent className="mr-3 h-5 w-5" />
                {item.name}
              </Link>
            )
          })}
        </nav>
      </ScrollArea>

      {/* 退出登录 */}
      <div className="p-3 border-t">
        <Button
          variant="ghost"
          onClick={handleLogout}
          className="w-full justify-start text-muted-foreground hover:text-foreground"
        >
          <LogOut className="mr-3 h-5 w-5" />
          退出登录
        </Button>
      </div>
    </div>
  )

  return (
    <>
      {/* 移动端侧边栏 */}
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="left" className="p-0 w-64">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      {/* 桌面端侧边栏 */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-64 lg:flex-col">
        <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r bg-background px-6 pb-4">
          <SidebarContent />
        </div>
      </div>
    </>
  )
}
