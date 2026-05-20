import uuid
from typing import Any, Dict


def get_text_from_a2a(req: Dict[str, Any]) -> str:
    params = req.get("params", req)
    message = params.get("message", {})
    parts = message.get("parts", [])

    texts = []
    for part in parts:
        if "text" in part:
            texts.append(part["text"])
        elif part.get("kind") == "text":
            texts.append(part.get("text", ""))

    return "\n".join(texts).strip()


def a2a_response(result_text: str, request_id: Any = None) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id or str(uuid.uuid4()),
        "result": {
            "id": str(uuid.uuid4()),
            "contextId": str(uuid.uuid4()),
            "status": {"state": "completed"},
            "artifacts": [
                {
                    "parts": [
                        {
                            "kind": "text",
                            "text": result_text
                        }
                    ]
                }
            ]
        }
    }


def a2a_error(message: str, request_id: Any = None) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32000,
            "message": message
        }
    }