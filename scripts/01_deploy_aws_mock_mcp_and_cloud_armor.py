#!/usr/bin/env python3
"""[Task 1] Deploy Simulated AWS FastMCP Server (Inventory & OMS) and Google Cloud Armor WAF Policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.panel import Panel
from rich.table import Table
from scripts.common import MOCK_MCP_DIR, STATE_FILE, console, load_config, run_cmd


def main() -> None:
    cfg = load_config()
    console.print(
        Panel(
            f"[bold cyan]Task 1: Deploy Simulated AWS FastMCP Server & Cloud Armor WAF Policy[/bold cyan]\n"
            f"Project: [yellow]{cfg.project_id}[/yellow] ({cfg.project_number}) | "
            f"Region: [green]{cfg.region}[/green] | Mode: [magenta]{cfg.mcp_target_mode}[/magenta]",
            border_style="cyan",
        )
    )

    # 1. Enable required base APIs
    apis = [
        "run.googleapis.com",
        "compute.googleapis.com",
        "cloudbuild.googleapis.com",
        "artifactregistry.googleapis.com",
        "agentregistry.googleapis.com",
        "networkservices.googleapis.com",
        "networksecurity.googleapis.com",
        "serviceextensions.googleapis.com",
        "iap.googleapis.com",
        "modelarmor.googleapis.com",
        "dlp.googleapis.com",
        "discoveryengine.googleapis.com",
        "dns.googleapis.com",
        "bigquery.googleapis.com",
    ]
    console.print("[bold]1. Enabling required Google Cloud APIs...[/bold]")
    run_cmd(["gcloud", "services", "enable", *apis, f"--project={cfg.project_id}"], check=False)

    # 2. Deploy Simulated AWS FastMCP Server on Cloud Run (if simulated_aws_vpc mode)
    inventory_url = cfg.inventory_mcp_url
    oms_url = cfg.oms_mcp_url
    service_url = ""

    if cfg.mcp_target_mode == "simulated_aws_vpc" or not inventory_url:
        console.print(
            f"[bold]2. Deploying Simulated AWS FastMCP Server ([cyan]{cfg.mock_mcp_service_name}[/cyan]) to Cloud Run ({cfg.region})...[/bold]"
        )
        run_cmd(
            [
                "gcloud",
                "run",
                "deploy",
                cfg.mock_mcp_service_name,
                f"--source={MOCK_MCP_DIR}",
                f"--region={cfg.region}",
                f"--project={cfg.project_id}",
                "--allow-unauthenticated",
                f"--set-env-vars=MCP_AUTH_TOKEN={cfg.mcp_auth_token}",
                "--quiet",
            ],
            check=True,
        )
        res = run_cmd(
            [
                "gcloud",
                "run",
                "services",
                "describe",
                cfg.mock_mcp_service_name,
                f"--region={cfg.region}",
                f"--project={cfg.project_id}",
                "--format=value(status.url)",
            ],
            check=True,
        )
        service_url = res.stdout.strip().rstrip("/")
        inventory_url = f"{service_url}/inventory/mcp"
        oms_url = f"{service_url}/oms/mcp"
    else:
        console.print("[bold]2. Using configured External AWS MCP Endpoints from .env...[/bold]")

    # 3. Create Google Cloud Armor WAF Security Policy
    console.print(
        f"[bold]3. Creating Google Cloud Armor Edge WAF Policy ([cyan]{cfg.cloud_armor_policy_name}[/cyan])...[/bold]"
    )
    desc_res = run_cmd(
        [
            "gcloud",
            "compute",
            "security-policies",
            "describe",
            cfg.cloud_armor_policy_name,
            f"--project={cfg.project_id}",
        ],
        check=False,
    )
    if desc_res.returncode != 0:
        run_cmd(
            [
                "gcloud",
                "compute",
                "security-policies",
                "create",
                cfg.cloud_armor_policy_name,
                f"--project={cfg.project_id}",
                "--description=Zero-Trust Cloud Armor WAF Policy for AWS Custom MCP Server Ingress",
            ],
            check=True,
        )
        # Add OWASP SQLi/XSS block rule (Priority 900)
        run_cmd(
            [
                "gcloud",
                "compute",
                "security-policies",
                "rules",
                "create",
                "900",
                f"--security-policy={cfg.cloud_armor_policy_name}",
                f"--project={cfg.project_id}",
                "--expression=evaluatePreconfiguredWaf('sqli-v33-stable') || evaluatePreconfiguredWaf('xss-v33-stable')",
                "--action=deny-403",
                "--description=Block OWASP SQLi and XSS in MCP JSON-RPC payloads",
            ],
            check=False,
        )
        # Add X-MCP-Token header rule (Priority 1100)
        run_cmd(
            [
                "gcloud",
                "compute",
                "security-policies",
                "rules",
                "create",
                "1100",
                f"--security-policy={cfg.cloud_armor_policy_name}",
                f"--project={cfg.project_id}",
                f"--expression=has(request.headers['x-mcp-token']) && request.headers['x-mcp-token'] == '{cfg.mcp_auth_token}'",
                "--action=allow",
                "--description=Allow authenticated MCP calls carrying valid X-MCP-Token",
            ],
            check=False,
        )

    # Save runtime state
    state = {}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    state.update(
        {
            "mock_mcp_base_url": service_url,
            "inventory_mcp_url": inventory_url,
            "oms_mcp_url": oms_url,
            "cloud_armor_policy": cfg.cloud_armor_policy_name,
        }
    )
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    table = Table(title="Task 1 Deployment Summary", show_lines=True)
    table.add_column("Component", style="cyan", no_wrap=True)
    table.add_column("Resource / Endpoint", style="green")
    table.add_row("Store & Inventory MCP URL", inventory_url)
    table.add_row("OMS Order Management MCP URL", oms_url)
    table.add_row("Google Cloud Armor WAF Policy", cfg.cloud_armor_policy_name)
    console.print(table)


if __name__ == "__main__":
    main()
