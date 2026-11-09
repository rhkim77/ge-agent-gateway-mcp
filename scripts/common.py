#!/usr/bin/env python3
"""Shared configuration loader, ADC authentication, gcloud runner, and Luhn validator."""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import google.auth
from google.auth.transport.requests import Request
import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_MCP_DIR = REPO_ROOT / "mock_aws_mcp_servers"
REGISTRY_SPECS_DIR = REPO_ROOT / "registry_specs"
POLICIES_DIR = REPO_ROOT / "policies"
STATE_FILE = REPO_ROOT / ".demo_state.json"


@dataclasses.dataclass
class LabConfig:
    """Centralized configuration loaded from .env or environment variables."""

    project_id: str
    project_number: str
    org_id: str
    ge_location: str
    region: str
    ma_ge_location: str
    ma_agw_location: str
    bq_location: str
    mcp_target_mode: str
    mock_mcp_service_name: str
    inventory_mcp_url: str
    oms_mcp_url: str
    mcp_auth_token: str
    vpc_name: str
    psci_subnet_name: str
    psci_subnet_cidr: str
    cloud_router_name: str
    cloud_nat_name: str
    cloud_nat_static_ip_name: str
    psc_attachment_name: str
    dns_private_zone_name: str
    dns_private_domain: str
    inventory_mcp_registry_id: str
    oms_mcp_registry_id: str
    googleapis_registry_id: str
    act_id: str
    agent_gateway_id: str
    cloud_armor_policy_name: str
    ma_ge_template_id: str
    ma_agw_template_id: str
    sdp_policy_id: str
    iap_authz_ext_id: str
    ma_authz_ext_id: str
    iap_authz_policy_id: str
    ma_authz_policy_id: str
    uap_access_policy_id: str
    uap_policy_binding_id: str
    model_armor_enforcement: str
    sdp_verdict: str
    iap_authz_mode: str
    ge_engine_id: str
    bq_dataset_id: str
    bq_table_id: str

    @property
    def trust_domain(self) -> str:
        """Return SPIFFE trust domain for Agent Identity."""
        if self.org_id:
            return f"agents.global.org-{self.org_id}.system.id.goog"
        return f"agents.global.proj-{self.project_number}.system.id.goog"

    @property
    def all_agents_principal_set(self) -> str:
        """Return principalSet URI covering all Agent Runtime agents in this project."""
        return (
            f"principalSet://{self.trust_domain}"
            f"/attribute.platformContainer/aiplatform/projects/{self.project_number}"
        )


def run_cmd(
    cmd: list[str],
    check: bool = True,
    capture_output: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a CLI command and return the CompletedProcess."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture_output,
        text=True,
        env=merged_env,
    )


def resolve_project_number(project_id: str) -> str:
    """Resolve numeric GCP Project Number via gcloud."""
    res = run_cmd(
        ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"],
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return project_id


def resolve_org_id(project_id: str) -> str:
    """Resolve GCP Organization ID if the project belongs to an organization."""
    res = run_cmd(
        ["gcloud", "projects", "get-ancestors", project_id, "--format=json"],
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        import json

        try:
            ancestors = json.loads(res.stdout)
            for item in ancestors:
                if item.get("type") == "organization":
                    return str(item.get("id", ""))
        except Exception:  # noqa: BLE001
            pass
    return ""


def load_config() -> LabConfig:
    """Load LabConfig from .env and resolve dynamic project metadata."""
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(REPO_ROOT / ".env.example")

    project_id = os.getenv("PROJECT_ID", "").strip()
    if not project_id or project_id == "your-gcp-project-id":
        res = run_cmd(["gcloud", "config", "get-value", "project"], check=False)
        if res.returncode == 0 and res.stdout.strip():
            project_id = res.stdout.strip()

    if not project_id or project_id == "your-gcp-project-id":
        console.print(
            Panel(
                "[bold red]Missing PROJECT_ID configuration![/bold red]\n\n"
                "Please copy [cyan].env.example[/cyan] to [cyan].env[/cyan] and set your "
                "Google Cloud [bold]PROJECT_ID[/bold]:\n"
                "  [green]cp .env.example .env[/green]",
                title="Configuration Error",
                border_style="red",
            )
        )
        sys.exit(1)

    project_number = os.getenv("PROJECT_NUMBER", "").strip() or resolve_project_number(project_id)
    org_id = os.getenv("ORG_ID", "").strip() or resolve_org_id(project_id)

    return LabConfig(
        project_id=project_id,
        project_number=project_number,
        org_id=org_id,
        ge_location=os.getenv("GE_LOCATION", "global").strip(),
        region=os.getenv("REGION", "us-central1").strip(),
        ma_ge_location=os.getenv("MA_GE_LOCATION", "us").strip(),
        ma_agw_location=os.getenv("MA_AGW_LOCATION", "us-central1").strip(),
        bq_location=os.getenv("BQ_LOCATION", "US").strip(),
        mcp_target_mode=os.getenv("MCP_TARGET_MODE", "simulated_aws_vpc").strip(),
        mock_mcp_service_name=os.getenv("MOCK_MCP_SERVICE_NAME", "aws-sim-fastmcp-server").strip(),
        inventory_mcp_url=os.getenv("INVENTORY_MCP_URL", "").strip(),
        oms_mcp_url=os.getenv("OMS_MCP_URL", "").strip(),
        mcp_auth_token=os.getenv("MCP_AUTH_TOKEN", "mcp_demo_secret_token_2026").strip(),
        vpc_name=os.getenv("VPC_NAME", "default").strip(),
        psci_subnet_name=os.getenv("PSCI_SUBNET_NAME", "ge-agw-psci-subnet-usc1").strip(),
        psci_subnet_cidr=os.getenv("PSCI_SUBNET_CIDR", "10.250.10.0/26").strip(),
        cloud_router_name=os.getenv("CLOUD_ROUTER_NAME", "ge-agw-nat-router-usc1").strip(),
        cloud_nat_name=os.getenv("CLOUD_NAT_NAME", "ge-agw-cloud-nat-usc1").strip(),
        cloud_nat_static_ip_name=os.getenv(
            "CLOUD_NAT_STATIC_IP_NAME", "ge-agw-nat-static-ip-usc1"
        ).strip(),
        psc_attachment_name=os.getenv(
            "PSC_ATTACHMENT_NAME", "ge-agw-network-attachment-usc1"
        ).strip(),
        dns_private_zone_name=os.getenv("DNS_PRIVATE_ZONE_NAME", "aws-mcp-private-zone").strip(),
        dns_private_domain=os.getenv("DNS_PRIVATE_DOMAIN", "mcp.aws.cymbal.internal.").strip(),
        inventory_mcp_registry_id=os.getenv(
            "INVENTORY_MCP_REGISTRY_ID", "cymbal-store-inventory-mcp"
        ).strip(),
        oms_mcp_registry_id=os.getenv("OMS_MCP_REGISTRY_ID", "cymbal-oms-order-mcp").strip(),
        googleapis_registry_id=os.getenv("GOOGLEAPIS_REGISTRY_ID", "googleapis").strip(),
        act_id=os.getenv("ACT_ID", "cymbal-ge-aws-mcp-act-usc1").strip(),
        agent_gateway_id=os.getenv("AGENT_GATEWAY_ID", "cymbal-ge-egress-agw-usc1").strip(),
        cloud_armor_policy_name=os.getenv(
            "CLOUD_ARMOR_POLICY_NAME", "mcp-edge-cloud-armor-waf"
        ).strip(),
        ma_ge_template_id=os.getenv("MA_GE_TEMPLATE_ID", "cymbal-ge-assistant-armor-tmpl").strip(),
        ma_agw_template_id=os.getenv("MA_AGW_TEMPLATE_ID", "cymbal-agw-inline-armor-tmpl").strip(),
        sdp_policy_id=os.getenv("SDP_POLICY_ID", "cymbal-ge-sdp-content-policy").strip(),
        iap_authz_ext_id=os.getenv("IAP_AUTHZ_EXT_ID", "cymbal-agw-iap-authz-ext").strip(),
        ma_authz_ext_id=os.getenv("MA_AUTHZ_EXT_ID", "cymbal-agw-ma-content-authz-ext").strip(),
        iap_authz_policy_id=os.getenv(
            "IAP_AUTHZ_POLICY_ID", "cymbal-agw-request-authz-policy"
        ).strip(),
        ma_authz_policy_id=os.getenv(
            "MA_AUTHZ_POLICY_ID", "cymbal-agw-content-authz-policy"
        ).strip(),
        uap_access_policy_id=os.getenv(
            "UAP_ACCESS_POLICY_ID", "cymbal-agent-egress-access-policy"
        ).strip(),
        uap_policy_binding_id=os.getenv(
            "UAP_POLICY_BINDING_ID", "cymbal-agent-egress-binding"
        ).strip(),
        model_armor_enforcement=os.getenv(
            "MODEL_ARMOR_ENFORCEMENT", "INSPECT_AND_BLOCK"
        ).strip(),
        sdp_verdict=os.getenv("SDP_VERDICT", "BLOCK").strip(),
        iap_authz_mode=os.getenv("IAP_AUTHZ_MODE", "V1_IAM").strip(),
        ge_engine_id=os.getenv("GE_ENGINE_ID", "cymbal-enterprise-ge-app").strip(),
        bq_dataset_id=os.getenv("BQ_DATASET_ID", "security_audit_logs").strip(),
        bq_table_id=os.getenv("BQ_TABLE_ID", "sdp_content_policy_action_logs").strip(),
    )


def get_auth_headers(quota_project_id: str | None = None) -> dict[str, str]:
    """Obtain OAuth2 Bearer token from Application Default Credentials (ADC)."""
    try:
        credentials, default_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        token = credentials.token
    except Exception:  # noqa: BLE001
        res = run_cmd(["gcloud", "auth", "print-access-token"], check=True)
        token = res.stdout.strip()
        default_project = quota_project_id

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    target_project = quota_project_id or default_project
    if target_project:
        headers["x-goog-user-project"] = target_project
    return headers


def api_request(
    method: str,
    url: str,
    cfg: LabConfig,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> httpx.Response:
    """Perform an authenticated HTTP request against Google Cloud REST APIs."""
    headers = get_auth_headers(cfg.project_id)
    with httpx.Client(timeout=timeout) as client:
        return client.request(
            method=method,
            url=url,
            headers=headers,
            json=json_body,
            params=params,
        )


def is_valid_luhn(card_number: str) -> bool:
    """Verify whether a credit card string satisfies the Luhn Checksum algorithm."""
    digits = [int(ch) for ch in card_number if ch.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for idx, digit in enumerate(digits):
        if idx % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0
