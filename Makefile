# ==============================================================================
# Makefile — Gemini Enterprise + Agent Registry + Agent Gateway + Armor/SDP Demo
# Repository: https://github.com/rhkim77/ge-agent-gateway-mcp
# ==============================================================================

PYTHON ?= uv run python
TF_DIR := labs/ce-ge-agent-gateway-mcp-governance/terraform

.PHONY: help install task1-deploy-mcp task2-register-mcp task3-provision-gateway \
        task4-bind-security task5-test-scenarios task6-verify-logs \
        check-progress validate-bundle demo-all teardown run-local-mcp

help:
	@echo "=========================================================================================="
	@echo " Gemini Enterprise + Agent Registry + Agent Gateway + Cloud/Model Armor + SDP Hands-On Lab"
	@echo "=========================================================================================="
	@echo "  make install                : Install Python dependencies via uv (or venv/pip)"
	@echo "  make task1-deploy-mcp       : [Task 1] Deploy Simulated AWS FastMCP Server (Inventory & OMS)"
	@echo "                                         on Cloud Run + External ALB + Cloud Armor WAF Policy"
	@echo "  make task2-register-mcp     : [Task 2] Register AWS MCP Servers (with ToolSpec annotations)"
	@echo "                                         and consolidated googleapis in Agent Registry (us-central1)"
	@echo "  make task3-provision-gateway: [Task 3] Provision PSC-I Subnet (/26), Cloud NAT Static IP,"
	@echo "                                         PSC Network Attachment, Cloud DNS, ACT (ALL_TRAFFIC),"
	@echo "                                         and 1-Step Immutable Egress Agent Gateway"
	@echo "  make task4-bind-security    : [Task 4/5] Lock Cloud Armor to Agent GW NAT IP, create Model Armor"
	@echo "                                           Templates (us & us-central1) + SDP ContentPolicy,"
	@echo "                                           and bind IAP Authz (DENY destructiveHint=true)"
	@echo "  make task5-test-scenarios   : [Task 6A] Execute 5 End-to-End Security & Governance Scenarios"
	@echo "                                          (Normal Read, Cloud Armor 403, IAP 403, PI Block, SDP PII)"
	@echo "  make task6-verify-logs      : [Task 6B] Query BigQuery SDP ContentPolicyActionLog, Cloud Armor,"
	@echo "                                          IAP Audit Logs & StreamAssist User Correlation"
	@echo "  make check-progress         : [Grader] Run Qwiklabs-style 6-Step Activity Tracking Self-Check"
	@echo "  make validate-bundle        : [Linter] Run GitWhisperer V2 Pre-Flight Bundle Validator"
	@echo "  make demo-all               : Run Task 1 through Task 6 sequentially"
	@echo "  make teardown               : Safely delete all demo resources in reverse-dependency order"
	@echo "=========================================================================================="

install:
	@if command -v uv >/dev/null 2>&1; then \
		uv sync; \
	else \
		python3 -m venv .venv && .venv/bin/pip install -e .; \
	fi

run-local-mcp:
	$(PYTHON) mock_aws_mcp_servers/server.py

task1-deploy-mcp:
	$(PYTHON) scripts/01_deploy_aws_mock_mcp_and_cloud_armor.py

task2-register-mcp:
	$(PYTHON) scripts/02_register_mcp_in_agent_registry.py

task3-provision-gateway:
	$(PYTHON) scripts/03_provision_act_and_agent_gateway.py

task4-bind-security:
	$(PYTHON) scripts/04_bind_cloud_model_armor_and_sdp.py

task5-test-scenarios:
	$(PYTHON) scripts/05_bind_ge_and_run_security_scenarios.py

task6-verify-logs:
	$(PYTHON) scripts/06_query_audit_logs_and_correlation.py

check-progress:
	$(PYTHON) scripts/check_my_progress.py

validate-bundle:
	python3 scripts/validate_bundle.py

demo-all: task1-deploy-mcp task2-register-mcp task3-provision-gateway task4-bind-security task5-test-scenarios task6-verify-logs check-progress

teardown:
	$(PYTHON) scripts/99_teardown_demo_resources.py
