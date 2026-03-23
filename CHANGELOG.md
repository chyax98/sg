# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Batch search support**: Execute multiple queries in parallel via `/search/batch` endpoint and `sg search q1 q2 q3` CLI command
- **File-based result storage**: All search results are now saved to `~/.sg/history/` with file metadata (size, lines, words) returned to AI for intelligent reading strategies

### Changed
- **BREAKING**: Search responses now return `result_file` path instead of full results. AI tools must read the file to access content
- **BREAKING**: History is now always enabled and cannot be disabled. The `history.enabled` config option has been removed
- **Fallback mechanism**: Changed from global fallback to capability-specific. Configure `fallback_for: ["search"]` instead of `is_fallback: true`
- **CLI search output**: Now returns file paths with metadata instead of printing results directly

### Fixed
- Round Robin load balancing now uses thread-safe implementation with `threading.Lock`
- Removed all references to deprecated `is_fallback` field (replaced with `fallback_for`)
- Type safety improvements: resolved mypy errors in executor and provider implementations

### Migration Guide

**If you use the HTTP API or MCP tools:**
- Search responses now include `result_file` field pointing to a JSON file
- Read the file to access full search results
- File metadata helps decide reading strategy (direct read for small files, grep/jq for large files)

**If you have custom config:**
- Replace `is_fallback: true` with `fallback_for: ["search"]`
- Remove `history.enabled` from config (history is always on)

**If you use CLI:**
- `sg search` now outputs file paths instead of results
- Use `cat <path>` or `jq` to view results
- Multiple queries: `sg search "q1" "q2" "q3"` runs in parallel

