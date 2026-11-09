#!/usr/bin/env python3
"""[Task 4 & 5] Lock Cloud Armor to Agent Gateway NAT IP, create Model Armor Templates (us & us-central1) + SDP ContentPolicy (BigQuery Log), and bind IAP Authz (DENY destructiveHint=true)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import bigquery
from rich.panel import Panel
from rich.table import Table
from scripts.common import POLICIES_DIR, STATE_FILE, api_request, console, load_config, run_cmd


def _ensure_bigquery_audit_dataset(cfg) -> None:
    """Create BigQuery dataset for SDP ContentPolicyActionLog if not exists."""
    client = bigquery.Client(project=cfg.project_id)
    dataset_ref = f"{cfg.project_id}.{cfg.bq_dataset_id}"
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = cfg.bq_location
    client.create_dataset(dataset, exists_ok=True)
    console.print(f"  [green]Verified BigQuery Audit Dataset:[/green] {dataset_ref}")


def main() -> None:
    cfg = load_config()
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    nat_ip = state.get("nat_static_ip", "")

    console.print(
        Panel(
            f"[bold cyan]Task 4 & 5: Bind Cloud Armor, IAP Tool Authz, Model Armor & SDP Content Policy[/bold cyan]\n"
            f"Project: [yellow]{cfg.project_id}[/yellow] | "
            f"Model Armor Mode: [green]{cfg.model_armor_enforcement}[/green] | "
            f"SDP Verdict: [magenta]{cfg.sdp_verdict}[/magenta]",
            border_style="cyan",
        )
    )

    # 1. Update Cloud Armor Priority 1000 Rule with Agent Gateway Cloud NAT Static IP (/32)
    if nat_ip:
        console.print(
            f"[bold]1. Updating Cloud Armor ([cyan]{cfg.cloud_armor_policy_name}[/cyan]) to allow Agent Gateway Static NAT IP ([green]{nat_ip}/32[/green])...[/bold]"
        )
        run_cmd(
            [
                "gcloud",
                "compute",
                "security-policies",
                "rules",
                "create",
                "1000",
                f"--security-policy={cfg.cloud_armor_policy_name}",
                f"--project={cfg.project_id}",
                f"--src-ip-ranges={nat_ip}/32",
                "--action=allow",
                "--description=Allow Egress Agent Gateway Static Cloud NAT IP",
            ],
            check=False,
        )

    # 2. Create Model Armor Templates in 'us' (for GE Assistant) and 'us-central1' (for Agent Gateway CONTENT_AUTHZ)
    console.print("[bold]2. Creating Model Armor Templates (locations/us & locations/us-central1)...[/bold]")
    for loc, tmpl_id, json_file in (
        (cfg.ma_ge_location, cfg.ma_ge_template_id, "ge_assistant_template_us.json"),
        (cfg.ma_agw_location, cfg.ma_agw_template_id, "agw_inline_template_usc1.json"),
    ):
        raw_json = (POLICIES_DIR / "model_armor" / json_file).read_text(encoding="utf-8")
        body = json.loads(raw_json.replace("${MODEL_ARMOR_ENFORCEMENT}", cfg.model_armor_enforcement))
        ma_url = f"https://modelarmor.{loc}.rep.googleapis.com/v1/projects/{cfg.project_id}/locations/{loc}/templates"
        resp = api_request("POST", ma_url, cfg, json_body=body, params={"templateId": tmpl_id})
        if resp.status_code in (200, 201, 409):
            console.print(f"  [green]Model Armor Template ready:[/green] projects/{cfg.project_id}/locations/{loc}/templates/{tmpl_id}")
        else:
            console.print(f"  [yellow]Model Armor ({loc}) status {resp.status_code}: {resp.text[:200]}[/yellow]")

    # 3. Create BigQuery Dataset & Cloud DLP SDP Content Policy
    console.print("[bold]3. Creating BigQuery Audit Dataset & SDP Content Policy (KOREA_RRN, CREDIT_CARD_NUMBER)...[/bold]")
    _ensure_bigquery_audit_dataset(cfg)

    # Grant DLP Service Agent BigQuery Data Editor role
    run_cmd(["gcloud", "beta", "services", "identity", "create", "--service=dlp.googleapis.com", f"--project={cfg.project_id}"], check=False)
    dlp_sa = f"serviceAccount:service-{cfg.project_number}@dlp-api.iam.gserviceaccount.com"
    run_cmd(
        [
            "gcloud",
            "projects",
            "add-iam-policy-binding",
            cfg.project_id,
            f"--member={dlp_sa}",
            "--role=roles/bigquery.dataEditor",
            "--condition=None",
            "--quiet",
        ],
        check=False,
    )

    sdp_raw = (POLICIES_DIR / "sdp" / "ge_sdp_content_policy.json").read_text(encoding="utf-8")
    sdp_str = (
        sdp_raw.replace("${SDP_POLICY_ID}", cfg.sdp_policy_id)
        .replace("${SDP_VERDICT}", cfg.sdp_verdict)
        .replace("${PROJECT_ID}", cfg.project_id)
        .replace("${BQ_DATASET_ID}", cfg.bq_dataset_id)
        .replace("${BQ_TABLE_ID}", cfg.bq_table_id)
    )
    sdp_body = json.loads(sdp_str)
    dlp_url = f"https://dlp.googleapis.com/v2/projects/{cfg.project_id}/locations/{cfg.ge_location}/contentPolicies"
    sdp_resp = api_request("POST", dlp_url, cfg, json_body=sdp_body)
    if sdp_resp.status_code in (200, 201, 409):
        console.print(
            f"  [green]SDP Content Policy ready:[/green] projects/{cfg.project_id}/locations/{cfg.ge_location}/contentPolicies/{cfg.sdp_policy_id}"
        )
    else:
        console.print(f"  [yellow]SDP ContentPolicy response ({sdp_resp.status_code}): {sdp_resp.text[:200]}[/yellow]")

    # 4. Bind IAP Authorization (DENY destructiveHint=true) on Agent Registry & Agent Gateway
    console.print("[bold]4. Binding IAP Tool-Level Authorization Policy (ALLOW read/create, DENY destructiveHint=true)...[/bold]")
    # Track B (Zero-Org-Policy IAP V1 binding on Agent Registry resources)
    for mcp_id in (cfg.inventory_mcp_registry_id, cfg.oms_mcp_registry_id):
        desc = run_cmd(
            [
                "gcloud",
                "agent-registry",
                "mcp-servers",
                "describe",
                mcp_id,
                f"--project={cfg.project_id}",
                f"--location={cfg.region}",
                "--format=value(registryResource)",
            ],
            check=False,
        )
        reg_uuid = Path(desc.stdout.strip()).name if desc.returncode == 0 and desc.stdout.strip() else mcp_id
        run_cmd(
            [
                "gcloud",
                "iap",
                "web",
                "add-iam-policy-binding",
                f"--project={cfg.project_id}",
                f"--region={cfg.region}",
                "--resource-type=agent-registry",
                f"--mcp-server={reg_uuid}",
                f"--member=serviceAccount:service-{cfg.project_number}@gcp-sa-discoveryengine.iam.gserviceaccount.com",
                "--role=roles/iap.egressor",
                "--condition=^:^expression=api.getAttribute('iap.googleapis.com/mcp.tool.isDestructive', false) == false:title=DenyDestructiveTools",
                "--quiet",
            ],
            check=False,
        )

    # Also deploy AuthzExtension & AuthzPolicy for Agent Gateway
    with tempfile.TemporaryDirectory() as tmpdir:
        ext_path = Path(tmpdir) / "iap_ext.yaml"
        ext_yaml = (
            (POLICIES_DIR / "iap_authz" / "iap_request_authz_ext.yaml")
            .read_text(encoding="utf-8")
            .replace("${PROJECT_NUMBER}", cfg.project_number)
            .replace("${REGION}", cfg.region)
            .replace("${IAP_AUTHZ_EXT_ID}", cfg.iap_authz_ext_id)
            .replace("${IAP_POLICY_VERSION}", "V2" if cfg.iap_authz_mode == "V2_UAP" else "V1")
        )
        ext_path.write_text(ext_yaml, encoding="utf-8")
        run_cmd(
            [
                "gcloud",
                "service-extensions",
                "authz-extensions",
                "import",
                cfg.iap_authz_ext_id,
                f"--source={ext_path}",
                f"--location={cfg.region}",
                f"--project={cfg.project_id}",
                "--quiet",
            ],
            check=False,
        )

        pol_path = Path(tmpdir) / "agw_authz.yaml"
        pol_yaml = (
            (POLICIES_DIR / "iap_authz" / "agw_authz_policy.yaml")
            .read_text(encoding="utf-8")
            .replace("${PROJECT_NUMBER}", cfg.project_number)
            .replace("${REGION}", cfg.region)
            .replace("${IAP_AUTHZ_POLICY_ID}", cfg.iap_authz_policy_id)
            .replace("${AGENT_GATEWAY_ID}", cfg.agent_gateway_id)
            .replace("${IAP_AUTHZ_EXT_ID}", cfg.iap_authz_ext_id)
        )
        pol_path.write_text(pol_yaml, encoding="utf-8")
        run_cmd(
            [
                "gcloud",
                "beta",
                "network-security",
                "authz-policies",
                "import",
                cfg.iap_authz_policy_id,
                f"--source={pol_path}",
                f"--location={cfg.region}",
                f"--project={cfg.project_id}",
                "--quiet",
            ],
            check=False,
        )

    table = Table(title="Task 4 & 5 Security Governance Summary", show_lines=True)
    table.add_column("Security Layer", style="cyan")
    table.add_column("Resource Name", style="green")
    table.add_column("Enforcement Rule", style="yellow")
    table.add_row("Layer 1: Google Cloud Armor WAF", cfg.cloud_armor_policy_name, f"Allow Agent GW NAT ({nat_ip or '/32'}) & Valid Token; Deny 403 Bypass")
    table.add_row("Layer 2: IAP Request Authz", cfg.iap_authz_policy_id, "ALLOW Read/Standard MCP; DENY 403 destructiveHint=true")
    table.add_row("Layer 3A: Model Armor (GE & AGW)", f"{cfg.ma_ge_template_id} / {cfg.ma_agw_template_id}", f"{cfg.model_armor_enforcement} (PI/Jailbreak + SDP)")
    table.add_row("Layer 3B: SDP Content Policy", cfg.sdp_policy_id, f"Verdict={cfg.sdp_verdict} + Log to BigQuery ({cfg.bq_dataset_id}.{cfg.bq_table_id})")
    console.print(table)


if __name__ == "__main__":
    main()
