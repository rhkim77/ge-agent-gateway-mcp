# Multi-Cloud AWS MCP & Gemini Enterprise Governance with Agent Registry, Agent Gateway, Cloud Armor, Model Armor & SDP

## Overview

In enterprise multi-cloud environments where core retail and operational microservices (`Store Inventory Management`, `Order Management System (OMS)`) run in **Amazon Web Services (AWS)** while **Google Cloud Gemini Enterprise (GE)** serves as the unified enterprise AI assistant, security and platform engineering teams must enforce five strict governance controls:

1. **Deterministic Network Egress (`AWS Security Group Allowlisting`)**: Route outbound `MCP Tool Calls` from Google-managed tenant runtimes into the customer's VPC via **Private Service Connect Interface (`PSC-I` / `Network Attachment`)** and **Agent Connectivity Template (`ACT`)**, exiting through a single static **Cloud NAT IP (`/32`)**.
2. **Centralized Tool Governance (`Agent Registry`)**: Catalog multi-cloud `FastMCP` endpoints (`JSON-RPC 2.0` over `Streamable HTTP`) and their tool schemas in **Google Cloud Agent Registry (`us-central1`)**.
3. **Edge WAF Protection (`Cloud Armor`)**: Block `SQL Injection (SQLi)`, `Cross-Site Scripting (XSS)`, scanner probes, and volumetric abuse at the edge before requests reach the MCP server.
4. **Zero-Trust Identity & Inline Content Security (`IAP` + `Agent Gateway` + `Model Armor`)**: Enforce `IAP Request Authorization` (`roles/iap.egressor` & `UAP Policy V2` / `IAP Policy V1`) and inspect `MCP Tool Outputs` inline at the **Egress Agent Gateway (`us-central1`)** to block **Indirect Prompt Injection**.
5. **Sensitive Data Protection (`SDP Content Policy`) & End-to-End Audit Correlation**: Automatically mask sensitive `PII` (`KR_RRN`, `CREDIT_CARD_NUMBER`, `PHONE_NUMBER`, `EMAIL_ADDRESS`) in prompts and responses and correlate audit logs across **BigQuery** and **Cloud Logging**.

---

## Objectives

In this lab, you will complete the following 6 tasks:

- **Task 1**: Deploy the Simulated AWS FastMCP Server (`cymbal-store-inventory-mcp` and `cymbal-oms-order-mcp`) and provision the **Cloud Armor Edge WAF Policy** (`cymbal-mcp-edge-waf-policy`).
- **Task 2**: Register both multi-cloud MCP servers and their tool specifications in **Agent Registry (`us-central1`)**.
- **Task 3**: Provision the **PSC Network Attachment (`/26`)**, **Cloud NAT Static IP (`/32`)**, **Agent Connectivity Template (`ACT`)**, and **Egress Agent Gateway (`us-central1`)**.
- **Task 4**: Bind **IAP Request Authorization** (`UAP Policy V2` / `IAP Policy V1`), create **Model Armor Templates** (`locations/us` & `locations/us-central1`), and configure the **Sensitive Data Protection (`SDP`) Content Policy**.
- **Task 5**: Bind **Gemini Enterprise** to the governed MCP tools and execute **4 Red-Team Security Verification Scenarios (`Scenarios A–D`)**.
- **Task 6**: Query **BigQuery Conversation Logs** and **Cloud Logging** to verify end-to-end audit correlation across all 5 security layers.

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
<strong>Note:</strong> By default, <code>DRY_RUN=true</code> in <code>.env</code> validates payloads and generates state artifacts safely. Set <code>DRY_RUN=false</code> in <code>.env</code> (or pass <code>--live</code> to each script) to execute live API calls against your Google Cloud project.
</ql-infobox>

---

## Task 1. Deploy Simulated AWS FastMCP Server & Cloud Armor Edge WAF Policy

In this task, you deploy the **Simulated AWS FastMCP Server** (which emulates an AWS ECS Fargate / ALB target hosting `/inventory/mcp` and `/oms/mcp`) and create the **Cloud Armor Edge Security Policy** (`cymbal-mcp-edge-waf-policy`).

1. Run the Task 1 automation script:

```bash
uv run python scripts/01_deploy_aws_mock_mcp_and_cloud_armor.py
```

2. Inspect the generated state artifact in `artifacts/step1_mock_mcp_and_cloud_armor.json`:

```bash
cat artifacts/step1_mock_mcp_and_cloud_armor.json
```

Click **Check my progress** to verify the objective.
<ql-activity-tracking step=1>
Deploy Simulated AWS FastMCP Server & Cloud Armor Edge WAF Policy
</ql-activity-tracking>

---

## Task 2. Register Multi-Cloud AWS MCP Servers in Agent Registry (`us-central1`)

In this task, you register `cymbal-store-inventory-mcp` and `cymbal-oms-order-mcp` in **Google Cloud Agent Registry (`us-central1`)**.

<ql-warningbox>
<strong>Important (Region Pinning Rule):</strong> When integrating with a <code>global</code> or <code>us</code> Gemini Enterprise App, always register Agent Registry MCP servers and Egress Agent Gateways in <code>us-central1</code>. Do not manually register MCP servers in the <code>us</code> multi-region.
</ql-warningbox>

1. Run the Task 2 registration script:

```bash
uv run python scripts/02_register_mcp_in_agent_registry.py
```

2. Verify the assigned `mcpServerId (UUID)` values in `artifacts/step2_agent_registry_state.json`:

```bash
cat artifacts/step2_agent_registry_state.json
```

Click **Check my progress** to verify the objective.
<ql-activity-tracking step=2>
Register Multi-Cloud AWS MCP Servers in Agent Registry (us-central1)
</ql-activity-tracking>

---

## Task 3. Provision PSC Network Attachment, ACT & Egress Agent Gateway

In this task, you provision the **PSC-I Subnet (`10.240.10.0/26`)**, **Cloud NAT Static IP (`/32`)**, **PSC Network Attachment**, **Agent Connectivity Template (`ACT`)**, and **Egress Agent Gateway (`cymbal-aws-egress-gateway`)** in `us-central1`.

<ql-infobox>
<strong>Architecture Note:</strong> The <code>agentConnectivityTemplate</code> field on an <code>AgentGateway</code> resource is immutable after creation. Always provision the PSC Network Attachment and ACT before creating the Egress Agent Gateway in a single step.
</ql-infobox>

1. Run the Task 3 provisioning script:

```bash
uv run python scripts/03_provision_act_and_agent_gateway.py
```

2. Inspect the static egress IP and gateway endpoint in `artifacts/step3_act_and_gateway_state.json`:

```bash
cat artifacts/step3_act_and_gateway_state.json
```

Click **Check my progress** to verify the objective.
<ql-activity-tracking step=3>
Provision PSC Network Attachment, ACT & Egress Agent Gateway
</ql-activity-tracking>

---

## Task 4. Bind IAP Request Authz, Model Armor Templates & SDP Content Policy

In this task, you configure **IAP Request Authorization** (`roles/iap.egressor` via both `UAP Policy V2` and `IAP Policy V1` fallback), create **Model Armor Templates** in `locations/us` (for Gemini Enterprise Assistant) and `locations/us-central1` (for inline Agent Gateway inspection), and configure **Sensitive Data Protection (`SDP`) Inspect & De-identify Templates**.

1. Run the Task 4 security policy binding script:

```bash
uv run python scripts/04_bind_cloud_model_armor_and_sdp.py
```

2. Inspect the generated policy state in `artifacts/step4_security_policies_state.json`:

```bash
cat artifacts/step4_security_policies_state.json
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

In the final tasks, you bind the governed Agent Gateway MCP endpoints to **Gemini Enterprise**, execute the **4 Red-Team Security Verification Scenarios (`Scenarios A–D`)**, and run the **BigQuery & Cloud Logging Audit Correlation** check:

- **Scenario A (`Normal Store Inventory Lookup`)**: Allowed (`HTTP 200 OK`)
- **Scenario B (`SQLi Attack & Unauthorized Call`)**: Blocked at the Edge by **Cloud Armor WAF** (`HTTP 403 Forbidden`)
- **Scenario C (`Indirect Prompt Injection in Order Notes`)**: Blocked inline by **Agent Gateway + Model Armor** (`BLOCKED_BY_MODEL_ARMOR`)
- **Scenario D (`VIP Claim with Sensitive PII`)**: Allowed with automatic **`****` Character Masking** by **SDP Content Policy** (`ALLOW_WITH_SDP_REDACTION`)

1. Run the Task 5 security scenario verification script:

```bash
uv run python scripts/05_bind_ge_and_run_security_scenarios.py
```

2. Run the Task 6 audit correlation script and local progress checker:

```bash
uv run python scripts/06_query_audit_logs_and_correlation.py
make check-progress
```

Click **Check my progress** to verify the security scenarios and audit correlation report.
<ql-activity-tracking step=6>
Run 4 Red-Team Security Scenarios & BigQuery Audit Correlation
</ql-activity-tracking>

---

## Congratulations!

You have successfully registered multi-cloud AWS FastMCP servers in **Google Cloud Agent Registry (`us-central1`)**, provisioned a deterministic **Egress Agent Gateway** with **PSC Network Attachment** and **Cloud NAT (`/32`)**, enforced **Cloud Armor**, **IAP**, **Model Armor**, and **Sensitive Data Protection (`SDP`)** governance policies, and verified end-to-end security with **Gemini Enterprise**.
