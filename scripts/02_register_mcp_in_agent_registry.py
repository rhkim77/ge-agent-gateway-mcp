#!/usr/bin/env python3
"""[Task 2] Register AWS Custom MCP Servers (with ToolSpec annotations) and consolidated googleapis in Agent Registry (us-central1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.panel import Panel
from rich.table import Table
from scripts.common import REGISTRY_SPECS_DIR, STATE_FILE, console, load_config, run_cmd


GOOGLEAPIS_HOSTS = [
    ("https://agentregistry.googleapis.com", "HTTP_JSON"),
    ("https://aiplatform.googleapis.com", "HTTP_JSON"),
    ("https://aiplatform.mtls.googleapis.com", "HTTP_JSON"),
    ("https://us-central1-aiplatform.googleapis.com", "HTTP_JSON"),
    ("https://us-central1-aiplatform.mtls.googleapis.com", "HTTP_JSON"),
    ("https://aiplatform.us-central1.rep.googleapis.com", "HTTP_JSON"),
    ("https://us-aiplatform.googleapis.com", "HTTP_JSON"),
    ("https://us-aiplatform.mtls.googleapis.com", "HTTP_JSON"),
    ("https://aiplatform.us.rep.googleapis.com", "HTTP_JSON"),
    ("https://discoveryengine.googleapis.com", "HTTP_JSON"),
    ("https://discoveryengine.mtls.googleapis.com", "HTTP_JSON"),
    ("https://modelarmor.us-central1.rep.googleapis.com", "HTTP_JSON"),
    ("https://modelarmor.us.rep.googleapis.com", "HTTP_JSON"),
    ("https://dlp.googleapis.com", "HTTP_JSON"),
    ("https://cloudresourcemanager.googleapis.com", "HTTP_JSON"),
    ("https://cloudresourcemanager.mtls.googleapis.com", "HTTP_JSON"),
    ("https://iamcredentials.googleapis.com", "HTTP_JSON"),
    ("https://iamcredentials.mtls.googleapis.com", "HTTP_JSON"),
    ("https://storage.googleapis.com", "HTTP_JSON"),
    ("https://telemetry.mtls.googleapis.com", "GRPC"),
    ("https://monitoring.googleapis.com", "HTTP_JSON"),
    ("https://trace.mtls.googleapis.com", "GRPC"),
    ("https://cloudtrace.googleapis.com", "HTTP_JSON"),
    ("https://logging.googleapis.com", "HTTP_JSON"),
    ("https://telemetry.googleapis.com", "HTTP_JSON"),
    ("https://secretmanager.googleapis.com", "HTTP_JSON"),
    ("https://sts.googleapis.com", "HTTP_JSON"),
    ("https://oauth2.googleapis.com", "HTTP_JSON"),
]


def main() -> None:
    cfg = load_config()
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    inventory_url = (
        cfg.inventory_mcp_url
        or state.get("inventory_mcp_url")
        or f"https://{cfg.dns_private_domain.rstrip('.')}/inventory/mcp"
    )
    oms_url = (
        cfg.oms_mcp_url
        or state.get("oms_mcp_url")
        or f"https://{cfg.dns_private_domain.rstrip('.')}/oms/mcp"
    )

    console.print(
        Panel(
            f"[bold cyan]Task 2: Register AWS Custom MCP Servers & Consolidated googleapis in Agent Registry[/bold cyan]\n"
            f"Project: [yellow]{cfg.project_id}[/yellow] | Registry Location: [green]{cfg.region}[/green]",
            border_style="cyan",
        )
    )

    inv_spec = REGISTRY_SPECS_DIR / "cymbal-store-inventory.toolspec.json"
    oms_spec = REGISTRY_SPECS_DIR / "cymbal-oms-order.toolspec.json"

    # 1. Register Store & Inventory MCP Server
    console.print(
        f"[bold]1. Registering [cyan]{cfg.inventory_mcp_registry_id}[/cyan] ({inventory_url})...[/bold]"
    )
    run_cmd(
        [
            "gcloud",
            "agent-registry",
            "services",
            "create",
            cfg.inventory_mcp_registry_id,
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--display-name=Cymbal AWS Store & Inventory MCP Server",
            "--description=Store stock lookup, catalog search, and VIP customer claim MCP server",
            "--mcp-server-spec-type=tool-spec",
            f"--mcp-server-spec-content={inv_spec}",
            f"--interfaces=url={inventory_url},protocolBinding=JSONRPC",
            "--quiet",
        ],
        check=False,
    )

    # 2. Register OMS Order Management MCP Server (with destructiveHint=true annotations)
    console.print(
        f"[bold]2. Registering [cyan]{cfg.oms_mcp_registry_id}[/cyan] ({oms_url})...[/bold]"
    )
    run_cmd(
        [
            "gcloud",
            "agent-registry",
            "services",
            "create",
            cfg.oms_mcp_registry_id,
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--display-name=Cymbal AWS OMS Order Management MCP Server",
            "--description=Purchase order query, order creation, and high-risk bulk cancellation MCP server",
            "--mcp-server-spec-type=tool-spec",
            f"--mcp-server-spec-content={oms_spec}",
            f"--interfaces=url={oms_url},protocolBinding=JSONRPC",
            "--quiet",
        ],
        check=False,
    )

    # 3. Register consolidated 'googleapis' service for ALL_TRAFFIC Agent Gateway mode
    console.print(
        f"[bold]3. Registering consolidated [cyan]{cfg.googleapis_registry_id}[/cyan] endpoint catalog ({len(GOOGLEAPIS_HOSTS)} FQDNs)...[/bold]"
    )
    interfaces_flags = [
        f"--interfaces=url={url},protocolBinding={proto}" for url, proto in GOOGLEAPIS_HOSTS
    ]
    run_cmd(
        [
            "gcloud",
            "agent-registry",
            "services",
            "create",
            cfg.googleapis_registry_id,
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--display-name=Google Cloud APIs (Consolidated)",
            "--description=Consolidated Google Cloud APIs catalog for Egress Agent Gateway in ALL_TRAFFIC mode",
            "--endpoint-spec-type=no-spec",
            *interfaces_flags,
            "--quiet",
        ],
        check=False,
    )

    # 4. Audit registered MCP servers and highlight destructive tools
    console.print("[bold]4. Auditing registered MCP Servers & Tool Risk Annotations...[/bold]")
    list_res = run_cmd(
        [
            "gcloud",
            "agent-registry",
            "mcp-servers",
            "list",
            f"--location={cfg.region}",
            f"--project={cfg.project_id}",
            "--format=json",
        ],
        check=False,
    )

    table = Table(title="Agent Registry MCP Catalog & Tool Risk Annotations (us-central1)", show_lines=True)
    table.add_column("MCP Server", style="cyan")
    table.add_column("Tool Name", style="white")
    table.add_column("readOnlyHint", justify="center")
    table.add_column("destructiveHint", justify="center")

    if list_res.returncode == 0 and list_res.stdout.strip():
        servers = json.loads(list_res.stdout)
        for srv in servers:
            srv_name = srv.get("displayName") or srv.get("name", "").split("/")[-1]
            for tool in srv.get("tools", []):
                ann = tool.get("annotations", {})
                ro = str(ann.get("readOnlyHint", False))
                destr = ann.get("destructiveHint", False)
                destr_str = "[bold red]TRUE (HIGH RISK)[/bold red]" if destr else "[green]False[/green]"
                table.add_row(srv_name, tool.get("name", ""), ro, destr_str)
    console.print(table)


if __name__ == "__main__":
    main()
