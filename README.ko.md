# cc-session-utils

<div align="center">

<img src="https://upload.wikimedia.org/wikipedia/commons/8/8a/Claude_AI_logo.svg" alt="Claude" width="60"/>

### Claude Code 세션 관리 터미널 UI

**사용량 통계, 세션 정리, 마이그레이션, 백업/복원까지 — Textual 기반 TUI 앱**

[![Python](https://img.shields.io/badge/Python-3.11%2B-D97757?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-TUI-D97757?style=for-the-badge)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-D97757?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Linux%20%7C%20macOS-1A1915?style=for-the-badge)](#)

**[English](README.md)**

</div>

---

## 왜 만들었나요?

Claude Code를 많이 사용할수록 `~/.claude` 디렉토리에 파일이 쌓이고, 어떤 프로젝트가 얼마나 비용을 쓰는지, 어떤 파일이 정리되지 않고 남아있는지 파악하기 어렵습니다.

**cc-session-utils**는 터미널을 벗어나지 않고 대시보드로 사용량을 파악하고, 불필요한 orphaned 데이터를 안전하게 정리할 수 있습니다.

---

## 데모

| 기능 | 미리보기 |
|:-----|:---------|
| **대시보드** — 비용 & 사용량 통계 | ![Dashboard](docs/demo-dashboard.gif) |
| **프로젝트** — 세션 트리 & 미리보기 | ![Projects](docs/demo-projects.gif) |
| **마이그레이션** — 세션 선택 & 이동 | ![Migrate](docs/demo-migrate.gif) |
| **백업** — 백업 & 복원 | ![Backups](docs/demo-backups.gif) |

> GIF 준비 중. 녹화 방법: `pip install asciinema agg` → `asciinema rec` + `agg`

---

## 주요 기능

### 대시보드
- 총 사용 비용 및 모델별(Opus / Sonnet / Haiku) 토큰/비용 통계
- 일별 / 주별 / 월별 사용량 테이블 (클릭으로 전환)
- 프로젝트별 비용 Top 10 (바 차트 형식)
- 데이터 개요: 세션 수, 파일 히스토리 수, 디버그/투두 파일 수, 디스크 사용량

### 프로젝트 관리
- `.claude.json` 기반 프로젝트 목록을 트리 구조로 표시
- 프로젝트 펼치면 세션 목록 출력, 세션 클릭 시 대화 내용 미리보기
- 존재하지 않는 프로젝트(폴더 삭제/이동됨) 시각적 구분
- 개별 세션 삭제 (휴지통 이동), 설정에서 프로젝트 제거
- Orphaned 세션 디렉토리 일괄 감지 및 정리
- `--path` 옵션으로 특정 프로젝트만 필터링하여 관리

### 파일 히스토리
- Claude가 편집한 파일의 버전 스냅샷 목록 관리
- Orphaned 항목 감지 및 일괄 정리

### Debug / Todos
- Claude Code 내부 디버그 로그 및 투두 메모 파일 관리
- 파일 내용 우측 미리보기 패널에서 확인
- 빈 파일(내용이 `[]`, `{}`, 또는 비어있는 파일) 일괄 정리
- Orphaned 파일 일괄 정리

### 세션 마이그레이션
- 프로젝트 A의 세션을 프로젝트 B로 복사 (원본 유지)
- **개별 세션 선택:** `Space`로 체크/해제, `Enter`로 대화 내용 미리보기
- Append 모드 (기존 유지, 중복 스킵) / Overwrite 모드
- 메모리 파일 및 세션 인덱스 함께 마이그레이션
- 경로 참조(`cwd`, `projectPath` 등) 자동 업데이트

### 백업 / 복원
- 설정 백업: `.claude.json` 파일만 빠르게 백업
- 전체 백업: `~/.claude` 디렉토리 전체 복사
- 백업 목록 조회, 복원(현재 설정 자동 백업 후), 삭제
- 백업 삭제 시 OS 휴지통으로 이동 (`send2trash`)
- 복원 실패 시 자동 롤백(rename+rollback 패턴)

### 안전성
- **심볼릭 링크 차단:** symlink 여부 확인하여 우회 방지
- **경로 검증:** `is_relative_to` 기반 allowlist로 `~/.claude` 외부 접근 차단
- **스레드 안전 삭제 로그:** `threading.Lock` 보호 `~/.cc-tui/trash-log.jsonl`에 모든 삭제 기록
- **안전한 삭제:** 모든 삭제는 `send2trash`로 OS 휴지통 이동 (영구 삭제 없음)
- **원자적 설정 저장:** `.claude.json` 교체 시 tempfile + `os.replace`

---

## 설치

### PyPI에서 설치 (권장)

```bash
pip install cc-session-utils
```

### uv로 설치

```bash
uv tool install cc-session-utils
```

<details>
<summary><strong>소스에서 설치 (개발용)</strong></summary>

```bash
git clone https://github.com/Bae-ChangHyun/cc-session-utils.git
cd cc-session-utils
uv sync
uv run cc-tui
```

</details>

---

## 사용법

```bash
cc-tui                          # 기본 실행
cc-tui --path /your/project     # 특정 프로젝트만 필터링
cc-tui --lang ko                # 한국어 UI
CC_TUI_LANG=ko cc-tui           # 환경 변수로 설정
```

### 키보드 단축키

| 키 | 동작 |
|:---:|:---|
| `F1`~`F6` | 탭 전환 (Dashboard → Backups) |
| `q` | 앱 종료 |
| `r` | 전체 데이터 새로고침 |
| `↑`/`↓` | 목록 탐색 |
| `d` | 선택 항목 삭제 |
| `D` | Orphaned 전체 삭제 |
| `Space` | 다중 선택 토글 |
| `Enter` | 세션 대화 미리보기 (Migrate 탭) |

---

## 관리되는 데이터 경로

| 경로 | 설명 |
|:---|:---|
| `~/.claude.json` | 프로젝트 목록, 비용, 모델 사용량 설정 |
| `~/.claude/projects/` | 프로젝트별 세션 JSONL 파일 |
| `~/.claude/file-history/` | Claude가 편집한 파일의 버전 스냅샷 |
| `~/.claude/debug/` | Claude Code 내부 디버그 로그 |
| `~/.claude/todos/` | 세션 중 생성된 내부 투두 메모 |
| `~/.cc-tui/backups/` | cc-tui가 생성한 백업 파일 |
| `~/.cc-tui/trash-log.jsonl` | 삭제 이력 로그 |

---

## 주의사항

> **삭제 작업은 모두 OS 휴지통으로 이동**됩니다. 실수로 삭제한 경우 휴지통에서 복구할 수 있습니다.
>
> 전체 백업 기능은 `~/.claude` 디렉토리를 통째로 복사하므로 디스크 용량을 확인 후 사용하세요.
>
> 이 앱은 Claude Code의 **내부 데이터 파일을 직접 조작**합니다. 중요한 작업 전에는 반드시 백업을 생성하세요.

---

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하세요.

---

<div align="center">

Made with **Claude Code**

</div>
