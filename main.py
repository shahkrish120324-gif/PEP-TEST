from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from datetime import datetime

app = FastAPI(title="Realtime Message Hub")

# In-memory store (replace with DB later)
MESSAGES: List[dict] = []

class N8nMessage(BaseModel):
    chatId: str
    tenantPhone: str
    patientPhone: str
    message: str
    timestamp: str | None = None


@app.post("/webhook/n8n")
async def receive_from_n8n(payload: N8nMessage):
    msg = payload.dict()
    msg["receivedAt"] = datetime.utcnow().isoformat()

    MESSAGES.append(msg)
    print("📩 Message received from n8n:", msg)

    return {"ok": True}


@app.get("/messages/by-phone")
async def get_messages(patientPhone: str):
    results = [
        m for m in MESSAGES
        if m["patientPhone"] == patientPhone
    ]
    return {"messages": results}
