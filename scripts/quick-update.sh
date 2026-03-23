#!/bin/bash
# 快速更新脚本（不提交，只推送和安装）

set -e

echo "==> 快速更新"

# 推送
echo "==> 推送到远程..."
git push

# 重新安装
echo "==> 重新安装..."
uv tool install --force .

echo "✓ 完成！"
