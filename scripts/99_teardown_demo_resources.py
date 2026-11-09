#!/usr/bin/env python3
"""Reverse-dependency safe teardown script for all demo resources."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.panel import Panel
from scripts.common import STATE_FILE, api_request, console, load_config, run_cmd


def main() -> None:
    cfg = load_config()
    console.print(
        Panel(
            f"[bold yellow]Teardown: Safely Removing Demo Resources in Reverse-Dependency Order[/bold yellow]\n"
            f"Project: [cyan]{cfg.project_id}[/cyan] | Region: [green]{cfg.region}[/green]",
            border_style="yellow",
        )
    )

    # 1. Remove AuthzPolicies & AuthzExtensions before Agent Gateway
    console.print("[bold]1. Deleting Network Security AuthzPolicies & Service Extensions...[/bold]")
    for pol_id in (cfg.iap_authz_policy_id, cfg.ma_authz_policy_id):
        run_cmd(
            [
                "gcloud",
                "beta",
                "network-security",
                "authz-policies",
                "delete",
                pol_id,
                f"--location={cfg.region}",
                f"--project={cfg.project_id}",
                "--quiet",
            ],
            check=False,
        )
    for ext_id in (cfg.iap_authz_ext_id, cfg.ma_authz_ext_id):
        run_cmd(
            [
                "gcloud",
                "service-extensions",
                "authz-extensions",
                "delete",
                ext_id,
                f"--location={cfg.region}",
                f"--project={cfg.project_id}",
                "--quiet",
            ],
            check=False,
        )

    # 2. Delete Egress Agent Gateway & Agent Connectivity Template (ACT)
    console.print("[bold]2. Deleting Egress Agent Gateway & Agent Connectivity Template...[/bold]")
    run_cmd(
        [
            "gcloud",
            "network-services",
            "agent-gateways",
            "delete",
            cfg.agent_gateway_id,
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--quiet",
        ],
        check=False,
    )
    base_url = f"https://networkservices.googleapis.com/v1/projects/{cfg.project_id}/locations/{cfg.region}"
    api_request("DELETE", f"{base_url}/agentConnectivityTemplates/{cfg.act_id}", cfg)

    # 3. Delete Agent Registry Services
    console.print("[bold]3. Deleting Agent Registry Services...[/bold]")
    for svc_id in (cfg.inventory_mcp_registry_id, cfg.oms_mcp_registry_id, cfg.googleapis_registry_id):
        run_cmd(
            [
                "gcloud",
                "agent-registry",
                "services",
                "delete",
                svc_id,
                f"--location={cfg.region}",
                f"--project={cfg.project_id}",
                "--quiet",
            ],
            check=False,
        )

    # 4. Delete Model Armor Templates & Cloud Armor Policy
    console.print("[bold]4. Deleting Model Armor Templates & Cloud Armor Policy...[/bold]")
    for loc, tmpl_id in (
        (cfg.ma_ge_location, cfg.ma_ge_template_id),
        (cfg.ma_agw_location, cfg.ma_agw_template_id),
    ):
        run_cmd(
            [
                "gcloud",
                "model-armor",
                "templates",
                "delete",
                tmpl_id,
                f"--location={loc}",
                f"--project={cfg.project_id}",
                "--quiet",
            ],
            check=False,
        )
    run_cmd(
        [
            "gcloud",
            "compute",
            "security-policies",
            "delete",
            cfg.cloud_armor_policy_name,
            f"--project={cfg.project_id}",
            "--quiet",
        ],
        check=False,
    )

    if STATE_FILE.exists():
        STATE_FILE.unlink()

    console.print("[bold green]Teardown completed![/bold green]")


if __name__ == "__main__":
    main()
