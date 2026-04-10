#!/bin/bash
# ==============================================
# 一键同步: 拉取远程 staging 最新代码到当前分支
# 用法: ./sync_staging.sh
# ==============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

STAGING="staging"
CURRENT_BRANCH=$(git branch --show-current)

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}   Sync from origin/$STAGING${NC}"
echo -e "${BLUE}======================================${NC}"
echo -e "${YELLOW}当前分支: ${BLUE}$CURRENT_BRANCH${NC}"

# 如果有未提交的更改，先 stash
STASHED=0
if [ -n "$(git status --porcelain)" ]; then
    echo -e "\n${YELLOW}检测到未提交的更改，自动 stash...${NC}"
    git stash push -m "sync_staging: auto stash"
    STASHED=1
fi

# fetch + merge
echo -e "\n${YELLOW}[1/2] 拉取 origin/$STAGING...${NC}"
git fetch origin $STAGING

echo -e "${YELLOW}[2/2] 合并 origin/$STAGING 到 $CURRENT_BRANCH...${NC}"
if git merge origin/$STAGING --no-edit; then
    echo -e "${GREEN}✓ 合并成功${NC}"
else
    echo -e "${RED}合并冲突！请手动解决后执行 git merge --continue${NC}"
    [ $STASHED -eq 1 ] && echo -e "${YELLOW}提示: 你的本地修改已 stash，解决冲突后手动 git stash pop${NC}"
    exit 1
fi

# 恢复 stash
if [ $STASHED -eq 1 ]; then
    echo -e "\n${YELLOW}恢复之前 stash 的更改...${NC}"
    if git stash pop; then
        echo -e "${GREEN}✓ stash 已恢复${NC}"
    else
        echo -e "${RED}stash pop 冲突，请手动 git stash pop${NC}"
    fi
fi

echo -e "\n${GREEN}✅ 已同步 origin/$STAGING 到 $CURRENT_BRANCH${NC}"
echo -e "${BLUE}======================================${NC}"
