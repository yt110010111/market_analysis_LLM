# agents/data_extraction_agent/neo4j_storage.py

import os
import logging
import time
from typing import List, Dict, Any

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# -------------------------------------------------------------------
# Logger
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Neo4jStorage:
    """
    Neo4j 存儲管理器
    用於將資料萃取階段產生的實體（Entity）與關係（Relationship）
    存入 Neo4j 知識圖譜。
    """

    def __init__(self):
        self.uri = os.getenv("NEO4J_URL", "bolt://neo4j:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password123")
        self.driver = None

        self._connect_with_retry()

    # -------------------------------------------------------------------
    # Connection
    # -------------------------------------------------------------------
    def _connect_with_retry(self, max_retries: int = 5, retry_delay: int = 2):
        """
        建立 Neo4j 連線（含重試機制）
        """
        logger.info(f"🔗 嘗試連接 Neo4j: {self.uri}")

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"   第 {attempt}/{max_retries} 次嘗試...")

                self.driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                    max_connection_lifetime=3600,
                    max_connection_pool_size=50,
                    connection_timeout=10,
                    encrypted=False,
                )

                # 測試連線
                with self.driver.session() as session:
                    result = session.run("RETURN 1 AS test")
                    assert result.single()["test"] == 1

                logger.info("✅ Neo4j 連接成功")
                return

            except ServiceUnavailable as e:
                logger.warning(
                    f"⚠️ Neo4j 服務不可用 (嘗試 {attempt}/{max_retries}): {e}"
                )
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    logger.error("❌ Neo4j 連接失敗：達到最大重試次數")
                    self.driver = None

            except AuthError as e:
                logger.error(f"❌ Neo4j 認證失敗: {e}")
                self.driver = None
                return

            except Exception as e:
                logger.error(
                    f"❌ Neo4j 連接失敗 (嘗試 {attempt}/{max_retries}): {e}"
                )
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    self.driver = None

    # -------------------------------------------------------------------
    # Storage
    # -------------------------------------------------------------------
    def store_extraction_results(
        self,
        query: str,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        將萃取結果存入 Neo4j

        Args:
            query: 使用者查詢文字
            entities: 萃取出的實體列表
            relationships: 萃取出的關係列表

        Returns:
            存儲結果統計資訊
        """
        if not self.driver:
            logger.warning("⚠️ Neo4j 未連接，跳過存儲")
            return {"status": "skipped", "reason": "Neo4j not connected"}

        try:
            with self.driver.session() as session:
                # Step 1: Query Node
                session.run(
                    """
                    MERGE (q:Query {text: $query_text})
                    ON CREATE SET
                        q.created_at = timestamp(),
                        q.query_count = 1
                    ON MATCH SET
                        q.query_count = q.query_count + 1,
                        q.last_queried = timestamp()
                    """,
                    query_text=query,
                )

                # Step 2: Entity Nodes
                entities_created = 0
                for entity in entities:
                    try:
                        session.run(
                            """
                            MERGE (e:Entity {name: $name})
                            ON CREATE SET
                                e.type = $type,
                                e.description = $description,
                                e.source_url = $source_url,
                                e.source_title = $source_title,
                                e.importance = $importance,
                                e.created_at = timestamp()
                            ON MATCH SET
                                e.description = CASE
                                    WHEN size($description) > size(e.description)
                                    THEN $description
                                    ELSE e.description
                                END,
                                e.last_updated = timestamp()
                            WITH e
                            MATCH (q:Query {text: $query_text})
                            MERGE (q)-[:FOUND]->(e)
                            """,
                            name=entity.get("name", ""),
                            type=entity.get("type", "未分類"),
                            description=entity.get("description", ""),
                            source_url=entity.get("source_url", ""),
                            source_title=entity.get("source_title", ""),
                            importance=entity.get("importance", "medium"),
                            query_text=query,
                        )
                        entities_created += 1
                    except Exception as e:
                        logger.warning(
                            f"⚠️ 實體存儲失敗 {entity.get('name')}: {e}"
                        )

                logger.info(f"✅ 存儲了 {entities_created} 個實體")

                # Step 3: Relationship Edges
                relationships_created = 0
                for rel in relationships:
                    try:
                        session.run(
                            """
                            MATCH (source:Entity {name: $source_name})
                            MATCH (target:Entity {name: $target_name})
                            MERGE (source)-[r:RELATES_TO {type: $relation_type}]->(target)
                            ON CREATE SET
                                r.description = $description,
                                r.strength = $strength,
                                r.created_at = timestamp()
                            ON MATCH SET
                                r.last_seen = timestamp()
                            """,
                            source_name=rel.get("source", ""),
                            target_name=rel.get("target", ""),
                            relation_type=rel.get("relation", "相關"),
                            description=rel.get("description", ""),
                            strength=rel.get("strength", "medium"),
                        )
                        relationships_created += 1
                    except Exception as e:
                        logger.warning(f"⚠️ 關係存儲失敗: {e}")

                logger.info(f"✅ 存儲了 {relationships_created} 個關係")

                return {
                    "status": "success",
                    "entities_stored": entities_created,
                    "relationships_stored": relationships_created,
                }

        except Exception as e:
            logger.error(f"❌ Neo4j 存儲失敗: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------
    def close(self):
        """
        關閉 Neo4j 連線
        """
        if self.driver:
            self.driver.close()
            logger.info("Neo4j 連接已關閉")
