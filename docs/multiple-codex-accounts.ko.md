# Codex 계정이 여러 개일 때

Codex는 **로그인마다 홈 디렉터리를 하나씩** 쓴다. 두 번째 계정으로 로그인하면 그
세션은 `~/.codex`에 없고 별도 홈(보통 `~/.codex-<라벨>`)에 쌓인다:

```
~/.codex          25,739 rollouts   계정 A
~/.codex-hermes       23 rollouts   계정 B
```

일반적인 상황은 아니라서 asm은 기본적으로 홈이 하나라고 본다. 아래는 여러 개를
쓰는 경우에만 필요한 설정이다.

## asm이 홈을 정하는 순서

먼저 걸리는 것이 이긴다:

| 순서 | 방법 | 용도 |
| --- | --- | --- |
| 1 | `--codex-home PATH` (반복 지정 가능) | 일회성 실행, 스크립트, 어떤 경로든 |
| 2 | `ASM_CODEX_HOMES` (`os.pathsep` 구분) | 셸 rc에 넣는 영구 설정 |
| 3 | `CODEX_HOME`(없으면 `~/.codex`) **+** `sessions/`를 가진 형제 `~/.codex-*` | 흔한 배치, 설정 불필요 |

3번은 흔한 작명 패턴에 대한 편의일 뿐이다. 홈이 `~/work/.codex`, `/opt/codex-ci`
처럼 다른 곳에 있으면 1번이나 2번으로 직접 지정한다. 그 패턴을 넘어서 추측하지
않는다.

```bash
# 일회성
asm --codex-home ~/work/.codex --codex-home /opt/codex-ci import list --to claude

# 영구 (~/.zshrc)
export ASM_CODEX_HOMES="$HOME/.codex:$HOME/work/.codex"
```

## 실제로 어디를 훑는지 확인

```console
$ asm import homes
Codex homes scanned (--codex-home / ASM_CODEX_HOMES override this):
   /home/you/.codex  25739 sessions
   /home/you/.codex-work  23 sessions
```

없는 경로는 조용히 넘어가지 않고 `(missing)`으로 표시된다. `ASM_CODEX_HOMES`에
오타가 나면 바로 눈에 띈다.

## 모든 홈을 함께 보는 기능

- 세션 목록·검색·미리보기
- 대시보드 합계와 비용/토큰 집계 (usage ledger가 모든 홈을 수집)
- `asm import session <id>` — 모든 홈에서 id를 찾고, 출처 홈을 함께 표시한다:
  `codex -> claude: 139 turns  cwd=/home/you/notes  [.codex-hermes]`
- `asm import list` — 홈을 합쳐 마지막 활동 순으로 정렬
- 세션 삭제와 복구 스냅샷 복원

## 아직 기본 홈만 보는 기능

다음은 **기본 홈**(`CODEX_HOME`, 없으면 `~/.codex`)만 읽는다:

- `asm backup create --type codex` — 두 번째 홈을 백업하려면 그 실행에만
  `CODEX_HOME`을 그 홈으로 지정한다
- MCP 서버 가져오기(`asm import mcp`) — 그 홈의 `config.toml`을 읽는다
- Claude → Codex 중복 방지에 쓰는 import 원장
  (`external_agent_session_imports.json`)

지금 이 기능들을 계정별로 쓰려면 `CODEX_HOME=~/.codex-<라벨>`을 붙여 실행한다.
