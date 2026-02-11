#!/usr/bin/env python3
"""
HTTP-based MCP Server for Medicine Ordering (SSE Transport)

Deployed on Render.com for Healthcare Clinical Decision Support agent.
Server URL: https://<your-render-url>/mcp
"""

import os
import json
from datetime import datetime
from typing import Any
from aiohttp import web

# Mock medicine database
MEDICINES = {
    "lisinopril": {"name": "Lisinopril", "dosages": ["5mg", "10mg", "20mg"], "price": 15.99, "category": "ACE Inhibitor"},
    "metformin": {"name": "Metformin", "dosages": ["500mg", "850mg", "1000mg"], "price": 12.50, "category": "Antidiabetic"},
    "atorvastatin": {"name": "Atorvastatin", "dosages": ["10mg", "20mg", "40mg"], "price": 18.75, "category": "Statin"},
    "omeprazole": {"name": "Omeprazole", "dosages": ["20mg", "40mg"], "price": 9.99, "category": "PPI"},
    "amlodipine": {"name": "Amlodipine", "dosages": ["5mg", "10mg"], "price": 14.25, "category": "Calcium Channel Blocker"},
    "ibuprofen": {"name": "Ibuprofen", "dosages": ["200mg", "400mg", "600mg"], "price": 8.50, "category": "NSAID"},
    "acetaminophen": {"name": "Acetaminophen", "dosages": ["325mg", "500mg", "650mg"], "price": 7.99, "category": "Analgesic"},
    "aspirin": {"name": "Aspirin", "dosages": ["81mg", "325mg"], "price": 6.99, "category": "NSAID/Antiplatelet"},
    "losartan": {"name": "Losartan", "dosages": ["25mg", "50mg", "100mg"], "price": 16.50, "category": "ARB"},
    "gabapentin": {"name": "Gabapentin", "dosages": ["100mg", "300mg", "600mg"], "price": 22.00, "category": "Anticonvulsant"},
}

# Mock orders storage
orders = []

# Tool definitions
TOOLS = [
    {
        "name": "search_medicines",
        "description": "Search for available medicines by name or category. Returns matching medicines with dosages and pricing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Medicine name or category to search for (e.g., 'metformin', 'NSAID', 'blood pressure')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "check_availability",
        "description": "Check if a specific medicine is available in stock and get detailed pricing information.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "medicine_name": {
                    "type": "string",
                    "description": "Name of the medicine to check (e.g., 'lisinopril', 'metformin')"
                },
                "dosage": {
                    "type": "string",
                    "description": "Optional: Specific dosage to check (e.g., '10mg', '500mg')"
                }
            },
            "required": ["medicine_name"]
        }
    },
    {
        "name": "place_order",
        "description": "Place an order for a medicine. Orders require physician approval before dispensing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "medicine_name": {
                    "type": "string",
                    "description": "Name of the medicine to order"
                },
                "dosage": {
                    "type": "string",
                    "description": "Dosage strength (e.g., '10mg', '500mg')"
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of units to order (default: 30)"
                },
                "patient_id": {
                    "type": "string",
                    "description": "Patient identifier for the order"
                }
            },
            "required": ["medicine_name", "dosage", "quantity"]
        }
    },
    {
        "name": "check_drug_interactions",
        "description": "Check for potential drug interactions between multiple medicines. Important for patient safety.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "medicines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of medicine names to check for interactions"
                }
            },
            "required": ["medicines"]
        }
    },
    {
        "name": "get_order_status",
        "description": "Check the status of a medicine order by order ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID to check (e.g., 'ORD-1001')"
                }
            },
            "required": ["order_id"]
        }
    }
]


def search_medicines(query: str) -> dict[str, Any]:
    query_lower = query.lower()
    results = []
    category_aliases = {
        "blood pressure": ["ace inhibitor", "arb", "calcium channel blocker"],
        "diabetes": ["antidiabetic"],
        "cholesterol": ["statin"],
        "pain": ["nsaid", "analgesic"],
    }
    search_terms = [query_lower]
    for alias, categories in category_aliases.items():
        if alias in query_lower:
            search_terms.extend(categories)
    for key, med in MEDICINES.items():
        for term in search_terms:
            if term in key or term in med["category"].lower() or term in med["name"].lower():
                if med not in [r["data"] for r in results]:
                    results.append({
                        "data": med,
                        "display": {
                            "name": med["name"],
                            "category": med["category"],
                            "available_dosages": med["dosages"],
                            "price_per_unit": f"${med['price']:.2f}"
                        }
                    })
                break
    if results:
        text = f"Found {len(results)} medicine(s) matching '{query}':\n\n"
        for i, r in enumerate(results, 1):
            d = r["display"]
            text += f"{i}. **{d['name']}** ({d['category']})\n"
            text += f"   Dosages: {', '.join(d['available_dosages'])}\n"
            text += f"   Price: {d['price_per_unit']} per unit\n\n"
    else:
        text = f"No medicines found matching '{query}'."
    return {"content": [{"type": "text", "text": text}]}


def check_availability(medicine_name: str, dosage: str = None) -> dict[str, Any]:
    med_key = medicine_name.lower().replace(" ", "")
    found_med = None
    for key, med in MEDICINES.items():
        if med_key in key or med_key in med["name"].lower().replace(" ", ""):
            found_med = med
            break
    if found_med:
        if dosage and dosage not in found_med["dosages"]:
            text = f"**{found_med['name']}** is available but NOT in {dosage} dosage.\n"
            text += f"Available dosages: {', '.join(found_med['dosages'])}\nPrice: ${found_med['price']:.2f} per unit"
        else:
            text = f"**{found_med['name']}** is IN STOCK\n"
            text += f"Category: {found_med['category']}\nDosages: {', '.join(found_med['dosages'])}\nPrice: ${found_med['price']:.2f} per unit"
            if dosage:
                text += f"\n{dosage} dosage is available for immediate order."
    else:
        text = f"**{medicine_name}** is NOT AVAILABLE in our pharmacy inventory."
    return {"content": [{"type": "text", "text": text}]}


def place_order(medicine_name: str, dosage: str, quantity: int, patient_id: str = "UNKNOWN") -> dict[str, Any]:
    med_key = medicine_name.lower().replace(" ", "")
    found_med = None
    for key, med in MEDICINES.items():
        if med_key in key or med_key in med["name"].lower().replace(" ", ""):
            found_med = med
            break
    if not found_med:
        return {"content": [{"type": "text", "text": f"Order Failed: {medicine_name} not found."}], "isError": True}
    if dosage not in found_med["dosages"]:
        return {"content": [{"type": "text", "text": f"Order Failed: {dosage} not valid for {found_med['name']}."}], "isError": True}
    order = {
        "order_id": f"ORD-{len(orders) + 1001}",
        "medicine": found_med["name"],
        "dosage": dosage,
        "quantity": quantity,
        "patient_id": patient_id,
        "unit_price": found_med["price"],
        "total_price": found_med["price"] * quantity,
        "status": "PENDING_PHYSICIAN_APPROVAL",
        "created_at": datetime.now().isoformat()
    }
    orders.append(order)
    text = f"ORDER PLACED\nOrder ID: {order['order_id']}\nMedicine: {order['medicine']} {order['dosage']}\n"
    text += f"Quantity: {order['quantity']} units\nTotal: ${order['total_price']:.2f}\nStatus: {order['status']}"
    return {"content": [{"type": "text", "text": text}]}


def check_drug_interactions(medicines: list[str]) -> dict[str, Any]:
    interactions = {
        ("lisinopril", "ibuprofen"): ("MODERATE", "NSAIDs may reduce the antihypertensive effect of ACE inhibitors and increase risk of kidney problems"),
        ("lisinopril", "aspirin"): ("MINOR", "Low-dose aspirin is generally safe with ACE inhibitors"),
        ("metformin", "ibuprofen"): ("MINOR", "NSAIDs may slightly increase risk of lactic acidosis with metformin"),
        ("atorvastatin", "amlodipine"): ("SAFE", "No significant interaction - commonly prescribed together"),
        ("lisinopril", "metformin"): ("SAFE", "Commonly prescribed together for diabetic patients with hypertension"),
        ("lisinopril", "losartan"): ("SEVERE", "Do NOT combine ACE inhibitors with ARBs - increased risk of hyperkalemia and kidney damage"),
        ("ibuprofen", "aspirin"): ("MODERATE", "NSAIDs may reduce cardioprotective effect of low-dose aspirin"),
        ("gabapentin", "opioids"): ("SEVERE", "Increased risk of respiratory depression - use with extreme caution"),
    }
    found_interactions = []
    medicines_lower = [m.lower().replace(" ", "") for m in medicines]
    for i, med1 in enumerate(medicines_lower):
        for med2 in medicines_lower[i+1:]:
            for (drug1, drug2), (severity, description) in interactions.items():
                if (drug1 in med1 or med1 in drug1) and (drug2 in med2 or med2 in drug2):
                    found_interactions.append({"drugs": f"{medicines[medicines_lower.index(med1)]} + {medicines[medicines_lower.index(med2)]}", "severity": severity, "description": description})
                elif (drug2 in med1 or med1 in drug2) and (drug1 in med2 or med2 in drug1):
                    found_interactions.append({"drugs": f"{medicines[medicines_lower.index(med1)]} + {medicines[medicines_lower.index(med2)]}", "severity": severity, "description": description})
    if found_interactions:
        severity_order = {"SEVERE": 0, "MODERATE": 1, "MINOR": 2, "SAFE": 3}
        found_interactions.sort(key=lambda x: severity_order.get(x["severity"], 4))
        text = f"Drug Interaction Check for: {', '.join(medicines)}\n\n"
        for interaction in found_interactions:
            text += f"[{interaction['severity']}] {interaction['drugs']}: {interaction['description']}\n\n"
    else:
        text = f"No known interactions found between: {', '.join(medicines)}"
    return {"content": [{"type": "text", "text": text}]}


def get_order_status(order_id: str) -> dict[str, Any]:
    for order in orders:
        if order["order_id"] == order_id:
            text = f"Order {order['order_id']}: {order['medicine']} {order['dosage']} x{order['quantity']} - {order['status']}"
            return {"content": [{"type": "text", "text": text}]}
    return {"content": [{"type": "text", "text": f"Order {order_id} not found."}], "isError": True}


def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "search_medicines":
        return search_medicines(arguments.get("query", ""))
    elif name == "check_availability":
        return check_availability(arguments.get("medicine_name", ""), arguments.get("dosage"))
    elif name == "place_order":
        return place_order(arguments.get("medicine_name", ""), arguments.get("dosage", ""), arguments.get("quantity", 30), arguments.get("patient_id", "UNKNOWN"))
    elif name == "check_drug_interactions":
        return check_drug_interactions(arguments.get("medicines", []))
    elif name == "get_order_status":
        return get_order_status(arguments.get("order_id", ""))
    else:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}


async def handle_mcp_request(request: web.Request) -> web.StreamResponse:
    """Handle MCP JSON-RPC request with SSE response."""
    try:
        body = await request.json()
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id")

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "medicine-order-server", "version": "1.0.0", "description": "Medicine ordering and drug interaction checking"}
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = handle_tool_call(params.get("name", ""), params.get("arguments", {}))
    else:
        result = {"error": {"code": -32601, "message": f"Unknown method: {method}"}}

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )
    await response.prepare(request)

    message = {"jsonrpc": "2.0", "id": request_id, "result": result}
    event_data = f"event: message\ndata: {json.dumps(message)}\n\n"
    await response.write(event_data.encode())

    return response


async def handle_cors_preflight(request: web.Request) -> web.Response:
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint for Render."""
    return web.json_response({"status": "ok", "service": "mcp-medicine-server"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_post("/mcp", handle_mcp_request)
    app.router.add_options("/mcp", handle_cors_preflight)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    print(f"Medicine Order MCP Server starting on port {port}")
    print(f"MCP endpoint: http://0.0.0.0:{port}/mcp")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)
