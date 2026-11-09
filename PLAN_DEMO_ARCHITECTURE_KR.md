# `Gemini Enterprise` — `Agent Registry` + `Agent Gateway` + `Cloud/Model Armor` + `SDP` 기반 `Qwiklabs` 형 고객 `Demo Repository` 아키텍처 및 구축 계획서

| 문서 분류 구분 | 고객 제공용 `Hands-On Lab` & `Demo Repository` 아키텍처 설계 및 구축 계획서 | 문서 작성 일자 | 2026년 11월 9일 |
| :--- | :--- | :--- | :--- |
| **대상 `GitHub Repository`** | [`https://github.com/rhkim77/ge-agent-gateway-mcp`](https://github.com/rhkim77/ge-agent-gateway-mcp) | **적용 대상 범위** | 외부 클라우드(`AWS`) `Custom MCP Server`, `Agent Registry` (`us-central1`), `Egress Agent Gateway` (`us-central1`), `Google Cloud Armor`, `Model Armor`, `Sensitive Data Protection (SDP)`, `Gemini Enterprise` (`global`/`us`) |

---

## 1. 배경 및 아키텍처 목표 (`Executive Summary`)

엔터프라이즈 환경에서 `Gemini Enterprise (GE)`를 도입할 때, 기존 타 클라우드(`AWS`)나 온프레미스 사설망에 구축된 **`Custom MCP Server`**들을 안전하게 연결하고 전사 보안 거버넌스를 적용하기 위한 표준 아키텍처로 **`Agent Registry` + `Egress Agent Gateway`** 구성이 채택됩니다.

본 `Repository`([`https://github.com/rhkim77/ge-agent-gateway-mcp`](https://github.com/rhkim77/ge-agent-gateway-mcp))는 상용 인프라에 본구현을 착수하기 전, 고객사 아키텍트·보안팀·클라우드 엔지니어가 **`AWS`에 구성된 `MCP Server`를 `Agent Registry`에 등록하고, `Google Cloud Armor`·`Model Armor` 및 `Sensitive Data Protection (SDP)` 보안 정책이 적용된 환경에서 `Gemini Enterprise`를 직접 `Test`할 수 있는 `Qwiklabs` 형태의 핸즈온 환경**을 제공합니다.

### 1.1 핵심 구성 요소별 기술 검증 매트릭스 (`[확인됨 / Verified]`)

| 검증 영역 | 구현 목표 | 기술적 설계 및 제약사항(`Gotchas`) 해결 방안 | 공식 문서 근거 |
| :--- | :--- | :--- | :--- |
| **1. `Simulated AWS FastMCP Server` 및 실제 `AWS` 연동** | 별도 `AWS` 인프라 준비 없이도 즉시 실습 가능하며, 실제 `AWS MCP Server` URL로도 전환 가능하도록 구성 | • **`Simulated AWS VPC Mode` (기본값)**: `FastMCP` (`StreamableHTTP` & `JSON-RPC 2.0`) 기반의 엔터프라이즈 `MCP Server` 2종(`/inventory/mcp`, `/oms/mcp`)을 `Cloud Run` + `External ALB` + `Cloud Armor` 뒤편에 배포하여 가상 `AWS` 환경을 1:1 재현합니다.<br/>• **`External AWS URL Mode`**: `.env`의 `MCP_TARGET_MODE=external_aws_url` 변경만으로 고객의 실제 `AWS ALB / API Gateway` 엔드포인트에 즉시 연결됩니다. | [Set up VPC connectivity for custom MCP servers](https://cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-vpc-custom-mcp-server) |
| **2. `Agent Registry` (`us-central1`) 자산 등록** | `AWS MCP Server` 및 `Tool` 위험도 주석을 전사 카탈로그에 등록 | • `Gemini Enterprise` (`global`/`us`) 연동 규칙에 따라 **`us-central1` 단일 `Region`**에 `MCP Server` 2종(`cymbal-store-inventory-mcp`, `cymbal-oms-order-mcp`)과 `ALL_TRAFFIC` 필수 `googleapis` 통합 서비스를 등록합니다.<br/>• 각 `ToolSpec JSON`(`10 KB` 미만)에 `readOnlyHint`와 `destructiveHint`(`cancel_all_store_orders: true`) 주석을 부여합니다. | [Import and govern MCP servers with Agent Registry](https://cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/import-govern-mcp-server-agent-registry) |
| **3. `1-Step Egress Agent Gateway` & `ACT`** | 불변성(`Immutability`) 원칙을 준수한 사설/통제형 `Egress` 게이트웨이 구축 | • `Agent Gateway`의 `agentConnectivityTemplate`(`ACT`) 바인딩은 **최초 생성 시점 불변(`Immutable at creation`)**이므로, `PSC-I Subnet(/26)` ➔ `Cloud NAT`(`ENDPOINT_TYPE_VM,ENDPOINT_TYPE_SWG` + 고정 `/32 IP`) ➔ `PSC Network Attachment` ➔ `Cloud DNS Private Zone` ➔ `ACT`(`ALL_TRAFFIC`)를 선행 생성한 뒤 **`1-Step`으로 `Egress Agent Gateway`를 통합 생성**합니다. | [Configure VPC connectivity for Agent Gateway](https://cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/set-up-vpc-connectivity) |
| **4. `Cloud Armor` + `Model Armor` + `SDP` + `IAP` 다중 보안** | 네트워크 WAF, 도구 호출 인가, 입출력 AI 가드레일 및 개인정보 보호 정책 동시 검증 | • **`Google Cloud Armor`**: `Agent Gateway`의 `Cloud NAT` 고정 `/32 IP`만 허용하고 우회 접근을 `HTTP 403`으로 차단.<br/>• **`IAP Request Authz` (`V1` / `UAP V2`)**: `destructiveHint == true` 도구 호출을 `HTTP 403`으로 중앙 차단.<br/>• **`Model Armor`**: `locations/us`(`GE Assistant`) 및 `locations/us-central1`(`Agent Gateway` 인라인 `CONTENT_AUTHZ`)에서 간접 프롬프트 인젝션 차단.<br/>• **`SDP Content Policy`**: `KOREA_RRN`, `CREDIT_CARD_NUMBER`(`Luhn Checksum`) 탐지/차단 및 `BigQuery` 감사 로깅. | [Enable Model Armor in Gemini Enterprise](https://cloud.google.com/gemini/enterprise/docs/enable-model-armor)<br/>[Protect sensitive data in sources](https://cloud.google.com/gemini/enterprise/docs/protect-sensitive-data) |

---

## 2. 6단계 핸즈온 실습 및 5대 보안 검증 시나리오 (`Curriculum & Scenarios`)

| 단계 | 실습 제목 (`Task Title`) | 실행 명령어 (`Make Target`) | 핵심 검증 시나리오 |
| :---: | :--- | :--- | :--- |
| **Task 1** | `Simulated AWS FastMCP Server` 및 `Cloud Armor` `Edge WAF` 배포 | `make task1-deploy-mcp` | `Simulated AWS FastMCP` 컨테이너(`/inventory/mcp`, `/oms/mcp`) 배포 및 `Cloud Armor` 정책 생성 |
| **Task 2** | `Agent Registry` (`us-central1`)에 `AWS MCP Server` 및 `ToolSpec` 등록 | `make task2-register-mcp` | `cymbal-store-inventory-mcp`, `cymbal-oms-order-mcp`, `googleapis` 등록 및 `destructiveHint=true` 감사 |
| **Task 3** | `PSC Network Attachment`, `ACT` 및 `1-Step Egress Agent Gateway` 구축 | `make task3-provision-gateway` | `PSC-I Subnet(/26)`, 고정 `Cloud NAT IP`, `PSC Attachment`, `ACT`(`ALL_TRAFFIC`), `1-Step Agent Gateway` 생성 |
| **Task 4 & 5** | `Cloud Armor` IP 잠금, `IAP` 인가 정책, `Model Armor` & `SDP` 바인딩 | `make task4-bind-security` | `Cloud Armor` 고정 IP 허용 규칙 갱신, `IAP` 위험 도구 차단, `Model Armor` 및 `SDP ContentPolicy` 바인딩 |
| **Task 6A** | `Gemini Enterprise` 연동 및 5대 엔터프라이즈 보안 시나리오 실행 | `make task5-test-scenarios` | ① 정상 재고 조회(`200`) ② 비인가 IP 직접 호출(`Cloud Armor 403`) ③ 전체 발주 취소(`IAP 403`) ④ 간접 프롬프트 인젝션(`Model Armor Block`) ⑤ VIP 클레임 개인정보(`SDP Block/Log`) |
| **Task 6B** | `BigQuery` 및 `Cloud Logging` 통합 감사 로그 상관분석 | `make task6-verify-logs` | `BigQuery` `sdp_content_policy_action_logs`와 `StreamAssist` `assistToken` 조인으로 위반 사용자 식별 |
