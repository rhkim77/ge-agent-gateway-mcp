#!/usr/bin/env python3
"""GitWhisperer V2 Pre-Flight Validator & Customer-Agnostic Sanitization Checker."""

from __future__ import annotations

import os
import re
import sys
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN_CUSTOMER_TERMS = ("gsretail", "gs retail", "gs리테일", "gs_retail")


def check_customer_agnostic_cleanliness() -> list[str]:
    """Ensure zero customer-specific names appear anywhere in the repository."""
    errors: list[str] = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", ".venv", "venv", "__pycache__")]
        for fname in files:
            if fname == "validate_bundle.py" or fname.endswith((".png", ".jpg", ".pyc", ".zip")):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                for term in FORBIDDEN_CUSTOMER_TERMS:
                    if term in content:
                        rel = os.path.relpath(fpath, REPO_ROOT)
                        errors.append(f"[Brand Sanitization] Forbidden term '{term}' found in {rel}")
            except Exception:  # noqa: BLE001
                pass
    return errors


def check_instruction_md(md_path: str, expected_steps: int) -> tuple[list[str], int]:
    errors: list[str] = []
    img_dir = os.path.join(os.path.dirname(md_path), "img")
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    in_code = False
    h1_lines = []
    img_refs = []
    rel_links = []
    unconverted_alerts = []
    tracking_steps = []

    img_re = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
    link_re = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    alert_re = re.compile(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", re.IGNORECASE)
    track_re = re.compile(r"<ql-activity-tracking\s+step=(\d+)\s*>")

    for idx, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            if not in_code and line.strip() == "```prompt":
                errors.append(f"{md_path}:{idx}: Unconverted ```prompt fence found")
            in_code = not in_code
            continue

        if not in_code:
            if re.match(r"^#\s+", line):
                h1_lines.append((idx, line.strip()))
            if alert_re.match(line):
                unconverted_alerts.append(idx)
            for m in img_re.finditer(line):
                img_refs.append((idx, m.group(1)))
            for m in link_re.finditer(line):
                target = m.group(1)
                if target.startswith("../") or target.startswith("./"):
                    rel_links.append((idx, target))
            for m in track_re.finditer(line):
                tracking_steps.append(int(m.group(1)))

    if len(h1_lines) != 1:
        errors.append(f"[One title] {md_path}: Expected exactly 1 H1 title, found {len(h1_lines)}: {h1_lines}")

    for line_no, img_target in img_refs:
        if not img_target.startswith("./img/"):
            errors.append(f"[Dead end navigation] {md_path}:{line_no}: Image '{img_target}' does not use './img/' prefix")
        else:
            img_file = os.path.join(img_dir, os.path.basename(img_target))
            if not os.path.isfile(img_file):
                errors.append(f"[Dead end navigation] {md_path}:{line_no}: Missing image file '{img_file}'")

    for line_no, rel_target in rel_links:
        errors.append(f"[Dead end navigation] {md_path}:{line_no}: Relative link '{rel_target}' is not allowed in Qwiklabs bundle")

    if unconverted_alerts:
        errors.append(f"[Custom Boxes] {md_path}: Unconverted GitHub alerts at lines {unconverted_alerts}")

    expected_list = list(range(1, expected_steps + 1))
    if tracking_steps != expected_list:
        errors.append(
            f"[Activity Tracking] {md_path}: Expected steps {expected_list}, found {tracking_steps}"
        )

    return errors, len(img_refs)


def validate_lab(lab_dir: str) -> list[str]:
    lab_name = os.path.basename(lab_dir)
    errors: list[str] = []
    print(f"\n=== Validating Lab Bundle: {lab_name} ===")

    owner_path = os.path.join(lab_dir, "QL_OWNER")
    if not os.path.isfile(owner_path):
        errors.append(f"{lab_name}: Missing QL_OWNER file")
    else:
        with open(owner_path, "r", encoding="utf-8") as f:
            owners = [l.split("#")[0].strip() for l in f if l.split("#")[0].strip()]
        if not owners or any("@" not in o for o in owners):
            errors.append(f"{lab_name}: Invalid QL_OWNER content: {owners}")
        else:
            print(f"  [PASS] QL_OWNER ({len(owners)} owner/collaborator emails: {', '.join(owners)})")

    ql_yaml_path = os.path.join(lab_dir, "qwiklabs.yaml")
    with open(ql_yaml_path, "r", encoding="utf-8") as f:
        ql_cfg = yaml.safe_load(f)

    req_keys = [
        "entity_type",
        "schema_version",
        "default_locale",
        "title",
        "description",
        "duration",
        "max_duration",
        "level",
        "credits",
        "instruction",
        "environment",
        "assessment",
    ]
    missing_keys = [k for k in req_keys if k not in ql_cfg]
    if missing_keys:
        errors.append(f"{lab_name}/qwiklabs.yaml: Missing required keys: {missing_keys}")

    for idx, res in enumerate(ql_cfg.get("resources", [])):
        for r_key in ("id", "type", "title", "uri"):
            if r_key not in res:
                errors.append(f"{lab_name}/qwiklabs.yaml: Element `{idx}` under key `resources` is missing `{r_key}` field")

    svos = ql_cfg.get("environment", {}).get("student_visible_outputs", [])
    refs = [s.get("reference") for s in svos]
    if "project_0.console_url" not in refs:
        errors.append(f"{lab_name}/qwiklabs.yaml: student_visible_outputs must include 'project_0.console_url'")

    print(
        f"  [PASS] qwiklabs.yaml V2 schema (schema_version={ql_cfg['schema_version']}, "
        f"resources={len(ql_cfg.get('resources', []))} with id/type, startup_script.type=qwiklabs)"
    )

    tf_dir = os.path.join(lab_dir, "terraform")
    tf_req_files = [
        "runtime.yaml",
        "variables.tf",
        "provider.tf",
        "apis.tf",
        "iam.tf",
        "antigravity.tf",
        "proxy.tf",
        "main.tf",
        "outputs.tf",
        "scripts/startup.sh",
    ]
    for tf_file in tf_req_files:
        if not os.path.isfile(os.path.join(tf_dir, tf_file)):
            errors.append(f"{lab_name}/terraform: Missing mandatory file '{tf_file}'")

    with open(os.path.join(tf_dir, "variables.tf"), "r", encoding="utf-8") as f:
        vars_content = f.read()
    for req_var in ("gcp_project_id", "gcp_region", "gcp_zone"):
        if f'variable "{req_var}"' not in vars_content:
            errors.append(f"{lab_name}/terraform/variables.tf: Missing mandatory Qwiklabs variable '{req_var}'")

    with open(os.path.join(tf_dir, "outputs.tf"), "r", encoding="utf-8") as f:
        outputs_content = f.read()
    for svo in svos:
        ref = svo.get("reference", "")
        if ref.startswith("project_0.startup_script."):
            out_name = ref.split("project_0.startup_script.")[1]
            if f'output "{out_name}"' not in outputs_content:
                errors.append(f"{lab_name}: student_visible_output '{ref}' not found in terraform/outputs.tf")

    print(f"  [PASS] terraform/ {len(tf_req_files)} modular files & Qwiklabs variable/output bindings verified")

    assess_yaml_path = os.path.join(lab_dir, ql_cfg["assessment"])
    with open(assess_yaml_path, "r", encoding="utf-8") as f:
        assess_cfg = yaml.safe_load(f)

    steps = assess_cfg.get("steps", [])
    locale_ids = set()
    for idx, step in enumerate(steps, 1):
        lid = step.get("locale_id")
        if not lid or lid in locale_ids:
            errors.append(f"{lab_name}/assessment.yaml: Step {idx} has missing or duplicate locale_id '{lid}'")
        locale_ids.add(lid)

        smsgs = step.get("student_messages")
        if not isinstance(smsgs, dict) or "success" not in smsgs or "error_message" not in smsgs:
            errors.append(
                f"{lab_name}/assessment.yaml: Step {idx} student_messages must be a dict with 'success' and 'error_message'"
            )

        for svc in step.get("services", []):
            if "." not in svc:
                errors.append(f"{lab_name}/assessment.yaml: Step {idx} service '{svc}' must be prefixed with resource id")

        method_name = step.get("method_name")
        rb_path = os.path.join(lab_dir, "assessments", f"{method_name}.rb")
        if not os.path.isfile(rb_path):
            errors.append(f"{lab_name}: Missing Ruby script assessments/{method_name}.rb for step {idx}")
        else:
            with open(rb_path, "r", encoding="utf-8") as f:
                rb_content = f.read()
            if f"def {method_name}(" not in rb_content:
                errors.append(f"{lab_name}: Function 'def {method_name}(' not found in assessments/{method_name}.rb")

    print(f"  [PASS] assessment.yaml V2 schema & {len(steps)} Ruby assessment scripts verified")

    inst_uri = ql_cfg.get("instruction", {}).get("uri", "instructions/en.md")
    md_path = os.path.join(lab_dir, inst_uri)
    md_errors, img_count = check_instruction_md(md_path, expected_steps=len(steps))
    errors.extend(md_errors)
    if not md_errors:
        print(
            f"  [PASS] {inst_uri}: 1 H1 title, {img_count} valid './img/' links, "
            f"{len(steps)} activity-tracking steps, 0 dead-end links"
        )

    return errors


def main() -> None:
    all_errors: list[str] = []

    brand_errors = check_customer_agnostic_cleanliness()
    all_errors.extend(brand_errors)
    if not brand_errors:
        print("=== Customer-Agnostic Sanitization Check ===")
        print("  [PASS] 0 customer-specific brand names found across all repository files")

    labs_root = os.path.join(REPO_ROOT, "labs")
    for slug in sorted(os.listdir(labs_root)):
        lab_dir = os.path.join(labs_root, slug)
        if os.path.isdir(lab_dir):
            all_errors.extend(validate_lab(lab_dir))

    ct_yaml = os.path.join(REPO_ROOT, "classroom_templates/ge-agent-gateway-mcp-governance/qwiklabs.yaml")
    with open(ct_yaml, "r", encoding="utf-8") as f:
        ct_cfg = yaml.safe_load(f)
    if ct_cfg.get("entity_type") != "ClassroomTemplate":
        all_errors.append("classroom_templates/ge-agent-gateway-mcp-governance/qwiklabs.yaml: Invalid entity_type")
    else:
        print("\n=== Validating ClassroomTemplate: ge-agent-gateway-mcp-governance ===")
        print(f"  [PASS] ClassroomTemplate links {len(ct_cfg.get('labs', []))} lab(s)")

    if all_errors:
        print("\n[FAIL] Validation failed with errors:")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)

    print("\n======================================================================")
    print("ALL QWIKLABS V2 & CUSTOMER-AGNOSTIC CHECKS PASSED (0 ERRORS)!")
    print("======================================================================")


if __name__ == "__main__":
    main()
