# 역할 목록

역할은 과업의 책임과 산출물을 고르는 기준이다. 필요한 역할의 TOML만 읽는다. `developer_instructions`는 배정 때 전달할 역할 지침이다. `sandbox_mode`는 요청할 권한 조건이며 실행 도구가 이를 지원하는지 확인해야 한다. 이 TOML 파일을 둔다고 Codex의 네이티브 에이전트가 자동 등록되지는 않는다.

역할, 모델, 협업 위치(작성·검토·통합), 실제 도구 권한은 별도로 결정한다. 한 에이전트가 여러 역할을 겸할 수 있으며 간단한 작업에 불필요한 팀을 만들지 않는다. TOML의 협업 상대는 해당 팀에서 필요한 경우의 연결 예시이며 모두 생성하라는 뜻이 아니다. 작업에 맞는 스킬과 위임 범위는 [스킬 적용 기준](skill-routing.md)에서 확인한다.

## 총괄·조사·의사결정

| 역할 | 책임과 대표 산출물 |
|---|---|
| [`orchestrator`](roles/orchestrator.toml) | 목표·의존성·전문가 배정을 조정하고 통합 결과와 검증을 보고한다. |
| [`researcher`](roles/researcher.toml) | 공식·원자료를 조사하고 출처, 불확실성과 답을 정리한다. |
| [`evidence_reviewer`](roles/evidence-reviewer.toml) | 비코드 산출물의 주장·수치·인용을 독립 확인한 검증표를 만든다. |
| [`business_analyst`](roles/business-analyst.toml) | 업무 현황, 대안, 비용·효과와 사업 가정을 분석한 의사결정 자료를 만든다. |
| [`user_insights_analyst`](roles/user-insights-analyst.toml) | 제공된 사용자 자료에서 과업과 문제를 추출한 근거 매트릭스를 만든다. |
| [`operations_designer`](roles/operations-designer.toml) | 업무 분석을 담당자·예외·인계가 명확한 SOP와 체크리스트로 바꾼다. |
| [`financial_modeler`](roles/financial-modeler.toml) | 비용·매출·현금흐름의 가정과 민감도를 담은 시나리오 모델을 만든다. |
| [`product_manager`](roles/product-manager.toml) | 사용자 요구를 범위, 우선순위, 사용자 스토리와 수용 조건으로 정리한다. |

## 콘텐츠·교육·시각물

| 역할 | 책임과 대표 산출물 |
|---|---|
| [`content_strategist`](roles/content-strategist.toml) | 대상 독자, 메시지, 채널과 홍보 문안을 기획한다. |
| [`creative_writer`](roles/creative-writer.toml) | 서사·대본·에세이 등 창작 원고와 개정본을 작성한다. |
| [`localization_editor`](roles/localization-editor.toml) | 지정 언어권에 맞는 문안, 용어집과 변경 이유를 만든다. |
| [`learning_designer`](roles/learning-designer.toml) | 학습 목표, 강의안, 실습과 평가 문항을 설계한다. |
| [`technical_writer`](roles/technical-writer.toml) | 실제 동작에 맞는 README, API 문서와 사용 안내를 작성한다. |
| [`presentation_designer`](roles/presentation-designer.toml) | 발표 흐름과 슬라이드 구조를 설계하고 프레젠테이션 산출물을 만든다. |
| [`visual_creator`](roles/visual-creator.toml) | 사진·일러스트·목업 등 비트맵 이미지 자산을 제작한다. |

## 문서·데이터 산출물

| 역할 | 책임과 대표 산출물 |
|---|---|
| [`data_analyst`](roles/data-analyst.toml) | 데이터를 정리하고 지표·시각화·분석 보고서를 만든다. |
| [`document_producer`](roles/document-producer.toml) | DOCX를 제작·편집하고 렌더 품질을 확인한다. |
| [`spreadsheet_modeler`](roles/spreadsheet-modeler.toml) | 스프레드시트의 수식·재계산·서식을 검증한 파일을 만든다. |
| [`pdf_specialist`](roles/pdf-specialist.toml) | PDF 추출·생성·양식 필드와 렌더 품질을 확인한다. |
| [`template_author`](roles/template-author.toml) | 반복 사용 가능한 아티팩트 템플릿 스킬과 사용 예시를 만든다. |

## 제품·웹·인터페이스

| 역할 | 책임과 대표 산출물 |
|---|---|
| [`ux_designer`](roles/ux-designer.toml) | 정보 구조, 사용자 흐름과 화면 명세를 설계한다. |
| [`accessibility_auditor`](roles/accessibility-auditor.toml) | 기존 웹 UI의 접근성·인터페이스 문제를 재현 조건과 함께 검토한다. |
| [`sites_builder`](roles/sites-builder.toml) | 사이트 소유 에이전트가 맡는 역할. Sites 제작·수정·게시를 수행하며 하위 작업은 자산·조사로 제한한다. |
| [`architect`](roles/architect.toml) | 소프트웨어·업무 시스템의 구조, 입출력 계약, 의존성과 통합 순서를 설계한다. |
| [`frontend_developer`](roles/frontend-developer.toml) | 일반 웹 프로젝트의 화면·상태·상호작용을 구현한다. |
| [`backend_developer`](roles/backend-developer.toml) | API, 서버 로직, 인증·인가와 데이터 흐름을 구현한다. |
| [`database_engineer`](roles/database-engineer.toml) | 스키마, SQL, 인덱스, 무결성과 마이그레이션을 설계·구현한다. |

## 구현·운영·Codex 확장

| 역할 | 책임과 대표 산출물 |
|---|---|
| [`automation_engineer`](roles/automation-engineer.toml) | 반복 작업 스크립트와 도구 연동을 구현한다. |
| [`app_operator`](roles/app-operator.toml) | 실제 허용된 앱에서 일회성 UI 작업을 수행하고 상태를 확인한다. |
| [`devops_engineer`](roles/devops-engineer.toml) | 빌드·배포 설정, CI/CD와 운영 관측을 다룬다. |
| [`performance_engineer`](roles/performance-engineer.toml) | 응답 시간, 메모리, 렌더링과 처리량 병목을 분석한다. |
| [`openai_solution_designer`](roles/openai-solution-designer.toml) | 공식 문서에 근거해 OpenAI·Codex 기능 선택과 통합 명세를 만든다. |
| [`skill_author`](roles/skill-author.toml) | Codex 스킬의 트리거·지침·지원 리소스를 설계하고 검증한다. |
| [`plugin_developer`](roles/plugin-developer.toml) | Codex 플러그인 구조, 매니페스트와 설치 절차를 만든다. |

## 독립 검토

| 역할 | 책임과 대표 산출물 |
|---|---|
| [`qa_engineer`](roles/qa-engineer.toml) | 사용자 시나리오, 테스트와 회귀 검증 결과를 만든다. |
| [`reviewer`](roles/reviewer.toml) | 코드 변경의 버그, 회귀와 빠진 테스트를 독립 검토한다. |
| [`security_reviewer`](roles/security-reviewer.toml) | 인증·인가, 입력, 비밀정보와 의존성 위험을 검토한다. |

## 과업에 맞춘 역할 구성

카탈로그에 맞는 역할이 없어도 이름을 억지로 고르지 않는다. 일회성 과업에는 목표, 전문 범위, 산출물, 검증 기준과 동료에게 넘길 입력·결과를 적은 **임시 런타임 역할**을 배정할 수 있다. 반복될 역할이면 기존 역할과의 경계를 확인한 뒤 TOML과 이 목록을 갱신해 **재사용 영속 역할**로 만든다. 어느 경우든 실제 도구와 계정 권한은 별도이며 역할 이름이 이를 부여하지 않는다.
