.PHONY: install reinstall dev test push update clean

# 安装到全局
install:
	uv tool install --force .

# 重新安装（同 install）
reinstall: install

# 开发模式安装（代码修改后自动生效）
dev:
	uv tool install --editable .

# 快速更新：提交、推送、重新安装
update:
	@echo "==> Committing changes..."
	git add -A
	@read -p "Commit message: " msg; \
	git commit -m "$$msg" || true
	@echo "==> Pushing to remote..."
	git push
	@echo "==> Reinstalling..."
	uv tool install --force .
	@echo "==> Done!"

# 快速推送并重新安装（不提交）
push:
	@echo "==> Pushing to remote..."
	git push
	@echo "==> Reinstalling..."
	uv tool install --force .
	@echo "==> Done!"

# 运行测试
test:
	pytest tests/ -v

# 清理缓存
clean:
	rm -rf .pytest_cache __pycache__ .mypy_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# 显示帮助
help:
	@echo "Search Gateway 开发工具"
	@echo ""
	@echo "常用命令："
	@echo "  make install    - 安装到全局"
	@echo "  make dev        - 开发模式安装（代码修改自动生效）"
	@echo "  make push       - 推送并重新安装"
	@echo "  make update     - 提交、推送、重新安装"
	@echo "  make test       - 运行测试"
	@echo "  make clean      - 清理缓存"
