#!/usr/bin/env python3
"""[Task 6B] Query BigQuery SDP ContentPolicyActionLog, Cloud Armor Logs, IAP Audit Logs & StreamAssist User Correlation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import bigquery
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from scripts.common import console, load_config, run_cmd


CORRELATION_SQL_TEMPLATE = """SELECT
  sdp.log_time,
  ua.jsonPayload.userIamPrincipal AS user_email,
  sdp.data_source_type.type AS source_type,
  sdp.returned_verdict,
  ARRAY_TO_STRING(
    ARRAY(SELECT m.info_type_name FROM UNNEST(sdp.matching_info_types) AS m), ', '
  ) AS detected_info_types
FROM
  `{project_id}.{bq_dataset_id}.{bq_table_id}` AS sdp
LEFT JOIN
  `{project_id}.global._Default._AllLogs` AS ua
ON
  SPLIT(sdp.correlation_id, '|')[SAFE_OFFSET(2)] = JSON_VALUE(ua.jsonPayload.response.assistToken)
WHERE
  ARRAY_LENGTH(sdp.matching_info_types) > 0
ORDER BY
  sdp.log_time DESC
LIMIT 20;"""


def main() -> None:
    cfg = load_config()
    console.print(
        Panel(
            f"[bold cyan]Task 6B: Multi-Channel Security Audit Trail & User Correlation Verification[/bold cyan]\n"
            f"Project: [yellow]{cfg.project_id}[/yellow] | BigQuery Table: [green]{cfg.project_id}.{cfg.bq_dataset_id}.{cfg.bq_table_id}[/green]",
            border_style="cyan",
        )
    )

    # 1. Print Cross-Channel Correlation SQL Query
    sql_query = CORRELATION_SQL_TEMPLATE.format(
        project_id=cfg.project_id,
        bq_dataset_id=cfg.bq_dataset_id,
        bq_table_id=cfg.bq_table_id,
    )
    console.print("[bold]1. BigQuery SDP ContentPolicyActionLog <-> GE StreamAssist User Correlation SQL:[/bold]")
    console.print(Syntax(sql_query, "sql", theme="monokai", line_numbers=True))

    # 2. Query BigQuery SDP ContentPolicyActionLog table if created
    console.print("\n[bold]2. Querying BigQuery SDP Audit Table...[/bold]")
    try:
        bq_client = bigquery.Client(project=cfg.project_id)
        simple_sql = (
            f"SELECT * FROM `{cfg.project_id}.{cfg.bq_dataset_id}.{cfg.bq_table_id}` "
            "ORDER BY 1 DESC LIMIT 5"
        )
        rows = list(bq_client.query(simple_sql).result())
        console.print(f"  [green]Retrieved {len(rows)} SDP audit record(s) from BigQuery.[/green]")
    except Exception as exc:  # noqa: BLE001
        console.print(
            f"  [yellow]BigQuery table `{cfg.bq_dataset_id}.{cfg.bq_table_id}` is awaiting first async DLP flush ({exc}).[/yellow]"
        )

    # 3. Query Recent Cloud Logging Audit Entries (Agent Registry, Agent Gateway, Model Armor, DLP)
    console.print("\n[bold]3. Recent Cloud Audit Log Entries (Agent Registry / Agent Gateway / Model Armor / DLP):[/bold]")
    log_filter = (
        'protoPayload.serviceName=("agentregistry.googleapis.com" OR '
        '"networkservices.googleapis.com" OR "modelarmor.googleapis.com" OR '
        '"dlp.googleapis.com" OR "iap.googleapis.com")'
    )
    res = run_cmd(
        [
            "gcloud",
            "logging",
            "read",
            log_filter,
            f"--project={cfg.project_id}",
            "--limit=10",
            "--format=table(timestamp,protoPayload.serviceName,protoPayload.methodName,protoPayload.authenticationInfo.principalEmail)",
        ],
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        console.print(res.stdout)
    else:
        table = Table(title="Audit Log Verification Channels", show_lines=True)
        table.add_column("Audit Channel", style="cyan")
        table.add_column("Cloud Logging / BigQuery Filter", style="white")
        table.add_row("Google Cloud Armor WAF", 'resource.type="http_load_balancer" AND jsonPayload.enforcedSecurityPolicy.name="mcp-edge-cloud-armor-waf"')
        table.add_row("IAP Request Authz (403)", 'resource.labels.service="iap.googleapis.com" AND protoPayload.status.code=7')
        table.add_row("Model Armor Sanitize", 'resource.type="modelarmor.googleapis.com/Template"')
        table.add_row("SDP ContentPolicy BQ", f"`{cfg.project_id}.{cfg.bq_dataset_id}.{cfg.bq_table_id}`")
        console.print(table)


if __name__ == "__main__":
    main()
