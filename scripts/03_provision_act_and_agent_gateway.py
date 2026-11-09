#!/usr/bin/env python3
"""[Task 3] Provision PSC-I Subnet (/26), Static Cloud NAT, PSC Network Attachment, Cloud DNS, ACT (ALL_TRAFFIC), and 1-Step Immutable Egress Agent Gateway."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.panel import Panel
from rich.table import Table
from scripts.common import STATE_FILE, api_request, console, load_config, run_cmd


def main() -> None:
    cfg = load_config()
    console.print(
        Panel(
            f"[bold cyan]Task 3: Provision PSC-I Network, ACT (ALL_TRAFFIC) & 1-Step Egress Agent Gateway[/bold cyan]\n"
            f"Project: [yellow]{cfg.project_id}[/yellow] ({cfg.project_number}) | Region: [green]{cfg.region}[/green]",
            border_style="cyan",
        )
    )

    # 1. Create Service Identities for Network Services, Discovery Engine, AI Platform
    console.print("[bold]1. Bootstrapping Service Agents & IAM bindings...[/bold]")
    for svc in (
        "networkservices.googleapis.com",
        "discoveryengine.googleapis.com",
        "aiplatform.googleapis.com",
    ):
        run_cmd(
            ["gcloud", "beta", "services", "identity", "create", f"--service={svc}", f"--project={cfg.project_id}"],
            check=False,
        )

    net_sa = f"serviceAccount:service-{cfg.project_number}@gcp-sa-networkservices.iam.gserviceaccount.com"
    for role in ("roles/compute.networkAdmin", "roles/dns.peer"):
        run_cmd(
            [
                "gcloud",
                "projects",
                "add-iam-policy-binding",
                cfg.project_id,
                f"--member={net_sa}",
                f"--role={role}",
                "--condition=None",
                "--quiet",
            ],
            check=False,
        )

    # 2. Create PSC-I Subnet (/26) in us-central1 with Private Google Access
    console.print(
        f"[bold]2. Creating PSC-I Subnet ([cyan]{cfg.psci_subnet_name}[/cyan]: {cfg.psci_subnet_cidr}) in {cfg.region}...[/bold]"
    )
    run_cmd(
        [
            "gcloud",
            "compute",
            "networks",
            "subnets",
            "create",
            cfg.psci_subnet_name,
            f"--project={cfg.project_id}",
            f"--network={cfg.vpc_name}",
            f"--region={cfg.region}",
            f"--range={cfg.psci_subnet_cidr}",
            "--enable-private-ip-google-access",
        ],
        check=False,
    )

    # 3. Reserve Static Cloud NAT IP & Create Cloud Router + Cloud NAT
    console.print(
        f"[bold]3. Reserving Static Cloud NAT IP ([cyan]{cfg.cloud_nat_static_ip_name}[/cyan]) & configuring Cloud NAT...[/bold]"
    )
    run_cmd(
        [
            "gcloud",
            "compute",
            "addresses",
            "create",
            cfg.cloud_nat_static_ip_name,
            f"--project={cfg.project_id}",
            f"--region={cfg.region}",
        ],
        check=False,
    )
    ip_res = run_cmd(
        [
            "gcloud",
            "compute",
            "addresses",
            "describe",
            cfg.cloud_nat_static_ip_name,
            f"--project={cfg.project_id}",
            f"--region={cfg.region}",
            "--format=value(address)",
        ],
        check=False,
    )
    nat_static_ip = ip_res.stdout.strip() if ip_res.returncode == 0 else ""

    run_cmd(
        [
            "gcloud",
            "compute",
            "routers",
            "create",
            cfg.cloud_router_name,
            f"--project={cfg.project_id}",
            f"--network={cfg.vpc_name}",
            f"--region={cfg.region}",
        ],
        check=False,
    )
    run_cmd(
        [
            "gcloud",
            "compute",
            "routers",
            "nats",
            "create",
            cfg.cloud_nat_name,
            f"--project={cfg.project_id}",
            f"--router={cfg.cloud_router_name}",
            f"--region={cfg.region}",
            f"--nat-external-ip-pool={cfg.cloud_nat_static_ip_name}",
            f"--nat-custom-subnet-ip-ranges={cfg.psci_subnet_name}",
        ],
        check=False,
    )

    # 4. Create PSC Network Attachment in us-central1
    console.print(
        f"[bold]4. Creating PSC Network Attachment ([cyan]{cfg.psc_attachment_name}[/cyan]) in {cfg.region}...[/bold]"
    )
    run_cmd(
        [
            "gcloud",
            "compute",
            "network-attachments",
            "create",
            cfg.psc_attachment_name,
            f"--project={cfg.project_id}",
            f"--region={cfg.region}",
            f"--subnets={cfg.psci_subnet_name}",
            "--connection-preference=ACCEPT_AUTOMATIC",
        ],
        check=False,
    )

    # 5. Create Cloud DNS Private Zone
    console.print(
        f"[bold]5. Creating Cloud DNS Private Zone ([cyan]{cfg.dns_private_zone_name}[/cyan]: {cfg.dns_private_domain})...[/bold]"
    )
    run_cmd(
        [
            "gcloud",
            "dns",
            "managed-zones",
            "create",
            cfg.dns_private_zone_name,
            f"--project={cfg.project_id}",
            f"--dns-name={cfg.dns_private_domain}",
            "--description=Private Zone for Simulated AWS Custom MCP Servers",
            "--visibility=private",
            f"--networks={cfg.vpc_name}",
        ],
        check=False,
    )

    # 6. Create Agent Connectivity Template (ACT) with vpcEgress = ALL_TRAFFIC
    console.print(
        f"[bold]6. Creating Agent Connectivity Template ([cyan]{cfg.act_id}[/cyan], vpcEgress=ALL_TRAFFIC)...[/bold]"
    )
    base_url = f"https://networkservices.googleapis.com/v1/projects/{cfg.project_id}/locations/{cfg.region}"
    act_body = {
        "description": "Production ACT with ALL_TRAFFIC egress governance and DNS peering",
        "egressNetworkConfig": {
            "networkAttachment": (
                f"projects/{cfg.project_id}/regions/{cfg.region}"
                f"/networkAttachments/{cfg.psc_attachment_name}"
            ),
            "vpcEgress": "ALL_TRAFFIC",
        },
        "dnsPeeringConfig": [
            {
                "domain": cfg.dns_private_domain,
                "targetProject": cfg.project_id,
                "targetNetwork": cfg.vpc_name,
            }
        ],
    }
    act_resp = api_request(
        "POST",
        f"{base_url}/agentConnectivityTemplates",
        cfg,
        json_body=act_body,
        params={"agentConnectivityTemplateId": cfg.act_id},
    )
    if act_resp.status_code in (200, 201):
        console.print("  [green]ACT creation initiated. Waiting 15s for readiness...[/green]")
        time.sleep(15)
    elif act_resp.status_code == 409:
        console.print("  [yellow]ACT already exists. Proceeding...[/yellow]")
    else:
        console.print(f"  [yellow]ACT response ({act_resp.status_code}): {act_resp.text[:300]}[/yellow]")

    # 7. Create Egress Agent Gateway in 1-Step referencing ACT and Agent Registry
    console.print(
        f"[bold]7. Creating Egress Agent Gateway ([cyan]{cfg.agent_gateway_id}[/cyan]) in 1-Step (Immutability Compliant)...[/bold]"
    )
    agw_body = {
        "description": "Egress Agent Gateway bound in 1-Step to ACT and Agent Registry",
        "agentConnectivityTemplate": (
            f"projects/{cfg.project_id}/locations/{cfg.region}"
            f"/agentConnectivityTemplates/{cfg.act_id}"
        ),
        "googleManaged": {"governedAccessPath": "AGENT_TO_ANYWHERE"},
        "protocols": ["MCP"],
        "registries": [
            f"//agentregistry.googleapis.com/projects/{cfg.project_number}/locations/{cfg.region}"
        ],
    }
    agw_resp = api_request(
        "POST",
        f"{base_url}/agentGateways",
        cfg,
        json_body=agw_body,
        params={"agentGatewayId": cfg.agent_gateway_id},
    )
    if agw_resp.status_code in (200, 201):
        console.print("  [green]1-Step Egress Agent Gateway creation initiated![/green]")
    elif agw_resp.status_code == 409:
        console.print("  [yellow]Egress Agent Gateway already exists.[/yellow]")
    else:
        # Fallback to CLI creation if REST fields vary by project rollout
        run_cmd(
            [
                "gcloud",
                "network-services",
                "agent-gateways",
                "create",
                cfg.agent_gateway_id,
                f"--project={cfg.project_id}",
                f"--location={cfg.region}",
                "--protocols=MCP",
                "--google-managed-deployment-mode=AGENT_TO_ANYWHERE",
                f"--registries=//agentregistry.googleapis.com/projects/{cfg.project_number}/locations/{cfg.region}",
                "--quiet",
            ],
            check=False,
        )

    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    state.update(
        {
            "nat_static_ip": nat_static_ip,
            "act_id": cfg.act_id,
            "agent_gateway_id": cfg.agent_gateway_id,
            "psc_attachment_name": cfg.psc_attachment_name,
        }
    )
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    table = Table(title="Task 3 Egress Agent Gateway & Network Summary", show_lines=True)
    table.add_column("Resource", style="cyan")
    table.add_column("Identifier / Value", style="green")
    table.add_row("PSC-I Subnet (us-central1)", f"{cfg.psci_subnet_name} ({cfg.psci_subnet_cidr})")
    table.add_row("Cloud NAT Static IP (/32)", nat_static_ip or "Auto-allocated")
    table.add_row("PSC Network Attachment", cfg.psc_attachment_name)
    table.add_row("Agent Connectivity Template", f"{cfg.act_id} (ALL_TRAFFIC)")
    table.add_row("1-Step Egress Agent Gateway", cfg.agent_gateway_id)
    console.print(table)


if __name__ == "__main__":
    main()
