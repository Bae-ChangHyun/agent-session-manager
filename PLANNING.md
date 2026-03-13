# CC-TUI 개발 기획 문서

> Claude Code 세션 데이터 관리를 위한 터미널 UI 도구의 개발 여정 기록

---

## 1. 프로젝트 동기와 배경

### 문제 인식

Claude Code를 일상적으로 사용하다 보면 `~/.claude/` 디렉토리에 데이터가 조용히 쌓인다. 세션 대화 파일(`.jsonl`), 파일 히스토리 스냅샷, 디버그 로그, 내부 Todo 메모 등이 그것이다. 문제는 이 데이터들이 **가시성 없이** 쌓인다는 점이다.

- 어떤 프로젝트가 얼마나 비용을 썼는지 알 수 없다
- 프로젝트를 이동하거나 삭제하면 연관 데이터가 "orphan" 상태로 남는다
- 세션 수백 개가 쌓여도 어느 세션이 무슨 작업이었는지 한눈에 보이지 않는다
- 특히 laptop을 옮기거나 프로젝트 경로가 바뀌면 세션 데이터를 새 경로로 이전할 방법이 없다

Claude Code의 내부 데이터 구조는 경로를 인코딩한 디렉토리명(`-home-bch-Project-...` 형태)을 사용한다. 사람이 직접 관리하기 어려운 구조다.

### 해결 방향

터미널에서 바로 실행할 수 있는 TUI(Terminal User Interface) 도구를 만들기로 했다. GUI 앱이 아닌 TUI를 선택한 이유는 간단하다. Claude Code 자체가 터미널 도구이고, 그 데이터를 관리하는 도구도 같은 컨텍스트에서 동작해야 자연스럽다.

---

## 2. 기술 스택 선택

### 왜 Textual인가

Python TUI 라이브러리 중 Textual을 선택한 결정적인 이유는 세 가지다.

**1. 컴포넌트 기반 UI 모델**
Textual은 React와 유사한 컴포넌트 모델을 제공한다. `Widget` 단위로 UI를 구성하고, CSS로 스타일을 별도 관리할 수 있다. 복잡한 탭 레이아웃, 트리 뷰, 테이블, 모달 다이얼로그를 조합하는 이 프로젝트에 적합했다.

**2. 비동기 워커 지원**
데이터 로딩이 UI를 블로킹해선 안 된다. `run_worker(thread=True)`와 `call_from_thread()`를 통해 백그라운드 스레드에서 파일시스템/SDK 작업을 수행하고 결과를 UI 스레드로 안전하게 전달하는 패턴을 제공한다.

**3. Rich 마크업 통합**
Textual은 Rich 라이브러리를 기반으로 한다. `[bold]`, `[green]`, `[yellow]` 등의 Rich 마크업을 `Static` 위젯에 직접 쓸 수 있어 별도 위젯 없이도 시각적으로 풍부한 인터페이스를 만들 수 있다.

### 핵심 의존성

| 라이브러리 | 역할 |
|-----------|------|
| `textual >= 1.0.0` | TUI 프레임워크 |
| `send2trash >= 1.8.0` | 안전한 파일 삭제 (휴지통으로 이동) |
| `claude-agent-sdk` | Claude 세션 메타데이터 조회 |

`send2trash`를 선택한 이유는 중요하다. 세션 데이터를 실수로 영구 삭제하면 복구가 불가능하다. `os.remove()`나 `shutil.rmtree()` 대신 OS 휴지통으로 이동하는 방식을 선택해서 안전망을 확보했다.

---

## 3. 아키텍처

### 디렉토리 구조

```
src/cc_tui/
├── __main__.py          # 진입점, CLI 인자 파싱
├── app.py               # CCTuiApp: 탭 레이아웃, 전역 키바인딩
├── models.py            # 데이터 모델, 경로 상수, 인코딩 유틸
├── i18n.py              # 국제화 (한국어/영어)
├── screens/             # UI 화면(탭) 모음
│   ├── dashboard.py     # 대시보드: 비용/사용량 통계
│   ├── projects.py      # 프로젝트 트리 + 세션 관리
│   ├── sessions.py      # 전체 세션 목록 (시간순)
│   ├── file_history.py  # 파일 히스토리 관리
│   ├── debug_todos.py   # 디버그/Todo 파일 관리
│   ├── migrate.py       # 세션 마이그레이션
│   ├── backups.py       # 백업/복원
│   ├── orphaned.py      # Orphan 데이터 관리
│   └── confirm.py       # 확인 모달 다이얼로그
└── services/            # 비즈니스 로직 레이어
    ├── claude_data.py   # 데이터 읽기 (SDK + JSONL fallback)
    ├── cleaner.py       # 파일 삭제 (send2trash 래퍼)
    ├── backup.py        # 백업/복원
    └── migrate.py       # 세션 마이그레이션 로직
```

### 레이어 분리 원칙

UI 레이어(`screens/`)와 데이터 레이어(`services/`)를 명확히 분리했다. `screens/`는 Textual 위젯만 다루고, 실제 파일시스템 접근과 데이터 처리는 모두 `services/`에서 담당한다. 이 구조 덕분에 UI 변경이 로직에 영향을 주지 않고, 서비스 로직을 독립적으로 테스트할 수 있다.

### Claude 데이터 구조 이해

Claude Code는 프로젝트 경로를 다음 규칙으로 인코딩해서 디렉토리명으로 사용한다.

```
/home/bch/Project/my-app
  → -home-bch-Project-my-app
```

구체적으로는 알파벳/숫자 이외의 문자를 모두 `-`로 치환한다. `models.py`의 `encode_path()`가 이 로직을 구현한다.

이 인코딩은 단방향이다. `-home-bch-Project-my-app`을 다시 `/home/bch/Project/my-app`으로 완벽하게 복원할 수 없다 (원래 문자가 `/`인지 `-`인지 알 수 없다). 따라서 `decode_path_hint()`는 "힌트" 수준의 표시용 디코딩만 제공한다.

### SDK + JSONL Fallback 패턴

세션 데이터 조회는 두 경로로 구현했다.

```python
def get_session_details(project_dir):
    try:
        return _get_sessions_via_sdk(project_dir)  # 우선
    except Exception:
        return _get_sessions_via_jsonl(project_dir)  # fallback
```

`claude-agent-sdk`가 설치되어 있고 동작하면 SDK를 사용하고, 실패하면 `.jsonl` 파일을 직접 파싱한다. SDK 의존성이 미래에 깨질 경우에도 동작을 보장하는 방어적 설계다.

---

## 4. 주요 기술적 결정사항

### 4.1 Rich markup 기반 액션바

Textual에서 클릭 가능한 버튼을 여러 개 나란히 배치하려면 `Button` 위젯을 여러 개 쓰거나 `Horizontal` 컨테이너를 쓰는 것이 일반적이다. 하지만 이 프로젝트는 다른 방식을 선택했다.

`Static` 위젯 하나에 Rich 마크업으로 색깔 있는 버튼처럼 보이는 텍스트를 렌더링하고, 클릭 이벤트의 `x` 좌표를 사전에 계산해둔 클릭 맵과 대조해서 어떤 "버튼"이 눌렸는지 판단한다.

```python
def _build_action_bar(self, actions):
    parts = []
    click_map = []
    x = 0
    for action_id, label, color in actions:
        text = f" {label} "
        width = cell_len(text)          # Rich cell 너비 계산
        click_map.append((x, x + width, action_id))
        parts.append(f"[bold white on {color}]{text}[/]")
        x += width
    return "  ".join(parts), click_map
```

이 방식을 선택한 이유는 레이아웃 유연성이다. 표시할 버튼 수와 라벨이 동적으로 변한다 (예: orphan이 없으면 "Orphan 전체 삭제" 버튼이 사라진다). 위젯 수가 동적으로 변하는 것보다 텍스트를 동적으로 생성하는 것이 Textual에서 훨씬 간단하다.

### 4.2 Orphan 감지 로직

"Orphan"은 `.claude.json`에 등록된 프로젝트와 매칭되지 않는 데이터를 의미한다. 이 감지는 두 가지 방향으로 구현된다.

**세션 디렉토리 orphan 감지**: `~/.claude/projects/` 아래 각 디렉토리명을 `.claude.json`의 프로젝트 경로 인코딩 결과와 대조한다.

```python
for pp in project_paths:
    if encode_path(pp) == actual_path:
        is_orphaned = False
        break
```

**파일 히스토리/디버그/Todo orphan 감지**: 파일명에서 session ID를 추출하고, 현재 존재하는 모든 세션 ID 집합과 대조한다.

```python
def _get_active_session_ids() -> set[str]:
    ids = set()
    for d in PROJECTS_DIR.iterdir():
        for jsonl in d.glob("*.jsonl"):
            ids.add(jsonl.stem)
    return ids
```

Todo 파일명은 `{UUID}-agent-{UUID}.json` 형태라 앞부분 UUID만 추출해서 세션 ID로 사용한다.

### 4.3 프로젝트 트리 경로 압축

프로젝트가 `/home/bch/Project/backend/api` 처럼 깊은 경로에 있을 때, 중간 경로 노드를 하나씩 다 펼치면 트리가 너무 깊어진다. 자식이 하나뿐인 중간 디렉토리는 자동으로 압축해서 `home/bch/Project/backend` 를 하나의 노드로 표시한다.

```python
elif len(child_dirs) == 1 and not is_project:
    # Single child dir - collapse into parent label
    collapsed_label = f"{key}/{child_key}"
    while 단일_자식_체인이_계속되면:
        collapsed_label = f"{collapsed_label}/{next_key}"
```

### 4.4 비동기 데이터 로딩

대시보드의 일별/주별/월별 사용량 데이터는 수백 개의 JSONL 파일을 파싱해야 한다. 이 작업을 메인 스레드에서 하면 UI가 멈춘다.

구현 전략:
1. 앱 시작 시 일별(daily) 데이터를 먼저 로드해서 즉시 표시
2. 주별(weekly)/월별(monthly) 데이터는 백그라운드 워커로 추가 로드
3. 로드 완료 시 `call_from_thread()`로 UI 업데이트
4. 한번 로드한 데이터는 `_cached_periods` 딕셔너리에 캐시

```python
def _load(self) -> None:
    daily = get_period_usage("daily")
    self.app.call_from_thread(self._on_data_loaded, stats, usage, {"daily": daily})
    # 백그라운드에서 추가 로드
    for key in ("weekly", "monthly"):
        data = get_period_usage(key)
        self.app.call_from_thread(self._on_bg_period_loaded, key, data)
```

### 4.5 세션 마이그레이션 경로 재작성

프로젝트를 `A` 경로에서 `B` 경로로 이전할 때, 세션 파일 내부에 기록된 `cwd` 경로도 함께 업데이트해야 한다. `migrate.py`의 `_update_paths()`가 복사된 JSONL 파일의 텍스트를 치환하는 방식으로 이를 처리한다.

---

## 5. 구현된 기능 상세

### 탭 1: 대시보드 (Dashboard)

Claude Code 사용 현황을 한눈에 파악하는 화면이다.

**표시 정보:**
- 최초 사용일, 총 시작 횟수, 총 세션 수
- 모델별 누적 비용 및 토큰 사용량 (claude-sonnet, claude-haiku 등)
- 일별/주별/월별 사용량 집계 테이블 (클릭으로 전환)
- 비용 상위 10개 프로젝트 (막대 그래프 형식)
- 데이터 개요: 프로젝트 수, 세션 수, orphan 수, 디스크 사용량

**데이터 소스:**
- `~/.claude.json`: 프로젝트별 lastCost, lastModelUsage
- `~/.claude/history.jsonl`: 세션 시작 이력
- `~/.claude/projects/**/*.jsonl`: 어시스턴트 메시지의 usage 필드 파싱

비용 집계는 Claude 공개 요금표 기준으로 직접 계산한다 (Sonnet: input $3/1M, output $15/1M 등).

### 탭 2: 프로젝트 (Projects)

`.claude.json`에 등록된 모든 프로젝트를 계층적 트리로 표시하는 화면이다.

**주요 기능:**
- 프로젝트 경로를 파일시스템 구조 그대로 트리로 표시
- 각 프로젝트 옆에 [O]=폴더 존재, [X]=폴더 없음(삭제/이동됨) 표시
- 프로젝트를 펼치면 세션 목록이 최신순으로 표시
- 세션 선택 시 우측 패널에 대화 내용 미리보기
- 세션 개별 삭제 (휴지통으로 이동)
- 세션 없는 프로젝트를 `.claude.json` 목록에서 제거
- Orphan 세션 디렉토리 일괄 삭제 액션바

**설계 포인트:** 세션 목록은 프로젝트 노드를 펼칠 때 lazy하게 로드한다. placeholder 노드를 먼저 추가해두고, 실제 데이터가 로드되면 교체하는 방식이다.

### 탭 3: 파일 히스토리 (File History)

`~/.claude/file-history/`에 저장된 파일 버전 스냅샷을 관리하는 화면이다.

Claude Code가 파일을 수정하기 전에 원본을 이 디렉토리에 저장한다. "파일 되돌리기" 기능의 백엔드다. 오래된 스냅샷은 정리해도 안전하지만, 활성 프로젝트에 연결된 것은 삭제 시 롤백이 불가능해진다.

**표시 방식:** orphan 항목을 상단에 강조 표시하고, 항목 선택 시 어느 프로젝트/세션에 연결된 것인지 상세 정보를 우측 패널에 표시한다.

### 탭 4: 디버그/Todos (Debug/Todos)

`~/.claude/debug/`와 `~/.claude/todos/`의 내부 파일들을 관리하는 화면이다.

이 파일들은 Claude Code가 내부적으로 생성하는 것으로, 사용자의 Todo가 아니다.

- **Debug 파일**: Claude Code 오류 발생 시 생성되는 내부 로그. 버그 리포트 외에는 불필요하다.
- **Todo 파일**: Claude가 세션 중 내부 작업 추적용으로 생성하는 메모. 세션 종료 후 불필요하다.

**추가 기능:**
- 빈 파일 감지 및 일괄 정리 (`[]`, `{}`, 빈 문자열)
- 선택 항목의 파일 내용 우측 패널에서 미리보기
- 항목을 프로젝트별로 그룹화해서 표시

### 탭 5: 마이그레이션 (Migrate)

프로젝트 A의 세션 데이터를 프로젝트 B로 복사하는 기능이다.

**사용 사례:** 프로젝트를 다른 경로로 이전했을 때, 기존 경로의 세션들을 새 경로로 옮기고 싶은 경우.

**UI 설계:** 좌우 두 패널로 구성되어 있다. 왼쪽에서 소스 프로젝트를, 오른쪽에서 대상 프로젝트를 선택한다. 소스 선택 시 하단에 세션 미리보기가 표시된다.

**동작 모드:**
- **Append**: 기존 세션을 유지하고 새 세션만 추가 (중복 스킵)
- **Overwrite**: 기존 세션을 모두 삭제하고 소스 세션으로 교체

세션 파일 복사 후 내부에 기록된 경로 문자열도 자동으로 업데이트한다.

### 탭 6: 백업 (Backups)

`~/.cc-tui/backups/`에 백업을 생성하고 복원하는 기능이다.

**백업 종류:**
- **설정 백업**: `.claude.json`만 복사 (빠르고 가벼움)
- **전체 백업**: `.claude/` 디렉토리 전체와 `.claude.json`을 통째로 복사

세션 데이터 삭제나 마이그레이션 전에 미리 백업을 생성해두면 실수해도 복구할 수 있다. 복원 시에는 현재 설정을 먼저 자동 백업한 뒤 복원을 진행해서 복원 작업 자체도 되돌릴 수 있게 했다.

### 공통: 확인 모달 (ConfirmScreen)

모든 삭제/수정 작업은 `ConfirmScreen` 모달을 통해 확인을 거친다. `ModalScreen[bool]`을 상속해서 타입 안전한 결과 반환을 구현했다.

### 국제화 (i18n)

모든 UI 문자열을 `i18n.py`의 `TRANSLATIONS` 딕셔너리에서 관리한다. `--lang ko` CLI 옵션 또는 `CC_TUI_LANG=ko` 환경변수로 한국어로 전환할 수 있다.

```bash
cc-tui --lang ko
# 또는
CC_TUI_LANG=ko cc-tui
```

---

## 6. Claude Code 데이터 구조 참고

cc-tui가 다루는 경로들:

```
~/.claude.json                  # 프로젝트 목록, 비용, 모델 사용량
~/.claude/
├── projects/                   # 세션 데이터
│   └── -home-bch-Project-app/  # 경로 인코딩된 디렉토리
│       ├── {session-uuid}.jsonl  # 대화 기록
│       ├── sessions-index.json   # 세션 인덱스
│       └── memory/             # 프로젝트 메모리
├── file-history/               # 파일 버전 스냅샷
├── debug/                      # 내부 디버그 로그
├── todos/                      # 내부 Todo 메모
├── session-env/                # 세션 환경 변수
└── history.jsonl               # 세션 시작 이력
~/.cc-tui/backups/              # cc-tui 백업 저장소
```

---

## 7. 앞으로의 계획 (로드맵)

### 단기 (v0.2)

- **세션 검색**: 대화 내용 키워드 검색
- **비용 알림**: 일/월 사용량이 임계값 초과 시 알림
- **설정 파일**: YAML/TOML 기반 사용자 설정 (알림 임계값, 기본 언어 등)
- **Sessions 탭 완성**: 현재 `sessions.py`가 구현되어 있으나 앱에 아직 탭으로 노출되지 않음

### 중기 (v0.3)

- **자동 정리 규칙**: "30일 이상 된 orphan 자동 정리" 같은 규칙 설정
- **사용량 내보내기**: CSV/JSON으로 사용량 데이터 내보내기
- **세션 태그/메모**: 세션에 사용자 정의 태그 붙이기
- **디스크 사용량 분석**: 어느 프로젝트가 공간을 많이 차지하는지 시각화

### 장기 (v1.0)

- **패키지 배포**: PyPI에 `cc-tui` 패키지 배포
- **다중 Claude 인스턴스 지원**: 팀 내 여러 사용자의 데이터 통합 뷰
- **MCP 서버 관리**: 프로젝트별 MCP 서버 설정 시각화 및 관리

---

## 8. 개발 시 트레이드오프

### 버튼 vs 텍스트 액션바

Textual `Button` 위젯을 쓰면 접근성과 포커스 관리가 자동으로 된다. 하지만 동적 개수의 버튼을 수평 배치하고 조건부로 표시/숨기는 것은 위젯 추가/제거가 필요해서 복잡해진다. Rich 마크업 기반 클릭 맵은 단순하지만 키보드 접근성이 없다는 단점이 있다. 현재는 마우스 클릭 중심 사용 패턴을 가정하고 후자를 선택했다.

### SDK 의존 vs 직접 파싱

`claude-agent-sdk`가 편리하지만 Claude Code의 내부 API이므로 언제든 변경될 수 있다. JSONL 직접 파싱은 안정적이지만 SDK가 제공하는 메타데이터(summary, git_branch 등)를 얻기 어렵다. SDK 우선, JSONL fallback 구조가 현재로선 최선의 타협이다.

### 실시간 감시 vs 수동 새로고침

`watchdog` 같은 파일시스템 감시 라이브러리로 데이터 변경을 실시간 감지할 수 있다. 하지만 Claude Code가 세션을 진행하는 동안 계속 업데이트되는 파일을 실시간으로 읽으면 I/O 경합이 발생한다. `r` 키 수동 새로고침을 선택한 것은 이 때문이다.

---

*최초 작성: 2026-03-13*
