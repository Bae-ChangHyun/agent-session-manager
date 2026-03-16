<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://cdn.simpleicons.org/anthropic/D97757">
  <source media="(prefers-color-scheme: light)" srcset="https://cdn.simpleicons.org/anthropic/1A1915">
  <img alt="Claude" width="48" height="48">
</picture>

# cc-session-utils

**Claude Code 세션 관리 터미널 UI**

[![Python](https://img.shields.io/badge/Python-3.11%2B-D97757?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-TUI-D97757?style=for-the-badge)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-D97757?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Linux%20%7C%20macOS-1A1915?style=for-the-badge)](#)

사용량 통계 · 세션 정리 · 마이그레이션 · 백업/복원 — 터미널에서 한눈에

**[English](README.md)**

</div>

---

## 데모

<div align="center">
<img src="docs/demo.gif" alt="cc-session-utils 데모" width="800"/>
</div>

---

## 왜 만들었나요?

Claude Code를 많이 사용할수록 `~/.claude` 디렉토리에 파일이 쌓이고, 어떤 프로젝트가 얼마나 비용을 쓰는지, 어떤 파일이 정리되지 않고 남아있는지 파악하기 어렵습니다.

**cc-session-utils**는 터미널을 벗어나지 않고 대시보드로 사용량을 파악하고, 불필요한 orphaned 데이터를 안전하게 정리할 수 있습니다.

---

## 주요 기능

### 📊 대시보드
- 총 사용 비용 및 모델별(Opus / Sonnet / Haiku) 토큰/비용 통계
- 일별 / 주별 / 월별 사용량 테이블
- 프로젝트별 비용 Top 10 바 차트
- 데이터 개요: 세션 수, 파일 히스토리, 디버그/투두 파일, 디스크 사용량

### 📁 프로젝트 관리
- `.claude.json` 기반 프로젝트 목록을 트리 구조로 표시
- 세션 클릭 시 대화 내용 미리보기
- 개별 세션 삭제, 설정에서 프로젝트 제거
- Orphaned 세션 일괄 감지 및 정리
- `--path` 옵션으로 특정 프로젝트만 필터링

### 📋 파일 히스토리
- Claude가 편집한 파일의 버전 스냅샷 관리
- Orphaned 항목 감지 및 일괄 정리

### 🐛 Debug / Todos
- 디버그 로그 및 투두 메모 관리, 미리보기 패널
- 빈 파일 및 Orphaned 파일 일괄 정리

### 🔄 세션 마이그레이션
- 프로젝트 간 세션 복사 (원본 유지)
- **개별 세션 선택:** `Space`로 체크/해제, `Enter`로 대화 미리보기
- Append / Overwrite 모드
- 경로 참조 자동 업데이트

### 💾 백업 / 복원
- 설정 백업 (`.claude.json`) 또는 전체 백업 (`~/.claude`)
- 복원 전 자동 안전 백업
- 복원 실패 시 자동 롤백

---

## 설치

```bash
# pip
pip install cc-session-utils

# uv
uv tool install cc-session-utils

# 소스에서 설치
git clone https://github.com/Bae-ChangHyun/cc-session-utils.git
cd cc-session-utils
uv sync && uv run cc-tui
```

---

## 사용법

```bash
cc-tui                          # 기본 실행
cc-tui --path /your/project     # 특정 프로젝트 필터링
cc-tui --lang ko                # 한국어 UI
```

### 키보드 단축키

| 키 | 동작 |
|:---:|:---|
| `F1`~`F6` | 탭 전환 |
| `q` | 앱 종료 |
| `r` | 전체 새로고침 |
| `d` / `D` | 선택 삭제 / 전체 Orphaned 삭제 |
| `Space` | 선택 토글 |
| `Enter` | 세션 대화 미리보기 (Migrate 탭) |

---

## 관리되는 데이터 경로

| 경로 | 설명 |
|:---|:---|
| `~/.claude.json` | 프로젝트 목록, 비용, 모델 사용량 |
| `~/.claude/projects/` | 세션 JSONL 파일 |
| `~/.claude/file-history/` | 파일 버전 스냅샷 |
| `~/.claude/debug/` | 디버그 로그 |
| `~/.claude/todos/` | 투두 메모 |
| `~/.cc-tui/backups/` | 백업 파일 |
| `~/.cc-tui/trash-log.jsonl` | 삭제 이력 로그 |

---

## 주의사항

> **삭제 작업은 모두 OS 휴지통으로 이동**됩니다. 휴지통에서 복구 가능합니다.
>
> 전체 백업은 `~/.claude` 통째로 복사하므로 디스크 용량을 확인하세요.
>
> Claude Code **내부 데이터를 직접 조작**합니다. 중요 작업 전 반드시 백업하세요.

---

## 라이선스

[MIT](LICENSE)

<div align="center">
<br/>
Made with <b>Claude Code</b>
</div>
