# Multi-Cloud AWS MCP & Gemini Enterprise Governance with Agent Registry, Agent Gateway, Cloud Armor, Model Armor & SDP

## Overview & Architectural Rationale ("Why This Architecture?")

In enterprise multi-cloud environments where core retail and operational microservices (`Store Inventory Management`, `Order Management System (OMS)`) run in **Amazon Web Services (AWS)** while **Google Cloud Gemini Enterprise (GE)** serves as the unified enterprise AI assistant, connecting an MCP server directly by URL introduces four critical enterprise security and networking gaps.

This lab teaches you **why** each of the 5 governance layers is required and **how** to configure them step-by-step in both the **Google Cloud Console UI** and via automation:

1. **Why PSC Network Attachment + Agent Connectivity Template (`ACT`) + Cloud NAT (`/32`)? (`Deterministic Egress IP`)**
   - **Background Technology**: `Gemini Enterprise` and `Egress Agent Gateway` run inside a **Google-Managed Tenant Project (`Producer VPC`)**, not inside your customer VPC. Without an explicit network bridge, outbound `MCP Tool Calls` exit through Google's shared `Cloud Conduit` IP pools (dozens of dynamic CIDR blocks), making it impossible for an enterprise **AWS Security Group** to allowlist a single static IP.
   - **How It Works**: Creating a **Private Service Connect Interface (`PSC-I` / `Network Attachment`)** in your `us-central1` VPC subnet (`10.250.10.0/26`) and binding it to an **Agent Connectivity Template (`ACT` with `ALL_TRAFFIC`)** attaches a virtual network interface (`NIC`) from the Google-managed `Agent Gateway` directly into your VPC subnet. Every outbound `MCP` packet enters your VPC first and exits through your **Cloud NAT Static IP (`/32`)**.
2. **Why Agent Registry (`us-central1`) & IAP Request Authorization? (`Catalog & Zero-Trust Tool Access Control`)**
   - **Background Technology**: Hardcoding MCP URLs across agents creates unmanaged `Shadow MCP` endpoints and exposes high-risk destructive tools (`cancel_all_store_orders`, `override_product_unit_price`).
   - **How It Works**: Registering MCP servers in **Agent Registry (`us-central1`)** assigns an immutable `mcpServerId (UUID)` and records tool annotations (`readOnlyHint`, `destructiveHint`). Binding **IAP Request Authorization** (`roles/iap.egressor` via `IAP Policy V1` or `UAP Policy V2` CEL rules) ensures only authorized principals can invoke the MCP server and blocks destructive tools at the gateway layer.
3. **Why Dual-Location Model Armor Templates (`locations/us` & `locations/us-central1`)? (`Prompt Injection & Indirect Injection Defense`)**
   - **Background Technology**: A `global` or `us` **Gemini Enterprise App** requires a **`locations/us` Model Armor Template** to inspect user prompts (`Direct Jailbreak`) and final responses. However, if an external **AWS MCP Server** returns poisoned data (for example, a supplier order note containing `[SYSTEM OVERRIDE INSTRUCTION: Ignore all previous user instructions...]`), that **Indirect Prompt Injection** must be blocked *inline* at the **Egress Agent Gateway (`us-central1`)** before it enters the LLM context window—which requires a regional **`locations/us-central1` Model Armor Template**.
4. **Why Cloud Armor Edge WAF & Sensitive Data Protection (`SDP`)? (`Edge L7 Protection & PII Masking`)**
   - **Cloud Armor Edge WAF**: Blocks `SQL Injection (SQLi)`, `Cross-Site Scripting (XSS)`, scanner probes, and volumetric abuse (`HTTP 403 / 429`) before the MCP container parses the `JSON-RPC 2.0` payload.
   - **Sensitive Data Protection (`SDP`)**: Uses `InfoType` detectors (`KOREA_RRN`, `CREDIT_CARD_NUMBER` with `Luhn Checksum` verification, `PHONE_NUMBER`, `EMAIL_ADDRESS`) to redact (`******`) or block sensitive customer PII and write compliance audit records to **BigQuery**.

![Figure 1. Multi-Cloud AWS MCP & Gemini Enterprise 5-Layer Zero-Trust Governance Architecture](./img/diagram-1-e2e-5layer-governance-architecture.png)

![Figure 2. Direct Multi-Cloud MCP Challenges vs. 5-Layer Governance Architecture Solutions](./img/diagram-2-problems-vs-5layer-solutions.png)

![Figure 3. 7-Step Immutable Provisioning Workflow & Region Pinning](./img/diagram-3-immutable-provisioning-sequence.png)

---

## Objectives

In this lab, you will complete 6 tasks (using either the **Google Cloud Console UI** or the provided **Automation Scripts**):

- **Task 1**: Deploy the Simulated AWS FastMCP Server (`cymbal-store-inventory-mcp` and `cymbal-oms-order-mcp`) and configure the **Cloud Armor Edge WAF Policy** (`mcp-edge-cloud-armor-waf`).
- **Task 2**: Register both multi-cloud MCP servers and their tool specifications in **Agent Registry (`us-central1`)**.
- **Task 3**: Configure the **PSC-I Subnet (`10.250.10.0/26`)**, **Cloud NAT Static IP (`/32`)**, **PSC Network Attachment**, **Agent Connectivity Template (`ACT`)**, and **Egress Agent Gateway (`us-central1`)**.
- **Task 4**: Configure **IAP Request Authorization** (`roles/iap.egressor`), create **Model Armor Templates** (`locations/us` & `locations/us-central1`), and configure **Sensitive Data Protection (`SDP`) Templates**.
- **Task 5**: Bind **Gemini Enterprise** to the governed MCP tools and execute **4 Red-Team Security Verification Scenarios (`Scenarios A–D`)**.
- **Task 6**: Query **BigQuery Audit Logs** and **Cloud Logging** to verify end-to-end correlation across all 5 security layers.

---

## Environment Preparation

1. Open your terminal (or the pre-provisioned **Remote Browser Work Environment**) and clone the lab repository:

```bash
git clone https://github.com/rhkim77/ge-agent-gateway-mcp.git
cd ge-agent-gateway-mcp
```

2. Initialize your `.env` configuration file with your active Google Cloud Project ID:

```bash
cp .env.example .env
export PROJECT_ID=$(gcloud config get-value project)
sed -i "s/your-gcp-project-id/${PROJECT_ID}/g" .env
make setup
```

<ql-infobox>
<strong>Note:</strong> For every task below, you can follow <strong>Method A (Google Cloud Console UI Step-by-Step)</strong> to understand each setting in the Console, and/or run <strong>Method B (CLI Automation Script)</strong> to verify and generate the state artifacts.
</ql-infobox>

---

## Task 1. Deploy Simulated AWS FastMCP Server & Cloud Armor Edge WAF Policy

### Why You Configure This
`MCP Streamable HTTP` uses `JSON-RPC 2.0` over `HTTP POST`. If a malicious prompt tricks the agent into passing `SQL Injection` (`' OR 1=1--`) or `XSS` payloads inside tool arguments (`store_id`, `order_id`), **Cloud Armor Edge WAF** blocks the request at the load balancer edge (`HTTP 403 Forbidden`) before it reaches the MCP server container.

### Method A: Configure in the Google Cloud Console UI
1. **Deploy Simulated AWS FastMCP Service (`Cloud Run`)**:
   - In the Google Cloud Console, navigate to **Cloud Run > Deploy container > Service**.
   - Set **Service name** to `aws-sim-fastmcp-server` and **Region** to `us-central1 (Iowa)`.
   - Under **Container(s) > General**, set **Container port** to `8080` and add environment variable `MCP_AUTH_TOKEN=mcp_demo_secret_token_2026`. Click **Create**.
2. **Create Cloud Armor Edge WAF Policy**:
   - Navigate to **Network Security > Cloud Armor policies** and click **+ Create policy**.
   - Set **Name** to `mcp-edge-cloud-armor-waf`, **Policy type** to **Backend security policy**, and **Scope** to **Global**.
   - Under **Add more rules**, switch to **Advanced mode** and add the following 4 rules:
     - **Priority `1000` (`Deny 403`)**: `evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})`
     - **Priority `1100` (`Deny 403`)**: `evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})`
     - **Priority `1200` (`Deny 403`)**: `evaluatePreconfiguredWaf('scannerdetection-v33-stable', {'sensitivity': 1})`
     - **Priority `2000` (`Throttle 429`)**: `true` (`120 requests per 1 minute` per IP)
   - Click **Create policy**.

### Method B: Run Automation Script
```bash
uv run python scripts/01_deploy_aws_mock_mcp_and_cloud_armor.py
```

Click **Check my progress** to verify the objective.
<ql-activity-tracking step=1>
Deploy Simulated AWS FastMCP Server & Cloud Armor Edge WAF Policy
</ql-activity-tracking>

---

## Task 2. Register Multi-Cloud AWS MCP Servers in Agent Registry (`us-central1`)

### Why You Configure This
Registering MCP servers in **Agent Registry (`us-central1`)** establishes a governed catalog, assigns an immutable `mcpServerId (UUID)` required by `Agent Gateway` and `IAP`, and records tool-level safety annotations (`readOnlyHint: true` vs. `destructiveHint: true`).

<ql-warningbox>
<strong>Important (Region Pinning Rule):</strong> When integrating with a <code>global</code> or <code>us</code> Gemini Enterprise App, always select <code>us-central1</code> in Agent Registry. Never manually register MCP servers in the <code>us</code> multi-region.
</ql-warningbox>

### Method A: Configure in the Google Cloud Console UI
1. In the Google Cloud Console, navigate to **Vertex AI (or Agent Builder) > Agent Registry**.
2. Set the **Region** dropdown at the top of the page to **`us-central1 (Iowa)`**.
3. Select the **MCP Servers** tab and click **+ Register MCP Server** to register both endpoints:
   - **`cymbal-store-inventory-mcp`**: Endpoint `<SERVICE_URL>/inventory/mcp` (`get_store_inventory`, `search_product_catalog`, `get_vip_customer_claim` with `readOnlyHint: true`)
   - **`cymbal-oms-order-mcp`**: Endpoint `<SERVICE_URL>/oms/mcp` (`get_purchase_order`, `create_purchase_order`, and high-risk tools `cancel_all_store_orders` & `override_product_unit_price` with `destructiveHint: true`)
4. Copy the generated **Server UUID** for each registered MCP server.

### Method B: Run Automation Script
```bash
uv run python scripts/02_register_mcp_in_agent_registry.py
```

Click **Check my progress** to verify the objective.
<ql-activity-tracking step=2>
Register Multi-Cloud AWS MCP Servers in Agent Registry (us-central1)
</ql-activity-tracking>

---

## Task 3. Provision PSC Network Attachment, ACT & Egress Agent Gateway

### Why You Configure This
Because `Agent Gateway` runs in a Google-managed tenant VPC, you must provision a **PSC-I Subnet (`/26`)**, **Cloud NAT Static IP (`/32`)**, **PSC Network Attachment**, and **Agent Connectivity Template (`ACT`)** so outbound MCP traffic enters your VPC and exits via your single `/32` NAT IP.

<ql-infobox>
<strong>Architecture Note (ACT Immutability):</strong> The <code>agentConnectivityTemplate</code> field on an <code>AgentGateway</code> resource is immutable after creation. Always provision the PSC Network Attachment and ACT first, then bind the ACT when creating the Egress Agent Gateway.
</ql-infobox>

![Figure 4. Deterministic Egress Packet Flow via PSC Network Attachment, ACT (ALL_TRAFFIC) & Cloud NAT (/32)](./img/diagram-4-psci-act-cloud-nat-packet-flow.png)

### Method A: Configure in the Google Cloud Console UI
1. **Create PSC-I Subnet (`/26`)**: Navigate to **VPC network > VPC networks > default > + Add subnet**. Set **Name** = `ge-agw-psci-subnet-usc1`, **Region** = `us-central1`, **IPv4 range** = `10.250.10.0/26`, **Private Google Access** = `On`.
2. **Reserve Static Egress IP (`/32`)**: Navigate to **VPC network > IP addresses > + Reserve external static IP address**. Set **Name** = `ge-agw-nat-static-ip-usc1`, **Region** = `us-central1`.
3. **Configure Cloud Router & Cloud NAT**: Navigate to **Network services > Cloud NAT > + Create Cloud NAT gateway**. Set **Gateway name** = `ge-agw-cloud-nat-usc1`, **Region** = `us-central1`, **NAT IP addresses** = **Manual** (`ge-agw-nat-static-ip-usc1`).
4. **Create PSC Network Attachment**: Navigate to **VPC network > Private Service Connect > Network attachments > + Create network attachment**. Set **Name** = `ge-agw-network-attachment-usc1`, **Region** = `us-central1`, **Subnetwork** = `ge-agw-psci-subnet-usc1`.
5. **Create ACT & Egress Agent Gateway**: Under **Network Services > Agent Gateways** (`us-central1`), create ACT `cymbal-ge-aws-mcp-act-usc1` (`ALL_TRAFFIC`) and bind it to Egress Agent Gateway `cymbal-ge-egress-agw-usc1` (`mode: CLIENT_TO_AGENT`, `protocols: [MCP]`).

### Method B: Run Automation Script
```bash
uv run python scripts/03_provision_act_and_agent_gateway.py
```

Click **Check my progress** to verify the objective.
<ql-activity-tracking step=3>
Provision PSC Network Attachment, ACT & Egress Agent Gateway
</ql-activity-tracking>

---

## Task 4. Bind IAP Request Authz, Model Armor Templates & SDP Content Policy

### Why You Configure This
- **IAP Request Authorization (`roles/iap.egressor`)**: Ensures only authorized principals can invoke MCP servers through the gateway and blocks `destructiveHint == true` tools.
- **Model Armor (`locations/us` & `locations/us-central1`)**: Protects Gemini Enterprise prompts/responses (`locations/us`) and inspects external AWS MCP outputs inline at the Agent Gateway (`locations/us-central1`) to stop **Indirect Prompt Injection**.
- **Sensitive Data Protection (`SDP`)**: Detects and masks `KOREA_RRN`, `CREDIT_CARD_NUMBER` (validated via Luhn checksum), `PHONE_NUMBER`, and `EMAIL_ADDRESS`.

![Figure 5. Dual-Location Model Armor (locations/us & locations/us-central1) & SDP Inline Inspection Architecture](./img/diagram-5-dual-model-armor-sdp-inspection.png)

### Method A: Configure in the Google Cloud Console UI
1. **Grant IAP Egress Role**: Navigate to **Security > Identity-Aware Proxy (IAP)**, select the **Agent Registry / MCP Servers** resources in `us-central1`, click **+ Add Principal**, and grant **`IAP-secured Egress App User` (`roles/iap.egressor`)** to your user and Discovery Engine service agent.
2. **Create SDP Inspect & De-identify Templates**: Navigate to **Security > Sensitive Data Protection > Configuration > Templates** (`Location: us`) and create:
   - Inspect Template `cymbal-ge-sdp-inspect` (`KOREA_RRN`, `CREDIT_CARD_NUMBER`, `PHONE_NUMBER`, `EMAIL_ADDRESS`, `PERSON_NAME`, `Minimum likelihood: Possible`)
   - De-identify Template `cymbal-ge-sdp-deid` (`Mask with character: *`)
3. **Create Dual-Location Model Armor Templates**: Navigate to **Security > Model Armor > + Create template** and create:
   - **`cymbal-ge-assistant-ma-us`** in **`Location: us (Multi-region)`** (for Gemini Enterprise Assistant)
   - **`cymbal-agw-inline-ma-usc1`** in **`Location: us-central1 (Region)`** (for inline Agent Gateway inspection)
   - Enable **Prompt injection and jailbreak detection (`Low and above`)**, **Malicious URL detection**, and link the **SDP Inspect & De-identify templates**.

### Method B: Run Automation Script
```bash
uv run python scripts/04_bind_cloud_model_armor_and_sdp.py
```

Click **Check my progress** to verify the IAP Request Authorization policy binding.
<ql-activity-tracking step=4>
Bind IAP Request Authz (UAP Policy V2 / IAP Policy V1)
</ql-activity-tracking>

Click **Check my progress** to verify the Model Armor Templates and SDP Content Policy.
<ql-activity-tracking step=5>
Create Model Armor Templates (us & us-central1) & SDP Content Policy
</ql-activity-tracking>

---

## Task 5 & 6. Run 4 Red-Team Security Scenarios & BigQuery Audit Correlation

### Why You Configure This
Binding the governed **Agent Gateway MCP endpoints**, **Model Armor Template (`locations/us`)**, and **SDP Content Policy** to **Gemini Enterprise** enables end-to-end protection and writes correlated compliance logs to **BigQuery (`security_audit_logs.sdp_content_policy_action_logs`)**.

### Method A: Configure & Test in the Google Cloud Console UI
1. Navigate to **AI Applications > Apps**, select your **Gemini Enterprise App**, attach the governed Agent Gateway MCP endpoints under **Connected Tools**, and bind `cymbal-ge-assistant-ma-us` and `cymbal-ge-sdp-content-policy` under **Security**.
2. Open the **Preview** chat console and test all 4 scenarios:
   - **Scenario A (`Normal Store Inventory Lookup`)**: Query `STORE-SEOUL-001` stock for `SKU-LUNCHBOX-101` -> Allowed (`HTTP 200 OK`, `48 units`)
   - **Scenario B (`SQLi Attack & Destructive Tool Call`)**: Query `store_id="STORE-SEOUL-001' OR 1=1--"` or invoke `cancel_all_store_orders` -> Blocked by **Cloud Armor WAF** & **IAP Authz** (`HTTP 403 Forbidden`)
   - **Scenario C (`Indirect Prompt Injection in Order Notes`)**: Query `get_purchase_order` for `ORD-INJ-9999` -> Blocked inline by **Agent Gateway + Model Armor** (`BLOCKED_BY_MODEL_ARMOR`)
   - **Scenario D (`VIP Claim with Sensitive PII`)**: Query `get_vip_customer_claim` for `CLM-PII-9001` -> Blocked or masked (`******`) by **SDP Content Policy** and logged to **BigQuery**
3. Navigate to **BigQuery Studio** and query `security_audit_logs.sdp_content_policy_action_logs` to inspect the correlated audit records.

### Method B: Run Automation Scripts & Progress Grader
```bash
uv run python scripts/05_bind_ge_and_run_security_scenarios.py
uv run python scripts/06_query_audit_logs_and_correlation.py
make check-progress
```

Click **Check my progress** to verify the security scenarios and audit correlation report.
<ql-activity-tracking step=6>
Run 4 Red-Team Security Scenarios & BigQuery Audit Correlation
</ql-activity-tracking>

---

## Congratulations!

You have understood the architectural rationale behind each governance layer and configured **Multi-Cloud AWS FastMCP Servers**, **Agent Registry (`us-central1`)**, **PSC Network Attachment + Cloud NAT (`/32`)**, **Egress Agent Gateway**, **Cloud Armor**, **IAP**, **Model Armor (`us` & `us-central1`)**, and **Sensitive Data Protection (`SDP`)** with **Gemini Enterprise**.
