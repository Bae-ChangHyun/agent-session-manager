# cc-tui

<div align="center">

![Logo](https://via.placeholder.com/150?text=CC-TUI)

**Claude Code 데이터를 터미널에서 한눈에 관리하세요**<br/>
사용량 통계, 세션 정리, 백업/복원까지 — Textual 기반 TUI 앱

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Textual](https://img.shields.io/badge/Textual-1.0%2B-purple?style=flat-square)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![uv](https://img.shields.io/badge/Managed%20with-uv-orange?style=flat-square)](https://github.com/astral-sh/uv)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey?style=flat-square)](#)

</div>

---

## 소개

**cc-tui**는 Claude Code가 `~/.claude` 디렉토리에 생성하는 세션 파일, 비용 로그, 파일 히스토리, 디버그/투두 파일들을 터미널에서 시각적으로 관리하는 TUI(Terminal User Interface) 앱입니다.

### 왜 만들었나요?

- **문제:** Claude Code를 많이 사용할수록 `~/.claude` 디렉토리에 파일이 쌓이고, 어떤 프로젝트가 얼마나 비용을 쓰는지, 어떤 파일이 정리되지 않고 남아있는지 파악하기 어렵습니다.
- **해결:** 터미널을 벗어나지 않고 대시보드로 사용량을 파악하고, 불필요한 orphaned 데이터를 안전하게 정리할 수 있습니다.

---

## 스크린샷

<div align="center">
  <img src="https://via.placeholder.com/900x550?text=Dashboard+Screenshot" alt="대시보드" width="900"/>
  <br/>
  <em>대시보드 - 총 비용, 모델별 사용량, 프로젝트별 비용 Top 10</em>
</div>

<details>
<summary><strong>더 많은 화면 보기</strong></summary>

<br/>

<div align="center">
  <img src="https://via.placeholder.com/900x550?text=Projects+Screen" alt="프로젝트 관리" width="900"/>
  <br/>
  <em>프로젝트 관리 - 세션 트리, 대화 내용 미리보기</em>
</div>

<br/>

<div align="center">
  <img src="https://via.placeholder.com/900x550?text=Debug+Todos+Screen" alt="Debug/Todos" width="900"/>
  <br/>
  <em>Debug/Todos - 파일 내용 미리보기, orphaned 정리</em>
</div>

<br/>

<div align="center">
  <img src="https://via.placeholder.com/900x550?text=Backups+Screen" alt="백업 관리" width="900"/>
  <br/>
  <em>백업 관리 - 설정/전체 백업 생성, 복원, 삭제</em>
</div>

</details>

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

### 파일 히스토리

- Claude가 편집한 파일의 버전 스냅샷 목록 관리
- Orphaned 항목(프로젝트 삭제로 연결이 끊긴 항목) 감지 및 일괄 정리

### Debug / Todos

- Claude Code 내부 디버그 로그 및 투두 메모 파일 관리
- 파일 내용 우측 미리보기 패널에서 확인
- 빈 파일(내용이 `[]`, `{}`, 또는 비어있는 파일) 일괄 정리
- Orphaned 파일(세션 삭제 후 남은 파일) 일괄 정리

### 세션 마이그레이션

- 프로젝트 A의 세션을 프로젝트 B로 복사 (원본 유지)
- Append 모드: 기존 세션 유지, 중복 건너뜀
- Overwrite 모드: 기존 세션 삭제 후 덮어쓰기
- 메모리 파일 및 세션 인덱스 함께 마이그레이션

### 백업 / 복원

- 설정 백업: `.claude.json` 파일만 빠르게 백업
- 전체 백업: `~/.claude` 디렉토리 전체 복사
- 백업 목록 조회, 복원(복원 전 현재 설정 자동 백업), 삭제

### 기타

- 한국어 / 영어 UI 지원 (i18n)
- 삭제는 모두 휴지통 이동 방식으로 안전하게 처리 (`send2trash`)
- `r` 키로 전체 데이터 새로고침

---

## 설치

### 사전 요구사항

- Python 3.11 이상
- [uv](https://github.com/astral-sh/uv) (권장) 또는 pip

### uv로 설치 (권장)

```bash
git clone https://github.com/[User]/cc-tui.git
cd cc-tui
uv sync
```

<details>
<summary><strong>pip으로 설치</strong></summary>

```bash
git clone https://github.com/[User]/cc-tui.git
cd cc-tui
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

</details>

---

## 사용법

### 기본 실행

```bash
# uv 사용 시
uv run cc-tui

# 가상환경 활성화 후
cc-tui
```

### 옵션

```bash
# 특정 프로젝트 경로 지정
cc-tui --path /your/project/path

# 언어 설정 (기본값: en)
cc-tui --lang ko

# 환경 변수로 언어 설정
CC_TUI_LANG=ko cc-tui
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

> 화면별 전체 단축키는 [docs/keybindings.md](docs/keybindings.md)를 참고하세요.

---

## 프로젝트 구조

```
cc-tui/
├── src/
│   └── cc_tui/
│       ├── __main__.py          # CLI 진입점 (--path, --lang 옵션)
│       ├── app.py               # Textual 앱, 탭 구성
│       ├── i18n.py              # 다국어 지원 (한국어/영어)
│       ├── models.py            # 데이터 모델, 경로 상수
│       ├── screens/
│       │   ├── dashboard.py     # 대시보드 (사용량/비용 통계)
│       │   ├── projects.py      # 프로젝트/세션 관리 트리
│       │   ├── file_history.py  # 파일 히스토리 관리
│       │   ├── debug_todos.py   # Debug/Todos 파일 관리
│       │   ├── migrate.py       # 세션 마이그레이션
│       │   ├── backups.py       # 백업/복원
│       │   ├── orphaned.py      # Orphaned 데이터 뷰
│       │   └── confirm.py       # 확인 다이얼로그
│       └── services/
│           ├── claude_data.py   # Claude 데이터 파싱/조회
│           ├── backup.py        # 백업/복원 로직
│           ├── cleaner.py       # 파일 삭제(휴지통 이동)
│           └── migrate.py       # 세션 마이그레이션 로직
├── pyproject.toml
└── README.md
```

---

## 기술 스택

| 기술 | 역할 |
|:---|:---|
| [Python 3.11+](https://python.org) | 언어 |
| [Textual](https://github.com/Textualize/textual) | TUI 프레임워크 |
| [Rich](https://github.com/Textualize/rich) | 텍스트 포맷팅 (Textual 내장) |
| [send2trash](https://github.com/arsenetar/send2trash) | OS 휴지통 연동 삭제 |
| [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) | 세션 데이터 조회 (폴백: JSONL 파싱) |
| [uv](https://github.com/astral-sh/uv) | 패키지/환경 관리 |

---

## 관리되는 Claude Code 데이터 경로

| 경로 | 설명 |
|:---|:---|
| `~/.claude.json` | 프로젝트 목록, 비용, 모델 사용량 설정 |
| `~/.claude/projects/` | 프로젝트별 세션 JSONL 파일 |
| `~/.claude/file-history/` | Claude가 편집한 파일의 버전 스냅샷 |
| `~/.claude/debug/` | Claude Code 내부 디버그 로그 |
| `~/.claude/todos/` | 세션 중 생성된 내부 투두 메모 |
| `~/.cc-tui/backups/` | cc-tui가 생성한 백업 파일 |

---

## 기여하기

버그 리포트, 기능 제안, 풀 리퀘스트 모두 환영합니다.

### 개발 환경 설정

```bash
git clone https://github.com/[User]/cc-tui.git
cd cc-tui
uv sync
uv run cc-tui
```

### 기여 방법

1. 이 저장소를 포크합니다.
2. 기능 브랜치를 생성합니다: `git checkout -b feat/my-feature`
3. 변경사항을 커밋합니다: `git commit -m "feat: 새 기능 추가"`
4. 브랜치에 푸시합니다: `git push origin feat/my-feature`
5. Pull Request를 생성합니다.

<details>
<summary><strong>커밋 메시지 컨벤션</strong></summary>

```
feat:     새 기능 추가
fix:      버그 수정
docs:     문서 수정
refactor: 리팩토링
chore:    기타 작업
```

</details>

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
Made with Claude Code
</div>
