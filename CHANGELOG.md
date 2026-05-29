# Changelog

All notable changes to this project will be documented in this file.

## [0.3.1] - 2026-05-29

### Removed
- Chat page (`/chat`) and all related UI, API client functions, and i18n keys
- Agent Chat page (`/agent`) and all related UI, API client functions, and i18n keys
- `showChat` toggle from Settings and LanguageContext
- Floating chat button from Layout
- All `chat.*`, `agent.*`, `nav.chat`, `nav.agent`, and `settings.showChat` translation keys (PT, EN, ES)

## [0.3.0] - 2026-05-28

### Added
- F6: per-session file activate/deactivate
- Persist chat options per session in localStorage
- F3: inline memory edit, compaction, project scoping
- SSE streaming for regular chat
- Fix `analyze_corpus` inline prompt
