# 스킬 적용 기준

역할은 책임을, 스킬은 특정 작업의 실행 방법을 정한다. 역할 이름만으로 스킬을 적용하지 않는다. 현재 세션의 **설치된 스킬 카탈로그**에서 실제 사용 가능 여부와 정확한 위치를 확인한 뒤 필요한 `SKILL.md`를 읽는다. 아래 표는 작성 당시의 연결 예시이며 허용 목록이 아니다. 표나 역할 TOML의 요약과 현재 스킬 본문의 적용 조건이 다르면 현재 스킬을 따른다. 버전별 파일 경로를 고정하거나 스킬을 외부에서 내려받아 적용하지 않는다. 전용 스킬이 없는 역할도 목표·자료·도구가 맞으면 수행할 수 있다.

| 설치된 스킬 이름 | 적용 조건과 중요한 경계 |
|---|---|
| `orchestrate` | 사용자가 전문가 팀, 하위 에이전트 배분 또는 병렬 협업을 요청했을 때. 단순 작업에는 팀을 만들 필요가 없다. |
| `openai-docs` | Codex·OpenAI 제품, 모델, API, 설정, 가격, 자동화 등의 현재 공식 정보가 필요할 때. 일반 앱 개발에 OpenAI가 언급됐다는 이유만으로 적용하지 않는다. |
| `skill-creator` | 재사용 가능한 Codex 스킬을 만들거나 갱신할 때. 일회성 문서 작성과 구분한다. |
| `skill-installer` | 큐레이션 목록 또는 저장소 경로에서 Codex 스킬 설치를 요청받았을 때. 역할 정의가 설치 권한을 주지는 않는다. |
| `plugin-creator` | 개인 Codex 플러그인 구조, 매니페스트 또는 마켓플레이스 항목을 만들거나 갱신할 때. |
| `plugin-management:plugin-management` | 플러그인 탐색·제안, 권한·의존성 확인, 연결 또는 제거 요청이 있을 때. 미설치 플러그인과 외부 계정 접근을 사용 가능한 것으로 가정하지 않는다. |
| `computer-use:computer-use` | 실제 연결된 Windows 앱 UI를 제어해야 할 때. 화면과 앱 접근이 제공된 범위에서만 수행한다. |
| `documents:documents` | DOCX·Word·Google Docs 대상 파일의 제작, 편집, 주석, 변경 표시 또는 렌더 품질 확인이 필요할 때. 배포 전 렌더를 확인한다. |
| `pdf:pdf` | PDF 읽기·생성·추출·양식 작성이나 페이지 렌더 품질 확인이 필요할 때. DOCX 원본 편집에는 문서 스킬을 사용한다. |
| `presentations:Presentations` | PowerPoint·Google Slides 발표 자료를 읽거나 만들거나 수정할 때. 발표 개요만 필요하면 파일 작업 범위를 먼저 확인한다. |
| `spreadsheets:Spreadsheets` | XLSX·XLS·CSV·TSV 파일이나 Google Sheets의 수식·서식·차트·재계산을 다룰 때. **열려 있는 Microsoft Excel 앱의 실시간 제어에는 사용하지 않는다.** |
| `spreadsheets:excel-live-control` | Microsoft Excel 앱 태그, Excel Desktop 또는 그 안의 열린/활성/연결된 통합문서·선택 범위, ChatGPT add-in for Excel을 명시한 요청, 기존 live 작업의 후속 편집에 적용한다. 연결과 설정은 해당 스킬의 절차를 따르며, 필수 기능이 없다고 로컬 파일 제작으로 임의 전환하지 않는다. 일반적인 새 XLSX·CSV 요청과 Google Sheets는 각각 파일·Sheets 경로를 따른다. |
| `template-creator:template-creator` | 참조 산출물에서 반복 사용 가능한 개인 아티팩트 템플릿 스킬을 만들거나 수정할 때. 기존 템플릿으로 일회성 산출물만 만드는 경우에는 적용하지 않는다. |
| `imagegen` | 사진·일러스트·질감·스프라이트·목업 등의 **비트맵** 이미지를 생성·편집할 때. 기존 SVG·아이콘 체계나 HTML/CSS/캔버스 그래픽 편집에는 적용하지 않는다. |
| `visualize:visualize` | 대화 안에서 개념 설명, 비교, 시나리오 탐색을 위한 인터랙티브 시각화가 도움이 될 때. **출판용 과학 그래프와 연구 그림은 표준 플로팅 도구로 별도 산출물**을 만든다. |
| `frontend-design` | 새 UI를 만들거나 기존 UI의 시각 방향을 크게 바꿀 때. 미적 방향과 타이포그래피 선택에 적용한다. |
| `web-design-guidelines` | 기존 UI 코드의 접근성, UX 또는 웹 인터페이스 지침 준수를 검토할 때. 시각 디자인 제작 자체와 구분한다. |
| `sites:sites-building` | 완성된 새 웹사이트 제작 또는 **기존 Site** 수정 요청에 적용한다. 다른 웹 저장소 개발에는 사용자가 Sites를 명시한 경우에 적용한다. 사이트 소유 에이전트가 체크아웃·Sites 도구·게시·인계를 수행하며 하위 에이전트에는 한정된 자산·조사만 위임한다. |
| `sites:sites-hosting` | Sites 제작·수정 뒤 게시 단계 또는 호스팅 관리 요청에 적용한다. 제작 스킬의 게시 흐름과 사용자의 로컬 작업·게시 제외·다른 제공자 지시를 따른다. |
| `sites:sites-preview-troubleshooting` | 관리형 Linux 프로필의 Sites 미리보기 세션이 실패했을 때만 적용한다. 휴대형 미리보기 문제에 일반화하지 않는다. |
| `vercel-composition-patterns` | React의 compound component, render prop, context 제공자 또는 재사용 API를 설계·리팩터링할 때. |
| `vercel-react-best-practices` | React/Next.js 컴포넌트, 데이터 가져오기, 번들 또는 성능 작업을 작성·검토할 때. |
| `supabase-postgres-best-practices` | Postgres 스키마, SQL, 마이그레이션, RLS, 인덱스, 함수, 큐, 복구·적재 또는 성능·잠금 문제를 다룰 **때 먼저** 적용한다. Supabase 외 Postgres에도 적용한다. |
| `systematic-debugging` | 버그, 테스트 실패 또는 예상치 못한 동작을 만났을 때 수정 제안보다 먼저 원인을 조사한다. |
| `test-driven-development` | 기능이나 버그 수정을 구현할 때 코드 작성 전 테스트 중심 절차를 확인한다. |
| `verification-before-completion` | 완료·수정·통과를 주장하거나 커밋·PR을 만들기 전 실제 검증 명령과 결과를 확인한다. |

스킬 지침과 사용자 요청이 충돌하면 사용자 지시가 우선한다. 스킬의 적용 조건에 맞더라도 연결된 도구, 계정, 샌드박스 권한이 실제로 제공되는지 별도로 확인한다. 파일 제작과 외부 게시·메시지 발송·계정 변경은 서로 다른 행동이며 역할이나 스킬을 읽은 사실만으로 후자의 권한이 생기지 않는다.
