import React from 'react'
import { DocsThemeConfig } from 'nextra-theme-docs'

const config: DocsThemeConfig = {
  logo: <span>Knowhere AI 文档</span>,
  project: {
    link: 'https://github.com/knowhere-ai/knowhere',
  },
  chat: {
    link: 'https://discord.gg/knowhere',
  },
  docsRepositoryBase: 'https://github.com/knowhere-ai/knowhere/tree/main/apps/docs',
  footer: {
    text: 'Knowhere AI Documentation © 2024',
  },
  head: (
    <>
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <meta property="og:title" content="Knowhere AI 文档" />
      <meta property="og:description" content="基于 AI 的知识库管理和智能问答系统" />
    </>
  ),
  search: {
    placeholder: '搜索文档...',
  },
  sidebar: {
    titleComponent({ title, type }) {
      if (type === 'separator') {
        return <span className="cursor-default">{title}</span>
      }
      return <>{title}</>
    },
    defaultMenuCollapseLevel: 1,
    toggleButton: true,
  },
  toc: {
    backToTop: true,
  },
  editLink: {
    text: '在 GitHub 上编辑此页',
  },
  feedback: {
    content: '有问题？给我们反馈',
    labels: 'feedback',
  },
  gitTimestamp: ({ timestamp }) => (
    <span>最后更新于 {timestamp.toLocaleDateString('zh-CN')}</span>
  ),
  i18n: [
    { locale: 'zh-CN', text: '中文' },
    { locale: 'en-US', text: 'English' },
  ],
}

export default config
