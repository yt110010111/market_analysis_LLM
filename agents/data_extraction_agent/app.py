# agents/data_extraction_agent/app.py

import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import DataExtractionAgent
from neo4j_storage import Neo4jStorage

# -------------------------------------------------------------------
# Logger
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# App & Services
# -------------------------------------------------------------------
app = FastAPI(title="Data Extraction Agent")

agent = DataExtractionAgent()
storage = Neo4jStorage()

# -------------------------------------------------------------------
# Schemas
# -------------------------------------------------------------------
class ExtractionRequest(BaseModel):
    query: str
    data: Dict[str, Any]

# -------------------------------------------------------------------
# Health Check
# -------------------------------------------------------------------
@app.get("/health")
def health():
    """
    Service health check
    """
    return {
        "status": "ok",
        "model": agent.model_name,
    }

# -------------------------------------------------------------------
# Main API
# -------------------------------------------------------------------
@app.post("/extract")
def extract(req: ExtractionRequest):
    """
    Execute data extraction and store results in Neo4j
    """
    logger.info(f"📥 Extract request received: {req.query}")

    try:
        # Step 1: Entity & relationship extraction
        extraction_result = agent.extract_and_analyze(
            req.data,
            req.query,
        )

        # Step 2: Neo4j storage (best-effort)
        if extraction_result.get("status") == "success":
            entities = extraction_result.get("entities", [])
            relationships = extraction_result.get("relationships", [])

            logger.info(
                f"💾 Preparing Neo4j storage: "
                f"{len(entities)} entities, {len(relationships)} relationships"
            )

            try:
                storage_result = storage.store_extraction_results(
                    query=req.query,
                    entities=entities,
                    relationships=relationships,
                )

                extraction_result["neo4j_storage"] = storage_result
                logger.info(f"✅ Neo4j storage completed: {storage_result}")

            except Exception as e:
                logger.error("❌ Neo4j storage failed", exc_info=True)
                extraction_result["neo4j_storage"] = {
                    "status": "error",
                    "error": str(e),
                }

        return extraction_result

    except Exception as e:
        logger.exception("❌ Extraction pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# Shutdown
# -------------------------------------------------------------------
@app.on_event("shutdown")
def shutdown_event():
    """
    Gracefully close Neo4j connection
    """
    storage.close()
