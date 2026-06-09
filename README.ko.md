<div align="center">

# agent-session-manager

**Claude Code와 Codex가 남기는 모든 것을, 터미널 대시보드 하나로.**
`~/.claude`와 `~/.codex`의 비용·세션을 한 화면에서 보고, Claude / Codex 필터로 정리합니다.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Built with Textual](https://img.shields.io/badge/Built%20with-Textual-5A2CA0?style=flat-square)](https://github.com/Textualize/textual)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-orange?style=flat-square)](#)
[![Status](https://img.shields.io/badge/Status-Personal--use-lightgrey?style=flat-square)](#)

`asm` · **[English](README.md)**

</div>

---

> **⚠️ 먼저 알아두세요**
> 이 도구는 **Claude Code와 OpenAI Codex의 내부 데이터**(`~/.claude`, `~/.codex`)를 직접 읽고 수정합니다. 모든 삭제는 OS 휴지통으로 가고 로그에 남지만, 대량 작업 전에는 백업을 권장합니다. Anthropic·OpenAI와 무관한 개인 프로젝트입니다.

---

## 무엇인가요

**Claude Code**와 **Codex**를 쓰다 보면 `~/.claude`, `~/.codex`에 세션 기록·비용 로그·디버그·task 목록·스냅샷이 쌓입니다. 몇 주만 지나면 어떤 프로젝트가 토큰을 가장 많이 썼는지, 어떤 파일이 정리해도 되는지 알기 어렵죠.

**agent-session-manager**(`asm`)는 이 모든 걸 터미널 대시보드 하나에 모읍니다. 두 에이전트를 함께 보여주고, 키 하나(`s`)로 **All / Claude / Codex** 필터를 전환해 비용을 비교하거나 한쪽만 들여다볼 수 있습니다.

### 💡 왜 만들었나요

- **문제:** 서로 다른 두 코딩 에이전트의 비용·세션 데이터가 각각 불투명한 디렉토리에 흩어져, 함께 보는 화면이 없음
- **해결:** 둘 다 읽어 정확히 가격을 매기고, 휴지통·복구 스냅샷으로 안전하게 정리하는 TUI 하나

---

## 데모

통합 대시보드(두 에이전트 합산 비용, 소스 태그된 행) → 같은 화면을 **Claude** / **Codex**로 필터링:

<img src="docs/demo.gif" alt="asm 데모" width="820"/>

---

## ✨ 주요 기능

### 통합 대시보드
- **두 에이전트 합산 비용** + 인앱 소스 필터 — `s`로 All / Claude / Codex 전환
- 모델별 토큰·비용 (Opus / Sonnet / Haiku / GPT-5.x), 각 행을 소스 태그로 구분
- 일별 / 주별 / 월별 사용량 표, 프로젝트 비용 Top 10 차트
- LiteLLM 기반 단가 테이블로 정확한 최신 가격 (신규 Opus/GPT 모델도 옛 단가가 아닌 현재 단가로 계산)

### Claude 관리
- **프로젝트:** `.claude.json` 트리, 세션 대화 미리보기, 세션 삭제, 설정에서 프로젝트 제거
- **고아 정리:** 매칭 프로젝트가 없는 세션·파일히스토리·디버그·task 항목을 감지·일괄 정리
- **중복 세션:** 여러 프로젝트에 복사된 동일 세션을 찾아 개별 복사본 삭제
- **마이그레이션:** 프로젝트 간 세션 복사(원본 유지), 경로 자동 갱신

### Codex 세션
- `~/.codex` rollout 세션을 작업 디렉토리별로 조회
- 대화 미리보기, 개별 세션 삭제

### 기본이 안전
- 모든 삭제는 **OS 휴지통**으로, 감사 로그에 기록
- 삭제 전 **복구 스냅샷** 생성 (Claude·Codex 모두)
- 백업: Claude(config / settings / plugins / sessions / 전체), Codex(세션, 대용량 캐시 제외). 복원 시 자동 안전 백업 + 실패 롤백

---

## 작동 방식

```
   ~/.claude  ┐
              ├──►  asm  ──►  대시보드 하나  ──►  필터: All / Claude / Codex
   ~/.codex   ┘              (비용 · 세션 · 정리 · 백업)
```

`asm`은 두 데이터 디렉토리를 직접 읽습니다 — 데몬·설정 없음. Claude는 프로젝트별, Codex는 작업 디렉토리별로 묶고, 비용은 각 세션에 기록된 토큰 사용량으로 계산합니다.

| 경로 | 내용 |
|:---|:---|
| `~/.claude.json` · `~/.claude/projects/` | Claude 프로젝트·비용·세션 JSONL |
| `~/.claude/file-history/` · `debug/` · `tasks/` | 스냅샷·디버그 로그·세션별 task 목록 |
| `~/.codex/sessions/` | Codex rollout 세션 파일 |
| `~/.asm/backups/` · `trash-log.jsonl` | 백업(기존 `~/.cc-tui`에서 자동 이전)·삭제 감사 로그 |

---

## 🛠️ 기술 스택

- **TUI:** [Textual](https://github.com/Textualize/textual) + [Rich](https://github.com/Textualize/rich)
- **안전장치:** [send2trash](https://github.com/arsenetar/send2trash) (`rm`이 아닌 OS 휴지통)
- **세션:** [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) + JSONL 폴백 파서
- **Python:** 3.11+

---

## 🚀 시작하기

### 설치 (권장)

```bash
# uv
uv tool install agent-session-manager

# pip
pip install agent-session-manager
```

둘 다 단일 `asm` 명령을 설치합니다. 최초 실행 시 기존 `~/.cc-tui` 데이터가 `~/.asm`로 자동 이전됩니다.

<details>
<summary><strong>소스에서 실행</strong></summary>

```bash
git clone https://github.com/Bae-ChangHyun/agent-session-manager.git
cd agent-session-manager
uv sync && uv run asm
```

</details>

### 사용법

```bash
asm                       # 실행 — Claude + Codex 함께 표시
asm --source codex        # 대시보드를 Codex 필터로 시작
asm --path /your/project  # 특정 Claude 프로젝트만
asm --lang ko             # 한국어 UI  (또는 ASM_LANG=ko)
asm --no-update-check     # 시작 시 업데이트 확인 건너뛰기
```

두 소스는 항상 함께 다룹니다. `--source`는 대시보드 초기 필터만 정하며, 실행 중 `s`로 언제든 바꿉니다.

### 키보드

| 키 | 동작 |
|:---:|:---|
| `F1`~`F6` | 탭 전환 |
| `s` | 대시보드 소스 필터 (All / Claude / Codex) |
| `Tab` / `Shift+Tab` · `1` `2` `3` | 대시보드 기간 (Daily / Weekly / Monthly) |
| `d` / `D` | 선택 삭제 / 전체 고아 삭제 |
| `Space` · `Enter` | 선택 토글 · 대화 미리보기 |
| `r` · `q` | 전체 새로고침 · 종료 |

### 업데이트

PyPI에 새 버전이 있으면 `asm` 실행 시 `y/N` 업그레이드 프롬프트가 뜹니다(`uv tool` 또는 `pip`). 비대화형 셸·오프라인에서는 건너뜁니다.

---

## 🗺️ 로드맵

- [ ] Codex 세션 **복원**(현재는 백업/목록/삭제까지, 복원은 미구현)
- [ ] 데이터 개요에 소스별 디스크 사용량·보존 힌트 추가
- [ ] PyPI에 `agent-session-manager`로 배포

---

## ⚠️ 상태 & 범위

- **개인용 / 프리릴리스**, 활발히 개발 중.
- Claude Code·Codex 내부 데이터를 직접 다룹니다 — **대량 삭제 전 백업**하세요.
- 삭제는 OS 휴지통 + 복구 스냅샷으로 처리, 제자리 `rm` 없음.
- 무보증. Anthropic·OpenAI와 무관.

---

## 📄 라이선스

[MIT](LICENSE)

<div align="center">
<br/>
Made with <b>Claude Code</b> · and now <b>Codex</b> too
</div>
