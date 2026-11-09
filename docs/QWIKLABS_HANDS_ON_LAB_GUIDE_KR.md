# Qwiklabs Hands-On Lab Guide: Multi-Cloud AWS MCP & Gemini Enterprise Governance via Agent Registry & Agent Gateway

> **Document Scope**: 본 문서는 `Multi-Cloud (AWS ↔ Google Cloud)` 환경에 배포된 `FastMCP Server`를 **`Google Cloud Agent Registry` (`us-central1`)**에 등록하고, **`Agent Connectivity Template (ACT)` + `Egress Agent Gateway`** 기반의 정적 `Egress IP` 고정 및 **`Cloud Armor` + `IAP` + `Model Armor` + `Sensitive Data Protection (SDP)`** 5계층 방어선을 거쳐 **`Gemini Enterprise (GE)`**에서 안전하게 호출·검증하는 `6-Task` 실습 `Guide`입니다.

---

## 1. Lab Overview & Learning Objectives

기업의 핵심业务 시스템(`Inventory Management`, `Order Management System`)이 `AWS VPC`에 위치하고 전사 `AI Assistant`로 **`Gemini Enterprise`**를 도입할 때, 보안팀과 인프라팀은 다음 4가지 요구사항을 동시에 충족해야 합니다.

1. **Deterministic Network Egress (`AWS Firewall` 허용)**: `Google Managed Tenant`에서 출발하는 `MCP Tool Call` 트래픽을 고객 소유의 `VPC` 내부로 인입(`PSC Interface`)시킨 뒤, 고정된 `Cloud NAT Static IP (/32)`를 통해서만 외부 `AWS Endpoint`와 통신하도록 구성합니다.
2. **Centralized Tool Governance (`Agent Registry`)**: 분산된 `Multi-Cloud MCP Server`의 `Protocol Binding (JSON-RPC 2.0 over Streamable HTTP)`과 `Tool Schema`를 `Agent Registry (us-central1)`에 통합 등록하고 카탈로그화합니다.
3. **Zero-Trust Identity & Content Security (`IAP` + `Cloud Armor` + `Model Armor` + `SDP`)**:
   - `Network Edge`: **`Cloud Armor WAF`**(`SQLi`/`XSS`/`Scanner` 차단 및 `Rate Limiting`)
   - `Identity Layer`: **`IAP Request Authz` (`UAP Policy V2` / `IAP Policy V1`)** 기반 `Service Agent` 및 `CEL Condition` 통제
   - `Gateway Inline Layer`: **`Agent Gateway` + `Model Armor` (`us-central1`)**를 통한 `AWS MCP Tool Output` 내 `Indirect Prompt Injection` 및 `PII` 실시간 차단
   - `Assistant Layer`: **`Gemini Enterprise` + `Model Armor` (`us`) + `SDP Content Policy`**를 통한 사용자 `Prompt` / `Response` 양방향 `De-identification (Masking)` 및 `Audit Logging`
4. **End-to-End Auditability (`BigQuery Correlation`)**: `Prompt` 입력부터 `Agent Gateway` `Tool` 호출, `SDP` 마스킹까지 전 과정을 단일 `Session` 기준으로 추적합니다.

```mermaid
flowchart TD
    subgraph UserLayer["1. Enterprise User & Gemini Enterprise (us / global)"]
        User(["Enterprise User<br/>(Web UI / streamAssist API)"])
        GE["Gemini Enterprise App<br/>(Enterprise Edition + Audit Logging)"]
        SDP["SDP Content Policy &<br/>Model Armor Template (us)"]
    end

    subgraph GovernanceLayer["2. Agent Registry & Egress Agent Gateway (us-central1)"]
        AR["Agent Registry (us-central1)<br/>MCP Server Catalog & Tool Specs"]
        AGW["Egress Agent Gateway (us-central1)<br/>(ACT Bound + IAP Authz + Model Armor Inline)"]
    end

    subgraph NetworkLayer["3. Customer VPC Egress Control (us-central1)"]
        PSCI["PSC Network Attachment<br/>(PSC-I Subnet /26 + ALL_TRAFFIC)"]
        NAT["Cloud Router & Cloud NAT<br/>(Deterministic Static IP /32)"]
    end

    subgraph TargetLayer["4. AWS Target MCP Tier (Simulated or Real AWS)"]
        CA["Cloud Armor Edge WAF<br/>(SQLi / XSS / Rate Limit)"]
        MCP1["cymbal-store-inventory-mcp<br/>(/inventory/mcp)"]
        MCP2["cymbal-oms-order-mcp<br/>(/oms/mcp)"]
    end

    User -->|"Prompt"| GE
    GE <-->|"Inspect & Mask"| SDP
    GE -->|"Discover"| AR
    GE -->|"Invoke MCP"| AGW
    AGW -->|"PSC-I"| PSCI
    PSCI -->|"Route"| NAT
    NAT -->|"HTTPS (/32 IP)"| CA
    CA -->|"JSON-RPC"| MCP1
    CA -->|"JSON-RPC"| MCP2

    style User fill:#FFFFFF,stroke:#4285F4,stroke-width:2px,color:#202124
    style GE fill:#E8F0FE,stroke:#1A73E8,stroke-width:2px,color:#202124
    style SDP fill:#FEF7E0,stroke:#FBBC04,stroke-width:2px,color:#202124
    style AR fill:#E6F4EA,stroke:#34A853,stroke-width:2px,color:#202124
    style AGW fill:#E8F0FE,stroke:#1A73E8,stroke-width:2px,color:#202124
    style PSCI fill:#F8F9FA,stroke:#5F6368,stroke-width:2px,color:#202124
    style NAT fill:#F8F9FA,stroke:#5F6368,stroke-width:2px,color:#202124
    style CA fill:#FCE8E6,stroke:#EA4335,stroke-width:2px,color:#202124
    style MCP1 fill:#FFF8E1,stroke:#F9AB00,stroke-width:2px,color:#202124
    style MCP2 fill:#FFF8E1,stroke:#F9AB00,stroke-width:2px,color:#202124
```

---

## 2. Environment Setup (`Task 0`)

실습을 시작하기 전 `.env.example`을 복사하여 `.env` `File`을 생성하고 `Project ID`를 설정합니다.

```bash
cp .env.example .env
# .env 파일 내 PROJECT_ID를 실습용 Google Cloud Project ID로 변경합니다.
export PROJECT_ID=$(gcloud config get-value project)
sed -i "s/your-gcp-project-id/${PROJECT_ID}/g" .env

# Python 가상환경 및 의존성 설치
make setup
```

> **Note (`DRY_RUN` vs Live Execution)**:
> - 모든 단계의 `REST API Payload`와 `gcloud CLI` 명령어를 먼저 검증하려면 `.env`에서 `DRY_RUN=true`로 실행합니다.
> - 실제 `Google Cloud Project`에 `Resource`를 배포할 때는 `.env`에서 `DRY_RUN=false`로 변경하거나 각 `Script` 실행 시 `--live` `Flag`를 추가합니다.

---

## 3. Step-by-Step Lab Instructions (`Task 1` ~ `Task 6`)

### Task 1: Deploy Simulated AWS FastMCP Server & Cloud Armor Edge WAF (`15분`)

첫 번째 단계에서는 `AWS ECS Fargate / ALB` 환경을 모사한 **`Simulated AWS FastMCP Server`**를 배포하고, 앞단에 **`Cloud Armor Edge Security Policy`**(`SQLi`, `XSS`, `Scanner Detection`, `Rate Limiting`)를 구성합니다.

#### 1.1 Simulated AWS FastMCP Server 구조 확인
`mock_aws_mcp_servers/server.py`는 단일 `Container` 내에서 2개의 논리적 `AWS MCP Endpoint`를 제공합니다:
- **`/inventory/mcp` (`cymbal-store-inventory-mcp`)**: `get_store_inventory`, `check_Safety_stock_alert` (`Normal Traffic` 검증용)
- **`/oms/mcp` (`cymbal-oms-order-mcp`)**:
  - `get_vip_customer_claim`: 고객 실명, 주민등록번호(`KR_RRN`), 신용카드번호(`CREDIT_CARD_NUMBER`), 휴대전화번호(`PHONE_NUMBER`), 이메일(`EMAIL_ADDRESS`)이 포함된 `Payload` 반환 (`SDP` & `Model Armor` 마스킹 검증용)
  - `get_supplier_order_notes`: 배송 메모에 숨겨진 악성 `Indirect Prompt Injection` 문자열을 반환 (`Agent Gateway Inline Model Armor` 차단 검증용)

#### 1.2 배포 및 Cloud Armor 정책 생성 실행
```bash
uv run python scripts/01_deploy_aws_mock_mcp_and_cloud_armor.py
```

#### 1.3 JSON-RPC 2.0 Handshake 테스트
배포된 `FastMCP Endpoint`에 직접 `tools/list` 요청을 보내 정상 응답하는지 확인합니다.
```bash
curl -s -X POST "${SIMULATED_AWS_MCP_BASE_URL:-http://localhost:8080}/inventory/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq .
```

---

### Task 2: Register Multi-Cloud MCP Servers in Agent Registry (`us-central1`) (`15분`)

두 번째 단계에서는 배포된 2개의 `AWS MCP Endpoint`를 **`Agent Registry` (`us-central1`)**에 등록하고, 발급된 고유 `mcpServerId (UUID)`를 확인합니다.

> **Important (`Region Pinning Rule`)**:
> `Gemini Enterprise App`이 `global` 또는 `us` `Multi-Region`에 위치할 때, `Agent Registry`와 `Agent Gateway`는 반드시 **`us-central1` `Regional Location`**에 등록해야 합니다 (`locations/us` 수동 등록 금지).

#### 2.1 Registry Spec 확인 및 등록 실행
- `registry_specs/cymbal-store-inventory.toolspec.json`
- `registry_specs/cymbal-oms-order.toolspec.json`

```bash
uv run python scripts/02_register_mcp_in_agent_registry.py
```

#### 2.2 등록된 MCP Server UUID 조회
```bash
gcloud alpha agent-registry mcp-servers list --location=us-central1
```
생성된 `artifacts/step2_agent_registry_state.json` `File`에 각 `MCP Server`의 `mcpServerId (UUID)`가 자동 저장됩니다.

---

### Task 3: Provision PSC Network Attachment, ACT & Egress Agent Gateway (`20분`)

세 번째 단계에서는 `Google Managed Tenant`가 고객 `VPC` 내부로 안전하게 진입하여 고정된 `Cloud NAT IP (/32)`로 나갈 수 있도록 **`PSC-I Subnet (/26)` → `Cloud NAT` → `PSC Network Attachment` → `Agent Connectivity Template (ACT)` → `Egress Agent Gateway`**를 순서대로 프로비저닝합니다.

> **Critical Gotcha (`ACT & Agent Gateway Immutability`)**:
> `AgentGateway` `Resource`의 `networkConfig.egress.agentConnectivityTemplate` 필드는 **생성 시점(`Create Time`)에만 지정 가능하며 생성 후 수정(`PATCH`)이 불가능(`Immutable`)**합니다. 따라서 반드시 `ACT`를 먼저 생성한 뒤 `Agent Gateway` 생성 시 1-Step으로 바인딩해야 합니다.

#### 3.1 네트워크 및 Agent Gateway 프로비저닝 실행
```bash
uv run python scripts/03_provision_act_and_agent_gateway.py
```

#### 3.2 AWS Firewall 허용용 Static NAT IP 확인
`artifacts/step3_act_and_gateway_state.json`에 출력된 `Cloud NAT Static IP (/32)`와 `Agent Gateway Managed Endpoint URL`을 확인합니다. 실제 `AWS` 연동 시에는 이 `/32 IP`만 `AWS ALB Security Group`에 허용하면 됩니다.

---

### Task 4: Bind IAP Request Authz (`UAP V2` / `IAP V1`), Model Armor & SDP (`20분`)

네 번째 단계에서는 `Agent Registry` 및 `Agent Gateway`에 접근 제어를 부여하고, **`Model Armor` (`locations/us` 및 `locations/us-central1`)**와 **`Sensitive Data Protection (SDP)` (`De-identify + Inspect Template`)**을 구성합니다.

#### 4.1 Dual IAP Authorization (`UAP Policy V2` vs `IAP Policy V1` Fallback)
고객사 `Sandbox Project`에서 `constraints/iam.managed.disableAccessPolicyBinding` 조직 정책 수정 권한이 없는 경우에도 즉시 실습할 수 있도록, 본 `Script`는 `UAP Policy V2`와 `IAP Policy V1` 명령어를 모두 생성·실행합니다:

```bash
# [Option B - Recommended for Sandbox without Org Policy Admin] IAP Policy V1
gcloud iap web add-iam-policy-binding \
  --resource-type=agent-registry \
  --location=us-central1 \
  --mcp-server=${INVENTORY_MCP_UUID} \
  --member="user:${TEST_USER_EMAIL}" \
  --role="roles/iap.egressor"
```

#### 4.2 보안 정책 통합 바인딩 실행
```bash
uv run python scripts/04_bind_cloud_model_armor_and_sdp.py
```

이 `Script`는 다음 4가지 보안 구성을 완료합니다:
1. **`IAP Request Authz`**: `roles/iap.egressor` 권한 및 `AuthzExtension` 연결
2. **`Model Armor Template (locations/us)`**: `Gemini Enterprise Assistant`의 `User Prompt` / `Response` 검사용
3. **`Model Armor Template (locations/us-central1)`**: `Agent Gateway` `Inline CONTENT_AUTHZ` 검사용 (`AWS MCP Output` 내 `Indirect Prompt Injection` 차단)
4. **`SDP Content Policy`**: `KR_RRN`, `CREDIT_CARD_NUMBER`, `PHONE_NUMBER`, `EMAIL_ADDRESS` 탐지 및 `Character Masking (*)` 적용

---

### Task 5: Bind Gemini Enterprise & Run 4 Red-Team Security Scenarios (`15분`)

다섯 번째 단계에서는 `Gemini Enterprise App`에 `Agent Gateway`를 통과하는 `MCP Tool`을 연결하고, 4가지 보안 시나리오(`Scenario A ~ D`)를 실행하여 다계층 방어 동작을 검증합니다.

```bash
uv run python scripts/05_bind_ge_and_run_security_scenarios.py
```

#### 4대 검증 시나리오 요약 (`Scenario A ~ D`)

| Scenario | 테스트 내용 및 공격 유형 | 작동 방어 계층 | 기대 결과 (`Expected Verdict`) |
| :--- | :--- | :--- | :--- |
| **Scenario A**<br/>*(Normal Flow)* | 강남 플래그십 스토어(`STORE-SEL-001`) 재고 및 안전재고 상태 조회 | `Gemini Enterprise` → `Agent Gateway` → `Inventory MCP` | **`HTTP 200 OK`**<br/>정상 재고 수량(`142 units`) 응답 |
| **Scenario B**<br/>*(Edge Attack)* | `store_id="STORE-SEL-001' OR 1=1--"` `SQL Injection` 및 비인가 호출 시도 | **`Cloud Armor Edge WAF`** (`evaluatePreconfiguredWaf('sqli-v33-stable')`) + **`IAP Authz`** | **`HTTP 403 Forbidden`**<br/>`MCP Server` 도달 전 `Edge`에서 즉시 차단 |
| **Scenario C**<br/>*(Indirect Prompt Injection)* | 주문(`ORD-2026-99812`) 공급사 메모에 숨겨진 시스템 명령 탈취 시도 (`[SYSTEM OVERRIDE: IGNORE ALL PREVIOUS INSTRUCTIONS...]`) | **`Agent Gateway Inline Model Armor` (`us-central1`)** + **`GE Model Armor` (`us`)** | **`BLOCKED_BY_MODEL_ARMOR`**<br/>`Prompt Injection` 탐지 및 차단 응답 반환 |
| **Scenario D**<br/>*(PII Leakage Prevention)* | VIP 클레임(`CLM-2026-88410`) 조회 시 반환되는 주민번호·카드번호·전화번호·이메일 유출 방지 | **`SDP De-identify Template`** + **`Model Armor SDP Filter`** | **`ALLOW_WITH_SDP_REDACTION`**<br/>민감정보는 `******` 마스킹 처리 후 클레임 사유만 안전하게 요약 |

---

### Task 6: Verify End-to-End BigQuery & Cloud Logging Audit Correlation (`10분`)

마지막 단계에서는 `Gemini Enterprise Conversation Log`, `Agent Gateway Access Log`, `Model Armor Verdict Log`, `SDP Finding Log`, `Cloud Armor WAF Log`를 교차 조회하고, 전체 실습 진행률(`6/6 Checkpoints`)을 채점합니다.

```bash
# Audit Log 상관분석 리포트 생성
uv run python scripts/06_query_audit_logs_and_correlation.py

# Qwiklabs 6단계 진행 상태 자가 채점 (100/100 pts 확인)
make check-progress
```

---

## 4. Cleanup (`Teardown`)

실습 종료 후 과금 방지를 위해 생성된 `Resource`를 역순으로 안전하게 정리하려면 아래 명령을 실행합니다.

```bash
make teardown
```
