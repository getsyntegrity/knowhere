#!/bin/bash
# ==============================================
# 标准推送脚本: parsing-update -> staging PR
# ==============================================
# 用法: ./push_to_staging.sh [可选的commit消息]
# ==============================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BRANCH="feat/eric/parsing-update"
TARGET_BRANCH="staging"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    标准推送流程 - Parsing Update${NC}"
echo -e "${BLUE}========================================${NC}"

# Step 1: 检查当前分支
echo -e "\n${YELLOW}[Step 1] 检查当前分支...${NC}"
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo -e "${RED}错误: 当前不在 $BRANCH 分支，当前分支: $CURRENT_BRANCH${NC}"
    echo -e "请先切换到 $BRANCH 分支: git checkout $BRANCH"
    exit 1
fi
echo -e "${GREEN}✓ 当前分支: $BRANCH${NC}"

# Step 2: 检查是否有未提交的更改
echo -e "\n${YELLOW}[Step 2] 检查未提交的更改...${NC}"
if [ -n "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}检测到未提交的更改:${NC}"
    git status --short
    
    # 询问是否提交
    echo -e "\n${YELLOW}是否提交这些更改? (y/n)${NC}"
    read -r REPLY
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # 使用传入的参数或默认消息
        COMMIT_MSG="${1:-feat: update parsing logic}"
        echo -e "提交消息: ${BLUE}$COMMIT_MSG${NC}"
        git add -A
        git commit -m "$COMMIT_MSG"
        echo -e "${GREEN}✓ 更改已提交${NC}"
    else
        echo -e "${RED}已取消，请先处理未提交的更改${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ 工作区干净${NC}"
fi

# Step 3: 拉取远程 staging 最新代码
echo -e "\n${YELLOW}[Step 3] 拉取远程 $TARGET_BRANCH 最新代码...${NC}"
git fetch origin $TARGET_BRANCH
echo -e "${GREEN}✓ 已拉取 origin/$TARGET_BRANCH${NC}"

# Step 4: 合并 staging 到当前分支
echo -e "\n${YELLOW}[Step 4] 合并 origin/$TARGET_BRANCH 到 $BRANCH...${NC}"
if git merge origin/$TARGET_BRANCH -m "Merge origin/$TARGET_BRANCH into $BRANCH"; then
    echo -e "${GREEN}✓ 合并成功${NC}"
else
    echo -e "${RED}合并冲突！请手动解决冲突后重新运行脚本${NC}"
    exit 1
fi

# Step 5: 推送到远程
echo -e "\n${YELLOW}[Step 5] 推送 $BRANCH 到远程...${NC}"
git push origin $BRANCH
echo -e "${GREEN}✓ 推送成功${NC}"

# Step 6: 提示创建 PR
echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}✅ 推送完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "\n${YELLOW}请创建 Pull Request:${NC}"
echo -e "  从: ${BLUE}$BRANCH${NC}"
echo -e "  到: ${BLUE}$TARGET_BRANCH${NC}"
echo -e "\n${YELLOW}GitHub PR 链接:${NC}"
echo -e "  https://github.com/Ontos-AI/knowhere-api/compare/$TARGET_BRANCH...$BRANCH"
echo -e "\n${GREEN}或者直接点击 GitHub 页面上的 'Compare & pull request' 按钮${NC}"
