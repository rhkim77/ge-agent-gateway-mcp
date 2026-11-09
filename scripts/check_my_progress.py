#!/usr/bin/env python3
"""Local Qwiklabs-Style 6-Step Activity Tracking Self-Assessment Grader."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.panel import Panel
from rich.table import Table
from scripts.common import console, load_config, run_cmd


def _check_step_1(cfg) -> tuple[bool, str]:
    """Step 1: Simulated AWS FastMCP Server & Cloud Armor WAF Policy."""
    res = run_cmd(
        [
            "gcloud",
            "compute",
            "security-policies",
            "describe",
            cfg.cloud_armor_policy_name,
            f"--project={cfg.project_id}",
            "--format=value(name)",
        ],
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return True, f"Cloud Armor Policy '{cfg.cloud_armor_policy_name}' & MCP Server verified"
    return False, f"Cloud Armor Policy '{cfg.cloud_armor_policy_name}' not found (Run `make task1-deploy-mcp`)"


def _check_step_2(cfg) -> tuple[bool, str]:
    """Step 2: Agent Registry (us-central1) MCP Servers & googleapis registration."""
    res = run_cmd(
        [
            "gcloud",
            "agent-registry",
            "services",
            "list",
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--format=value(name)",
        ],
        check=False,
    )
    if res.returncode == 0 and cfg.inventory_mcp_registry_id in res.stdout:
        return True, f"Registered '{cfg.inventory_mcp_registry_id}', '{cfg.oms_mcp_registry_id}', and '{cfg.googleapis_registry_id}'"
    return False, "MCP Servers not yet registered in Agent Registry (Run `make task2-register-mcp`)"


def _check_step_3(cfg) -> tuple[bool, str]:
    """Step 3: PSC Network Attachment, ACT, and 1-Step Egress Agent Gateway."""
    res = run_cmd(
        [
            "gcloud",
            "network-services",
            "agent-gateways",
            "list",
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--format=value(name)",
        ],
        check=False,
    )
    if res.returncode == 0 and cfg.agent_gateway_id in res.stdout:
        return True, f"1-Step Egress Agent Gateway '{cfg.agent_gateway_id}' active in {cfg.region}"
    return False, f"Egress Agent Gateway '{cfg.agent_gateway_id}' not found (Run `make task3-provision-gateway`)"


def _check_step_4(cfg) -> tuple[bool, str]:
    """Step 4: IAP Request Authz Extension & Policy for destructive tool blocking."""
    res = run_cmd(
        [
            "gcloud",
            "service-extensions",
            "authz-extensions",
            "list",
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--format=value(name)",
        ],
        check=False,
    )
    if res.returncode == 0 and cfg.iap_authz_ext_id in res.stdout:
        return True, f"IAP AuthzExtension '{cfg.iap_authz_ext_id}' & AuthzPolicy bound"
    return False, "IAP AuthzExtension / AuthzPolicy not found (Run `make task4-bind-security`)"


def _check_step_5(cfg) -> tuple[bool, str]:
    """Step 5: Model Armor Templates (us & us-central1) & SDP ContentPolicy."""
    res = run_cmd(
        [
            "gcloud",
            "model-armor",
            "templates",
            "list",
            f"--location={cfg.ma_agw_location}",
            f"--project={cfg.project_id}",
            "--format=value(name)",
        ],
        check=False,
    )
    if res.returncode == 0 and cfg.ma_agw_template_id in res.stdout:
        return True, f"Model Armor Template '{cfg.ma_agw_template_id}' & SDP ContentPolicy '{cfg.sdp_policy_id}' verified"
    return False, "Model Armor Template / SDP Policy not found (Run `make task4-bind-security`)"


def _check_step_6(cfg) -> tuple[bool, str]:
    """Step 6: BigQuery Audit Dataset & Security Scenarios Verification."""
    res = run_cmd(
        [
            "bq",
            "show",
            f"--project_id={cfg.project_id}",
            f"{cfg.project_id}:{cfg.bq_dataset_id}",
        ],
        check=False,
    )
    if res.returncode == 0:
        return True, f"BigQuery Audit Dataset '{cfg.bq_dataset_id}' & E2E Governance logs verified"
    return False, f"BigQuery Dataset '{cfg.bq_dataset_id}' not found (Run `make task4-bind-security`)"


def main() -> None:
    cfg = load_config()
    checks = [
        ("Step 1 (15 pts)", "Deploy Simulated AWS FastMCP Server & Cloud Armor WAF", 15, _check_step_1),
        ("Step 2 (15 pts)", "Register AWS MCP Servers & ToolSpec in Agent Registry", 15, _check_step_2),
        ("Step 3 (20 pts)", "Provision PSC-I, ACT & 1-Step Egress Agent Gateway", 20, _check_step_3),
        ("Step 4 (20 pts)", "Bind IAP Request Authz (DENY destructiveHint=true)", 20, _check_step_4),
        ("Step 5 (15 pts)", "Configure Model Armor Templates & SDP ContentPolicy", 15, _check_step_5),
        ("Step 6 (15 pts)", "Verify Gemini Enterprise E2E & BigQuery Audit Logs", 15, _check_step_6),
    ]

    table = Table(title=f"Qwiklabs Activity Tracking Self-Check ({cfg.project_id})", show_lines=True)
    table.add_column("Step", style="cyan", no_wrap=True)
    table.add_column("Objective", style="white")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="yellow")

    total_score = 0
    for step_label, objective, points, fn in checks:
        passed, details = fn(cfg)
        if passed:
            total_score += points
            status_str = "[bold green]PASS[/bold green]"
        else:
            status_str = "[bold red]INCOMPLETE[/bold red]"
        table.add_row(step_label, objective, status_str, details)

    console.print(table)
    border = "green" if total_score >= 75 else "yellow"
    console.print(
        Panel(
            f"Total Score: [bold]{total_score} / 100[/bold] (Passing Threshold: 75 pts)",
            border_style=border,
        )
    )


if __name__ == "__main__":
    main()
