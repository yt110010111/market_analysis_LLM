from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import logging
from agent import DataExtractionAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Extraction Agent")

agent = DataExtractionAgent()


class ExtractionRequest(BaseModel):
    data: Dict[str, Any]
    query: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": agent.model_name
    }


@app.post("/extract")
def extract(req: ExtractionRequest):
    try:
        logger.info(f"📥 Extract request: {req.query}")
        return agent.extract_and_analyze(req.data, req.query)
    except Exception as e:
        logger.exception("❌ Extraction failed")
        raise HTTPException(status_code=500, detail=str(e))
