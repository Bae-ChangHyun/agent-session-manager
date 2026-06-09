<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://cdn.simpleicons.org/anthropic/D97757">
  <source media="(prefers-color-scheme: light)" srcset="https://cdn.simpleicons.org/anthropic/1A1915">
  <img alt="asm" width="48" height="48">
</picture>

# agent-session-manager

**Claude Code & Codex 세션·비용·데이터 관리 터미널 UI**

[![Python](https://img.shields.io/badge/Python-3.11%2B-D97757?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-TUI-D97757?style=for-the-badge)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-D97757?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Linux%20%7C%20macOS%20%7C%20Windows-1A1915?style=for-the-badge)](#)

통합 비용 대시보드 · 세션 정리 · 마이그레이션 · 백업/복원

**[English](README.md)**

</div>

---

## 데모

<div align="center">
<img src="docs/demo.gif" alt="asm" width="800"/>
</div>

---

## 왜 만들었나요?

**Claude Code**와 **OpenAI Codex**를 많이 쓸수록 `~/.claude`, `~/.codex`에 세션·비용·디버그·스냅샷 파일이 쌓입니다. 어떤 프로젝트가 비용을 얼마나 쓰는지, 어떤 파일이 정리해도 되는지 파악하기 어렵죠.

**agent-session-manager**은 터미널에서 두 도구를 한 대시보드로 관리합니다 — Claude / Codex **필터**로 합쳐 보거나 따로 볼 수 있습니다.

---

## 주요 기능

### 📊 통합 대시보드
- **Claude + Codex 합산 비용**, 소스 필터 (`s` → All / Claude / Codex)
- 모델별 토큰/비용 (Opus / Sonnet / Haiku / GPT-5.x), 소스 태그로 구분
- 일별 / 주별 / 월별 사용량 테이블
- 프로젝트 비용 Top 10 (Claude 프로젝트 + Codex 작업 디렉토리)
- 정확한 최신 모델 단가 (LiteLLM 기반 단가 테이블)

### 📁 Claude 프로젝트 관리
- `.claude.json` 기반 프로젝트 트리, 세션 대화 미리보기
- 세션 삭제, 설정에서 프로젝트 제거, Orphaned 세션 일괄 정리
- **중복 세션:** 여러 프로젝트에 복사된 동일 세션을 찾아 개별 복사본 삭제

### 🤖 Codex 세션
- `~/.codex` rollout 세션을 작업 디렉토리별로 조회
- 대화 미리보기, 개별 세션 삭제

### 📋 파일 히스토리 · 🐛 Debug / Todos
- Claude 파일 스냅샷, 디버그 로그, 세션별 task 목록(`tasks/`) 관리
- 빈 항목·Orphaned 일괄 정리

### 🔄 세션 마이그레이션 (Claude)
- 프로젝트 간 세션 복사(원본 유지), Append / Overwrite, 경로 자동 갱신

### 💾 백업 / 복원
- Claude: 설정 / settings / plugins / sessions / 전체 백업
- Codex: 세션 백업(`~/.codex/sessions`, 대용량 캐시 제외)
- 복원 전 자동 안전 백업, 실패 시 자동 롤백, recovery 스냅샷

---

## 설치

```bash
# pip
pip install agent-session-manager

# uv
uv tool install agent-session-manager

# 소스에서 설치
git clone https://github.com/Bae-ChangHyun/agent-session-manager.git
cd agent-session-manager
uv sync && uv run asm
```

---

## 사용법

```bash
asm                       # 기본 실행 (Claude + Codex 함께 표시)
asm --source codex        # 대시보드를 Codex 필터로 시작
asm --path /your/project  # 특정 Claude 프로젝트 필터링
asm --lang ko             # 한국어 UI
```

두 소스는 항상 한 화면에서 함께 다룹니다 — `--source`는 대시보드 초기 필터만 정하며, 실행 중 `s`로 언제든 바꿀 수 있습니다.

### 키보드 단축키

| 키 | 동작 |
|:---:|:---|
| `F1`~`F6` | 탭 전환 |
| `s` | 대시보드 소스 필터 (All / Claude / Codex) |
| `Tab` / `Shift+Tab` | 대시보드 기간(Daily / Weekly / Monthly) 순환 |
| `1` / `2` / `3` | 대시보드 기간 바로 전환 |
| `q` 종료 · `r` 전체 새로고침 |
| `d` / `D` | 선택 삭제 / 전체 Orphaned 삭제 |
| `Space` 선택 토글 · `Enter` 대화 미리보기(Migrate) |

---

## 관리되는 데이터 경로

| 경로 | 설명 |
|:---|:---|
| `~/.claude.json` · `~/.claude/projects/` | Claude 프로젝트 목록·비용·세션 JSONL |
| `~/.claude/file-history/` · `~/.claude/debug/` · `~/.claude/tasks/` | 스냅샷·디버그 로그·task 목록 |
| `~/.codex/sessions/` | Codex rollout 세션 파일 |
| `~/.asm/backups/` | 백업 (기존 `~/.cc-tui`에서 자동 이전) |
| `~/.asm/trash-log.jsonl` | 삭제 이력 로그 |

---

## 주의사항

> **삭제 작업은 모두 OS 휴지통으로 이동**됩니다. 휴지통에서 복구 가능합니다.
>
> 전체 백업은 `~/.claude` 통째로 복사하므로 디스크 용량을 확인하세요.
>
> Claude Code / Codex **내부 데이터를 직접 조작**합니다. 중요 작업 전 반드시 백업하세요.

---

## 라이선스

[MIT](LICENSE)

<div align="center">
<br/>
Made with <b>Claude Code</b>
</div>
