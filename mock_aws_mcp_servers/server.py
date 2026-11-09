#!/usr/bin/env python3
"""Simulated AWS-Hosted Enterprise FastMCP Servers (Store Inventory & OMS Order Management).

Exposes two MCP JSON-RPC / StreamableHTTP endpoints on a single container for the
Gemini Enterprise + Agent Registry + Egress Agent Gateway + Cloud/Model Armor + SDP lab:
  1. POST /inventory/mcp  -> Cymbal Store & Inventory MCP Server (cymbal-store-inventory-mcp)
  2. POST /oms/mcp        -> Cymbal OMS Order Management MCP Server (cymbal-oms-order-mcp)
  3. GET  /healthz        -> Health check endpoint for ALB / Cloud Run probes
  4. GET  /app-info       -> Server metadata & active security scenario test hints
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

try:
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    import uvicorn
    _HAS_STARLETTE = True
except ImportError:  # pragma: no cover - fallback when imported without starlette
    Starlette = None  # type: ignore[assignment]
    Request = Any  # type: ignore[assignment,misc]
    JSONResponse = dict  # type: ignore[assignment,misc]
    Route = None  # type: ignore[assignment]
    uvicorn = None  # type: ignore[assignment]
    _HAS_STARLETTE = False

BASE_DIR = Path(__file__).resolve().parent
PAYLOADS_DIR = BASE_DIR / "sample_payloads"

INVENTORY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_store_inventory",
        "description": "Retrieve real-time stock quantity and shelf status for a store and product SKU.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_id": {
                    "type": "string",
                    "description": "Store identifier (e.g., STORE-SEOUL-001, STORE-GANGNAM-002)",
                },
                "product_sku": {
                    "type": "string",
                    "description": "Product SKU or item keyword (e.g., SKU-LUNCHBOX-101, SKU-COFFEE-202)",
                },
            },
            "required": ["store_id", "product_sku"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "search_product_catalog",
        "description": "Search the enterprise product catalog by keyword and category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Product search keyword"},
                "category": {
                    "type": "string",
                    "description": "Product category (ALL, FOOD, BEVERAGE, HOUSEHOLD)",
                    "default": "ALL",
                },
            },
            "required": ["keyword"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "get_vip_customer_claim",
        "description": (
            "Fetch customer claim details by claim_id. "
            "Use CLM-NORMAL-1001 for clean data or CLM-PII-9001 to test SDP PII detection."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "Claim ticket ID (e.g., CLM-NORMAL-1001 or CLM-PII-9001)",
                }
            },
            "required": ["claim_id"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]

OMS_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_purchase_order",
        "description": (
            "Fetch purchase order status and supplier delivery notes by order_id. "
            "Use ORD-2026-5001 for normal order or ORD-INJ-9999 to test Model Armor Indirect Prompt Injection."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Purchase order ID (e.g., ORD-2026-5001 or ORD-INJ-9999)",
                }
            },
            "required": ["order_id"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "create_purchase_order",
        "description": "Create a standard replenishment purchase order for a store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "Target store ID"},
                "product_sku": {"type": "string", "description": "Product SKU to order"},
                "quantity": {"type": "integer", "description": "Order quantity (1-500)"},
            },
            "required": ["store_id", "product_sku", "quantity"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    },
    {
        "name": "cancel_all_store_orders",
        "description": (
            "[HIGH-RISK DESTRUCTIVE TOOL] Cancel all pending store replenishment orders across an entire region."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "region_code": {"type": "string", "description": "Target region code (e.g., KR-SEOUL, ALL)"},
                "reason": {"type": "string", "description": "Cancellation reason"},
            },
            "required": ["region_code", "reason"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    },
    {
        "name": "override_product_unit_price",
        "description": (
            "[HIGH-RISK DESTRUCTIVE TOOL] Force-override master unit price for a SKU in production OMS."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_sku": {"type": "string", "description": "Target product SKU"},
                "new_price": {"type": "number", "description": "New unit price in KRW"},
            },
            "required": ["product_sku", "new_price"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    },
]


def _execute_inventory_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool on the Store & Inventory MCP Server."""
    if name == "get_store_inventory":
        store_id = arguments.get("store_id", "STORE-SEOUL-001")
        product_sku = arguments.get("product_sku", "SKU-LUNCHBOX-101")
        return {
            "status": "SUCCESS",
            "source_system": "AWS-AP-NORTHEAST-2-INVENTORY-MCP",
            "store_id": store_id,
            "product_sku": product_sku,
            "product_name": "Cymbal Fresh Signature Lunchbox",
            "on_hand_quantity": 48,
            "safety_stock_threshold": 15,
            "restock_eta": "2026-11-10T06:00:00Z",
        }
    if name == "search_product_catalog":
        keyword = arguments.get("keyword", "")
        category = arguments.get("category", "ALL")
        return {
            "status": "SUCCESS",
            "keyword": keyword,
            "category": category,
            "items": [
                {
                    "sku": "SKU-LUNCHBOX-101",
                    "name": "Cymbal Fresh Signature Lunchbox",
                    "category": "FOOD",
                    "unit_price_krw": 5500,
                },
                {
                    "sku": "SKU-COFFEE-202",
                    "name": "Cymbal Single Origin Cold Brew 500ml",
                    "category": "BEVERAGE",
                    "unit_price_krw": 3200,
                },
            ],
        }
    if name == "get_vip_customer_claim":
        claim_id = arguments.get("claim_id", "CLM-NORMAL-1001").upper()
        if "PII" in claim_id or "9001" in claim_id:
            pii_file = PAYLOADS_DIR / "vip_claim_with_pii.json"
            if pii_file.exists():
                return json.loads(pii_file.read_text(encoding="utf-8"))
        return {
            "status": "SUCCESS",
            "claim_id": claim_id,
            "customer_tier": "VIP_GOLD",
            "summary": "Packaging seal inspection request for SKU-LUNCHBOX-101 (No sensitive PII attached).",
            "resolution_status": "IN_PROGRESS",
        }
    raise ValueError(f"Unknown inventory tool: {name}")


def _execute_oms_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool on the OMS Order Management MCP Server."""
    if name == "get_purchase_order":
        order_id = arguments.get("order_id", "ORD-2026-5001").upper()
        if "INJ" in order_id or "9999" in order_id:
            inj_file = PAYLOADS_DIR / "poisoned_order_note_injection.json"
            if inj_file.exists():
                return json.loads(inj_file.read_text(encoding="utf-8"))
        return {
            "status": "SUCCESS",
            "order_id": order_id,
            "store_id": "STORE-SEOUL-001",
            "product_sku": "SKU-LUNCHBOX-101",
            "quantity": 120,
            "order_state": "APPROVED_IN_TRANSIT",
            "supplier_note": "Standard morning cold-chain delivery scheduled for Dock B.",
        }
    if name == "create_purchase_order":
        return {
            "status": "CREATED",
            "order_id": f"ORD-2026-{datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S')}",
            "store_id": arguments.get("store_id", "STORE-SEOUL-001"),
            "product_sku": arguments.get("product_sku", "SKU-LUNCHBOX-101"),
            "quantity": arguments.get("quantity", 50),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    if name == "cancel_all_store_orders":
        return {
            "status": "DESTRUCTIVE_ACTION_EXECUTED",
            "warning": (
                "CRITICAL: All pending store orders in region "
                f"{arguments.get('region_code')} were wiped! "
                "(If you see this, Agent Gateway IAP Policy is not yet enforcing DENY on destructiveHint=true)"
            ),
        }
    if name == "override_product_unit_price":
        return {
            "status": "DESTRUCTIVE_ACTION_EXECUTED",
            "warning": (
                f"CRITICAL: Master price for {arguments.get('product_sku')} overridden to "
                f"{arguments.get('new_price')} KRW!"
            ),
        }
    raise ValueError(f"Unknown OMS tool: {name}")


async def _handle_mcp_jsonrpc(
    request: Request,
    server_name: str,
    tools_catalog: list[dict[str, Any]],
    executor_fn: Any,
) -> JSONResponse:
    """Handle MCP StreamableHTTP / JSON-RPC 2.0 requests (initialize, tools/list, tools/call)."""
    expected_token = os.getenv("MCP_AUTH_TOKEN", "").strip()
    req_token = (
        request.headers.get("X-MCP-Token")
        or request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    )
    if expected_token and req_token and req_token != expected_token:
        return JSONResponse(
            {"error": "Unauthorized MCP token"},
            status_code=401,
        )

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    rpc_id = body.get("id", 1)
    method = body.get("method", "")
    params = body.get("params") or {}

    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": server_name, "version": "1.0.0"},
                },
            }
        )

    if method == "notifications/initialized":
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": {}})

    if method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"tools": tools_catalog},
            }
        )

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            output = executor_fn(tool_name, arguments)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(output, ensure_ascii=False, indent=2),
                            }
                        ],
                        "isError": False,
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Tool execution error: {exc}"}],
                        "isError": True,
                    },
                }
            )

    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        },
        status_code=404,
    )


async def inventory_mcp_endpoint(request: Request) -> JSONResponse:
    """Endpoint for /inventory/mcp (Cymbal Store & Inventory MCP Server)."""
    return await _handle_mcp_jsonrpc(
        request,
        server_name="cymbal-store-inventory-mcp",
        tools_catalog=INVENTORY_TOOLS,
        executor_fn=_execute_inventory_tool,
    )


async def oms_mcp_endpoint(request: Request) -> JSONResponse:
    """Endpoint for /oms/mcp (Cymbal OMS Order Management MCP Server)."""
    return await _handle_mcp_jsonrpc(
        request,
        server_name="cymbal-oms-order-mcp",
        tools_catalog=OMS_TOOLS,
        executor_fn=_execute_oms_tool,
    )


async def healthz_endpoint(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "ok",
            "service": "simulated-aws-fastmcp-servers",
            "endpoints": ["/inventory/mcp", "/oms/mcp"],
            "client_ip": request.client.host if request.client else "unknown",
        }
    )


async def app_info_endpoint(request: Request) -> JSONResponse:
    """Server metadata endpoint."""
    return JSONResponse(
        {
            "service": "Simulated AWS Enterprise FastMCP Server Suite",
            "mcp_servers": {
                "cymbal-store-inventory-mcp": {
                    "path": "/inventory/mcp",
                    "tools": [t["name"] for t in INVENTORY_TOOLS],
                },
                "cymbal-oms-order-mcp": {
                    "path": "/oms/mcp",
                    "tools": [t["name"] for t in OMS_TOOLS],
                },
            },
        }
    )


app = (
    Starlette(
        debug=False,
        routes=[
            Route("/healthz", healthz_endpoint, methods=["GET"]),
            Route("/app-info", app_info_endpoint, methods=["GET"]),
            Route("/inventory/mcp", inventory_mcp_endpoint, methods=["POST", "GET"]),
            Route("/oms/mcp", oms_mcp_endpoint, methods=["POST", "GET"]),
        ],
    )
    if _HAS_STARLETTE
    else None
)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    if _HAS_STARLETTE and uvicorn is not None:
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        raise RuntimeError("Please install starlette and uvicorn (`uv sync`) to run the ASGI server.")
