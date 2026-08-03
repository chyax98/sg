.PHONY: install reinstall dev test push update clean start stop status install-launchd uninstall-launchd

# 安装到全局（使用缓存，快速）
install:
	uv tool install --force .

# 重新安装（强制重新构建，代码更新后使用）
reinstall:
	uv tool install --force --reinstall .

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

# 启动服务（前台）
start:
	search-gateway start

# 启动服务（后台守护模式）
daemon:
	search-gateway start --daemon

# 停止服务
stop:
	search-gateway stop

# 查看状态
status:
	search-gateway status

# 显示帮助
help:
	@echo "Search Gateway 开发工具"
	@echo ""
	@echo "安装命令："
	@echo "  make install    - 安装到全局（使用缓存，快速）"
	@echo "  make reinstall  - 重新安装（强制重新构建，代码更新后使用）"
	@echo "  make dev        - 开发模式安装（代码修改自动生效）"
	@echo ""
	@echo "服务命令："
	@echo "  make start      - 启动服务（前台）"
	@echo "  make daemon     - 启动服务（后台守护模式）"
	@echo "  make stop       - 停止服务"
	@echo "  make status     - 查看服务状态"
	@echo "  make install-launchd - 安装 macOS 开机自启"
	@echo "  make uninstall-launchd - 卸载开机自启"
	@echo ""
	@echo "开发命令："
	@echo "  make push       - 推送并重新安装"
	@echo "  make update     - 提交、推送、重新安装"
	@echo "  make test       - 运行测试"
	@echo "  make clean      - 清理缓存"


# 安装 macOS LaunchAgent（开机自启 + KeepAlive）
# 通过 CLI 动态生成 plist，自动适配真实路径与端口
install-launchd:
	search-gateway daemon install

# 卸载 LaunchAgent
uninstall-launchd:
	search-gateway daemon uninstall
