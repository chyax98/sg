#!/bin/bash
# 快速开发安装脚本

set -e

echo "==> Search Gateway 开发安装"
echo ""

# 检查是否有未提交的更改
if [[ -n $(git status -s) ]]; then
    echo "⚠️  检测到未提交的更改："
    git status -s
    echo ""
    read -p "是否提交这些更改？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "提交信息: " commit_msg
        git add -A
        git commit -m "$commit_msg"
        echo "✓ 已提交"
    fi
fi

# 推送到远程
echo ""
echo "==> 推送到远程仓库..."
if git push; then
    echo "✓ 推送成功"
else
    echo "✗ 推送失败"
    exit 1
fi

# 重新安装
echo ""
echo "==> 重新安装到全局..."
if uv tool install --force .; then
    echo "✓ 安装成功"
else
    echo "✗ 安装失败"
    exit 1
fi

echo ""
echo "✓ 完成！"
echo ""
echo "可用命令："
echo "  sg start    - 启动服务器"
echo "  sg search   - 搜索"
echo "  sg status   - 查看状态"
