# Google Cloud Console UI Click-by-Click Verification Guide

> **Document Scope**: 본 문서는 `CLI`/`Script`(`make run-all`)로 구성된 **`Agent Registry` + `Agent Gateway` + `Cloud Armor` + `Model Armor` + `SDP` + `Gemini Enterprise`** 보안 거버넌스 환경을 **`Google Cloud Console Web UI`**에서 화면별로 직접 클릭하며 확인하고 시연(`Live Customer Demo`)하기 위한 단계별 가이드입니다.

---

## 1. Cloud Armor Edge WAF 정책 및 차단 로그 확인 (`Network Security`)

### 1.1 Cloud Armor Security Policy 확인
1. `Google Cloud Console` 상단 검색창에 **`Cloud Armor`**를 입력하고 **`Network Security > Cloud Armor policies`**로 이동합니다.
2. 목록에서 **`cymbal-mcp-edge-waf-policy`**를 클릭합니다.
3. **`Rules`** 탭을 클릭하여 아래 4개의 `Priority Rule`이 활성화되어 있는지 확인합니다:
   - **`Priority 1000` (`Deny 403`)**: `evaluatePreconfiguredWaf('sqli-v33-stable')` (`SQL Injection` 방어)
   - **`Priority 1100` (`Deny 403`)**: `evaluatePreconfiguredWaf('xss-v33-stable')` (`Cross-Site Scripting` 방어)
   - **`Priority 1200` (`Deny 403`)**: `evaluatePreconfiguredWaf('scannerdetection-v33-stable')` (`Scanner` 탐지 방어)
   - **`Priority 2000` (`Throttle 429`)**: `IP`당 분당 `120회` 요청 제한(`Rate Limiting`)

### 1.2 Cloud Armor 차단 로그 확인 (`Scenario B` 실행 후)
1. 해당 정책 상세 화면에서 **`Logs`** 탭을 클릭한 뒤 **`View in Logs Explorer`**를 클릭합니다.
2. `enforcedSecurityPolicy.name="cymbal-mcp-edge-waf-policy"` 및 `enforcedSecurityPolicy.outcome="DENY"` 조건으로 `SQLi` 공격(`Priority 1000`)이 `HTTP 403`으로 차단된 내역을 확인합니다.

---

## 2. Agent Registry 내 AWS MCP Server 카탈로그 확인 (`us-central1`)

1. `Google Cloud Console` 상단 검색창에 **`Agent Registry`**를 입력하거나 **`Vertex AI / Agent Builder > Agent Registry`** 메뉴로 이동합니다.
2. 상단 **`Region` 필터**를 반드시 **`us-central1` (`Iowa`)**로 선택합니다.
3. **`MCP Servers`** 탭을 클릭하여 등록된 2개의 `Multi-Cloud MCP Server`를 확인합니다:
   - **`cymbal-store-inventory-mcp`**: `Cymbal Enterprise Store Inventory MCP Server (AWS ECS)`
     - 클릭 시 노출되는 `Tools`: `get_store_inventory`, `check_safety_stock_alert`
   - **`cymbal-oms-order-mcp`**: `Cymbal Enterprise Order & Claim Management MCP Server (AWS ECS)`
     - 클릭 시 노출되는 `Tools`: `get_vip_customer_claim`, `get_supplier_order_notes`
4. 각 `MCP Server` 상세 페이지에서 **`Server ID (UUID)`**와 **`Protocol Binding (`JSON-RPC 2.0` / `Streamable HTTP`)`** 구성을 확인합니다.

---

## 3. VPC Network Attachment, Cloud NAT & Agent Gateway 확인 (`us-central1`)

### 3.1 PSC Network Attachment 확인
1. **`VPC network > Private Service Connect`** 메뉴로 이동합니다.
2. 상단 탭에서 **`Network attachments`**를 클릭합니다.
3. **`cymbal-agw-psc-attachment` (`us-central1`)**를 클릭하여 연결된 `Subnet`(**`cymbal-agw-psci-subnet`**, `10.240.10.0/26`)과 승인된 `Producer Project` 상태를 확인합니다.

### 3.2 Cloud NAT Static Egress IP (`/32`) 확인
1. **`Network services > Cloud NAT`** 메뉴로 이동합니다.
2. **`cymbal-agw-nat-gw` (`us-central1`)**를 클릭합니다.
3. **`Cloud NAT rules` / `NAT IP addresses`** 섹션에서 고정 할당된 **`cymbal-aws-mcp-egress-ip` (`/32 Static IP`)**를 확인합니다.
   - *시연 포인트*: "고객사 `AWS Security Group`에는 오직 이 단일 `/32 공인 IP`만 허용하면 됩니다."

### 3.3 Agent Connectivity Template (`ACT`) & Egress Agent Gateway 확인
1. **`Network Services > Agent Gateways`** (또는 `Cloud Shell`에서 `gcloud alpha network-services agent-gateways describe cymbal-aws-egress-gateway --location=us-central1`)를 확인합니다.
2. `Agent Gateway`의 핵심 속성을 점검합니다:
   - **`Mode`**: `CLIENT_TO_AGENT` (`Egress Agent Gateway`)
   - **`Protocols`**: `MCP`
   - **`Network Config (Egress)`**: `cymbal-aws-egress-act` (`ALL_TRAFFIC`) 바인딩 완료
   - **`Registry Target`**: `Agent Registry` 내 `AWS MCP Server` 연결 완료

---

## 4. Model Armor Templates (`us` & `us-central1`) 및 SDP Content Policy 확인

### 4.1 Model Armor Templates 확인
1. `Google Cloud Console` 상단 검색창에 **`Model Armor`**를 입력하고 **`Security > Model Armor`**로 이동합니다.
2. `Location` 필터에서 다음 2개의 `Template`을 각각 확인합니다:
   - **`us` (`Multi-Region`) — `cymbal-ge-assistant-ma-us`**:
     - `Gemini Enterprise Assistant` 전용 `Template`
     - `Prompt Injection & Jailbreak Detection`: **`HIGH` (`Confidence: LOW_AND_ABOVE`)**
     - `Malicious URI Filter`: **`ENABLED`**
     - `SDP Integration`: `Inspect Template` + `De-identify Template` 연결
   - **`us-central1` (`Region`) — `cymbal-agw-inline-ma-usc1`**:
     - `Agent Gateway` 인라인 `MCP Tool Call / Output` 검사용 `Template`
     - `AWS MCP Server`에서 반환되는 응답 내 숨겨진 `Indirect Prompt Injection`을 실시간 차단

### 4.2 Sensitive Data Protection (`SDP`) Templates & Content Policy 확인
1. `Google Cloud Console`에서 **`Security > Sensitive Data Protection`**으로 이동합니다.
2. **`Configuration > Templates > Inspect`** 탭에서 **`cymbal-ge-sdp-inspect`**를 클릭합니다:
   - 탐지 대상 `InfoTypes`: `KOREA_RRN` (주민등록번호), `CREDIT_CARD_NUMBER` (신용카드번호), `PHONE_NUMBER` (전화번호), `EMAIL_ADDRESS` (이메일), `PERSON_NAME` (성명)
3. **`Configuration > Templates > De-identify`** 탭에서 **`cymbal-ge-sdp-deid`**를 클릭합니다:
   - 변환 규칙: 민감 `InfoType` 탐지 시 끝 4자리를 제외한 앞자리를 `*`로 마스킹(`CharacterMaskConfig`)

---

## 5. Gemini Enterprise Web App 시연 및 BigQuery Audit Log 확인

### 5.1 Gemini Enterprise Web App에서 4대 시나리오 시연
1. `Google Cloud Console`에서 **`AI Applications (Discovery Engine) > Apps`**로 이동하여 대상 **`Gemini Enterprise App`**을 선택합니다.
2. 좌측 메뉴에서 **`Connected Tools / Extensions`**(또는 **`Agent Security`**)를 클릭하여 `Agent Gateway`를 경유하는 `MCP Tool`과 `Model Armor` / `SDP` 정책이 바인딩되어 있는지 확인합니다.
3. **`Preview` (또는 배포된 `Gemini Enterprise Web UI`)**를 열고 다음 프롬프트를 순서대로 입력하여 시연합니다:
   - **시연 1 (`정상 조회`)**:
     > `"강남 플래그십 스토어(STORE-SEL-001)의 SKU-1001 실시간 재고와 안전재고 상태를 조회해 줘."`
     - **결과**: `cymbal-store-inventory-mcp`를 호출하여 정상 재고(`142개`, `OK`)를 응답합니다.
   - **시연 2 (`Indirect Prompt Injection 차단`)**:
     > `"주문번호 ORD-2026-99812의 공급사 배송 메모(get_supplier_order_notes)를 조회해 줘."`
     - **결과**: `AWS MCP Server`가 반환한 악성 지시문(`[SYSTEM OVERRIDE: IGNORE ALL PREVIOUS INSTRUCTIONS...]`)을 `Agent Gateway` 및 `Model Armor`가 즉시 감지하여 차단합니다.
   - **시연 3 (`VIP 고객 PII 자동 마스킹`)**:
     > `"클레임 번호 CLM-2026-88410의 상세 내역(get_vip_customer_claim)을 조회하고 핵심 클레임 사유만 요약해 줘."`
     - **결과**: 원본 `Payload`에 있던 주민등록번호(`880101-1234567`), 신용카드번호(`4532-xxxx`), 전화번호(`010-xxxx`)는 `SDP De-identify Policy`에 의해 `******`로 마스킹되고, 냉장 배송 지연 사유만 안전하게 요약됩니다.

### 5.2 BigQuery & Cloud Logging 통합 감사 로그 확인
1. **`BigQuery Studio`**로 이동하여 `cymbal_ge_governance_audit` `Dataset`을 확장합니다.
2. `Conversation Audit Table`을 조회하여 방금 시연한 대화의 `session_id`, 호출된 `MCP Tool Name`, `SDP Finding Count`, `Model Armor Verdict`가 단일 타임라인으로 기록된 것을 확인합니다.
