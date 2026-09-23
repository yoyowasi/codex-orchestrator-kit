# 여러 CLI 창으로 전문가 팀 실행하기

이 실행기는 팀마다 별도 Codex App Server와 로컬 MCP 연결을 만들고, 총괄과 작업자를 실제 Codex CLI 창으로 보여줍니다.

## 설치와 시작

Windows에서 Node.js 22 이상, Python 3.11 이상과 로그인된 Codex CLI가 필요합니다. 저장소 루트에서 실행합니다.

```powershell
py -3 scripts/install.py --with-cli
codex-team start C:\projects\my-app
```

기본 구성은 총괄, 프론트엔드, 백엔드, QA입니다. 총괄 창에 다음처럼 입력합니다.

```text
프론트엔드와 백엔드 담당자에게 각자 맡을 구조를 조사하게 해줘.
파일은 수정하지 말고 결과를 합쳐서 다음 구현 순서를 제안해줘.
```

연결을 확인한 뒤 원하는 개발을 요청합니다. 수정 작업에서는 총괄이 담당 경로를 나눕니다.

```text
사용자 프로필 수정 기능을 구현해줘.
필요한 설계를 먼저 확정하고 프론트엔드와 백엔드에 담당 파일을 배정해줘.
일반 구현은 Sol Medium, 복잡한 분석은 Astra High로 맡기고 QA 검증 후 통합해줘.
```

`codex_team` 도구 승인이나 명령 실행 승인이 필요하면 해당 창에서 선택합니다. 실행기는 승인을 대신 수락하지 않습니다.

## 명령

```powershell
codex-team start C:\projects\my-app --roles architect,frontend_developer,reviewer
codex-team start C:\projects\my-app --roles researcher,business_analyst,technical_writer
codex-team roles
codex-team status
codex-team open
codex-team stop
```

| 명령 | 의미 |
|---|---|
| `start PROJECT` | 새 팀을 만들고 창 열기 |
| `--roles a,b` | 작업자 1~6명 선택; 총괄은 자동 추가 |
| `roles` | Codex 홈에 등록된 역할 보기 |
| `status` | 가장 최근 팀의 작업자 상태·배정 모델·최근 결과 조회 |
| `open` | 가장 최근 팀의 창 다시 열기; 기존 창이 있으면 중복 창이 열릴 수 있음 |
| `stop` | 가장 최근 팀 서버 종료; 해당 팀의 진행 중인 작업도 중단 |

여러 팀을 사용한다면 `status`, `open`, `stop` 뒤에 시작할 때 출력된 `team.json`의 전체 경로를 붙여 대상을 지정합니다.

## 모델 배정

총괄은 Astra High, 작업자는 Sol Medium으로 시작합니다. 총괄은 작업마다 `team_dispatch`의 `model`과 `model_reason`을 지정합니다.

```json
{
  "role": "backend_developer",
  "task": "동시성 오류의 원인을 조사하고 재현 조건을 보고해 주세요.",
  "read_only": true,
  "model": "gpt-6-astra",
  "model_reason": "여러 요청 사이의 상태 변화를 분석해야 하는 작업"
}
```

같은 작업자의 다음 작업은 `gpt-6-sol`로 바꿀 수 있습니다. 추론 수준은 Astra `high`, Sol `medium`으로 설정됩니다. 실행 중인 작업에는 새 작업을 배정하지 않습니다. 새 모델 배정은 완료 또는 사용자가 승인한 중단 후에 가능합니다.

총괄 도구는 `team_members`, `team_dispatch`, `team_wait`, `team_result`, `team_interrupt`입니다. 이 연결 방식에서는 총괄이 이미 연결된 작업자에게 작업을 보내며, 별도 내장 하위 에이전트를 추가로 만들지 않습니다.

## 파일과 세션

역할은 `$CODEX_HOME/agents`, 팀 상태와 로그는 `$CODEX_HOME/teams`에 저장됩니다. `CODEX_HOME` 기본값은 `~/.codex`입니다. 이 실행기를 설치할 때 지정한 Codex 홈과 Python 인터프리터는 실행기에 기록됩니다.

작업자들은 프로젝트 폴더를 공유합니다. `owned_paths` 예약이 중복되면 진행 중인 배정을 거절합니다. 경로는 프로젝트 내부의 상대 파일·디렉터리이고 글로브나 프로젝트 루트 전체는 허용하지 않습니다. 공통 파일의 변경은 총괄이 조정합니다. 이 예약은 파일별 접근 제어를 대신하지 않습니다.

새 설치나 역할 업데이트는 새 팀부터 적용됩니다. 기존 팀은 생성 시 저장한 역할 지침을 유지하므로 진행 중인 작업을 마친 뒤 새 팀으로 시작합니다.

## 문제 해결

- **명령을 찾지 못함:** 설치기가 출력한 `codex-team.cmd`의 전체 경로로 실행합니다. 새 터미널에서 PATH도 확인합니다.
- **역할 없음:** `scripts/install.py`로 별칭을 설치했는지와 `--codex-home` 경로를 확인합니다.
- **모델 사용 불가:** Codex 모델 선택기에 Astra와 GPT-6 Sol이 제공되는지 확인합니다. 실행기는 다른 모델로 임의 대체하지 않습니다.
- **승인 대기:** 해당 Codex 창의 승인 요청을 확인합니다.
- **서버 연결 실패:** 해당 팀 디렉터리의 `server.log`를 확인합니다. 팀을 종료하면 재연결할 수 없으므로 새 팀을 시작합니다.

현재 여러 창 실행기는 Windows와 Codex CLI 0.156.0의 실험적 App Server WebSocket 인터페이스를 기준으로 합니다. macOS/Linux에서도 핵심 스킬은 설치할 수 있지만 이 실행기의 창 열기 기능은 지원하지 않습니다.
