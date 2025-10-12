"use client"

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { 
  Search, 
  Send,
  BookOpen,
  FileText,
  Image,
  Table,
  Brain,
  Settings,
  RefreshCw,
  Copy,
  Check
} from 'lucide-react'
import { formatDate } from '@/lib/format'
import type { SearchAskRequest, SearchAskResponse } from '@/lib/api'

export default function KBSearchPage() {
  const { user } = useAuth()
  const toast = useToast()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchAskResponse | null>(null)
  const [isSearching, setIsSearching] = useState(false)
  const [knowledgeBases, setKnowledgeBases] = useState<string[]>([])
  const [selectedKB, setSelectedKB] = useState('')
  const [copiedText, setCopiedText] = useState<string | null>(null)

  // 搜索配置
  const [searchConfig, setSearchConfig] = useState({
    topk: 3,
    filter_mode: 'include',
    filter_type: 1,
    show_image: false,
    rerank: true,
    ask: true,
    ask_multimodal: false,
    ask_agent: false
  })

  useEffect(() => {
    loadKnowledgeBases()
  }, [])

  const loadKnowledgeBases = async () => {
    try {
      const response = await api.getDirectories()
      const directories = response || []
      // 提取目录标题作为知识库路径
      const kbPaths = directories.map((dir: any) => dir.title || dir.id)
      setKnowledgeBases(kbPaths)
      if (kbPaths.length > 0) {
        setSelectedKB(kbPaths[0])
      }
    } catch (error) {
      console.error('Failed to load knowledge bases:', error)
      toast.error('加载知识库列表失败')
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim() || !selectedKB) {
      toast.error('请输入搜索内容并选择知识库')
      return
    }

    try {
      setIsSearching(true)
      const request: SearchAskRequest = {
        question: searchQuery,
        topk: searchConfig.topk,
        filter_nodes: [selectedKB],
        filter_mode: searchConfig.filter_mode,
        filter_type: searchConfig.filter_type,
        show_image: searchConfig.show_image,
        rerank: searchConfig.rerank,
        ask: searchConfig.ask,
        ask_multimodal: searchConfig.ask_multimodal,
        ask_agent: searchConfig.ask_agent
      }

      const response = await api.searchKB(request)
      setSearchResults(response)
    } catch (error) {
      console.error('Failed to search knowledge base:', error)
      toast.error('搜索失败')
    } finally {
      setIsSearching(false)
    }
  }

  const handleCopyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedText(text)
      toast.success('已复制到剪贴板')
      setTimeout(() => setCopiedText(null), 2000)
    } catch (error) {
      console.error('Failed to copy text:', error)
      toast.error('复制失败')
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">知识库搜索</h1>
        <p className="text-muted-foreground">
          在您的知识库中搜索和问答，获取智能化的答案
        </p>
      </div>

      {/* 搜索配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <Settings className="mr-2 h-5 w-5" />
            搜索配置
          </CardTitle>
          <CardDescription>
            调整搜索参数以获得更精确的结果
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <Label htmlFor="knowledge_base">知识库</Label>
              <Select value={selectedKB} onValueChange={setSelectedKB}>
                <SelectTrigger>
                  <SelectValue placeholder="选择知识库" />
                </SelectTrigger>
                <SelectContent>
                  {knowledgeBases.map((kb) => (
                    <SelectItem key={kb} value={kb}>
                      {kb}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="topk">返回结果数量</Label>
              <Select
                value={searchConfig.topk.toString()}
                onValueChange={(value) => setSearchConfig({ ...searchConfig, topk: parseInt(value) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1</SelectItem>
                  <SelectItem value="3">3</SelectItem>
                  <SelectItem value="5">5</SelectItem>
                  <SelectItem value="10">10</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="filter_mode">过滤模式</Label>
              <Select
                value={searchConfig.filter_mode}
                onValueChange={(value) => setSearchConfig({ ...searchConfig, filter_mode: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="include">包含</SelectItem>
                  <SelectItem value="exclude">排除</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="filter_type">数据类型</Label>
              <Select
                value={searchConfig.filter_type.toString()}
                onValueChange={(value) => setSearchConfig({ ...searchConfig, filter_type: parseInt(value) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">全部</SelectItem>
                  <SelectItem value="2">文本</SelectItem>
                  <SelectItem value="3">图片</SelectItem>
                  <SelectItem value="4">表格</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex items-center justify-between">
              <Label htmlFor="show_image">显示图片</Label>
              <Switch
                id="show_image"
                checked={searchConfig.show_image}
                onCheckedChange={(checked) => setSearchConfig({ ...searchConfig, show_image: checked })}
              />
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="rerank">重排序</Label>
              <Switch
                id="rerank"
                checked={searchConfig.rerank}
                onCheckedChange={(checked) => setSearchConfig({ ...searchConfig, rerank: checked })}
              />
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="ask_multimodal">多模态问答</Label>
              <Switch
                id="ask_multimodal"
                checked={searchConfig.ask_multimodal}
                onCheckedChange={(checked) => setSearchConfig({ ...searchConfig, ask_multimodal: checked })}
              />
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="ask_agent">智能代理</Label>
              <Switch
                id="ask_agent"
                checked={searchConfig.ask_agent}
                onCheckedChange={(checked) => setSearchConfig({ ...searchConfig, ask_agent: checked })}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 搜索输入 */}
      <Card>
        <CardContent className="pt-6">
          <div className="space-y-4">
            <div className="relative">
              <Textarea
                placeholder="输入您的问题或搜索内容..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={handleKeyPress}
                className="min-h-[100px] resize-none"
              />
            </div>
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                按 Enter 搜索，Shift + Enter 换行
              </div>
              <Button onClick={handleSearch} disabled={isSearching || !searchQuery.trim()}>
                {isSearching ? (
                  <LoadingSpinner size="sm" className="mr-2" />
                ) : (
                  <Send className="mr-2 h-4 w-4" />
                )}
                {isSearching ? '搜索中...' : '搜索'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 搜索结果 */}
      {searchResults && (
        <div className="space-y-6">
          {/* AI 回答 */}
          {searchResults.answer && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Brain className="mr-2 h-5 w-5" />
                  AI 回答
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="prose prose-sm max-w-none">
                  <p className="whitespace-pre-wrap">{searchResults.answer}</p>
                </div>
                <div className="mt-4 flex justify-end">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleCopyText(searchResults.answer || '')}
                  >
                    {copiedText === searchResults.answer ? (
                      <Check className="mr-1 h-3 w-3" />
                    ) : (
                      <Copy className="mr-1 h-3 w-3" />
                    )}
                    复制回答
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 相关文档 */}
          {searchResults.sim_contents && searchResults.sim_contents.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <FileText className="mr-2 h-5 w-5" />
                  相关文档
                </CardTitle>
                <CardDescription>
                  找到 {searchResults.sim_contents.length} 个相关文档片段
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {searchResults.sim_contents.map((content, index) => (
                  <div key={index} className="border rounded-lg p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Badge variant="outline">{content.path}</Badge>
                        <Badge variant="secondary">
                          相似度: {(content.similarity * 100).toFixed(1)}%
                        </Badge>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleCopyText(content.content)}
                      >
                        {copiedText === content.content ? (
                          <Check className="h-3 w-3" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </Button>
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-3">
                      {content.content}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* 原始上下文 */}
          {searchResults.context && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <BookOpen className="mr-2 h-5 w-5" />
                  原始上下文
                </CardTitle>
                <CardDescription>
                  用于生成回答的完整上下文信息
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="prose prose-sm max-w-none">
                  <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg">
                    {searchResults.context}
                  </pre>
                </div>
                <div className="mt-4 flex justify-end">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleCopyText(searchResults.context)}
                  >
                    {copiedText === searchResults.context ? (
                      <Check className="mr-1 h-3 w-3" />
                    ) : (
                      <Copy className="mr-1 h-3 w-3" />
                    )}
                    复制上下文
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* 空状态 */}
      {!searchResults && !isSearching && (
        <EmptyState
          icon={<Search className="h-12 w-12" />}
          title="开始搜索"
          description="在知识库中搜索您需要的信息"
          action={
            <Button onClick={() => setSearchQuery('什么是人工智能？')}>
              <Search className="mr-2 h-4 w-4" />
              示例搜索
            </Button>
          }
        />
      )}
    </div>
  )
}
