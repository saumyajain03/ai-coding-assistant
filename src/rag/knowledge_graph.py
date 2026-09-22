"""
Local Knowledge Graph Engine
Zero-cost, lightweight graph database backed by SQLite and in-memory adjacency index.
Supports multi-hop traversal, entity relationships (IMPORTS, DEFINES, CALLS, etc.),
and strict provenance metadata preservation.
"""

import sqlite3
from collections import deque
from pathlib import Path

from pydantic import BaseModel

from src.config import get_settings


class GraphNode(BaseModel):
    id: str
    name: str
    node_type: str  # FILE, MODULE, CLASS, FUNCTION, METHOD, VARIABLE, CONFIG, DOC_SECTION, TEST
    filename: str
    file_type: str
    start_line: int = 1
    end_line: int = 1
    page: int | None = None
    section: str | None = None
    sha256: str = ""
    doc_id: str = ""
    snippet: str = ""


class GraphEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: str  # IMPORTS, DEFINES, CALLS, USES, INHERITS, DEPENDS_ON, TESTED_BY, REFERENCES, CONFIGURES, EXPOSES
    filename: str
    line_number: int = 1
    snippet: str = ""


class GraphEvidence(BaseModel):
    source_node: GraphNode
    relation: str
    target_node: GraphNode
    hop_depth: int
    citation: str
    provenance_line: int
    snippet: str


class KnowledgeGraph:
    def __init__(self, db_path: Path | None = None):
        settings = get_settings()
        self.db_path = db_path or settings.KNOWLEDGE_GRAPH_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    page INTEGER,
                    section TEXT,
                    sha256 TEXT,
                    doc_id TEXT,
                    snippet TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    snippet TEXT
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_filename ON nodes(filename);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);")
            conn.commit()

    def add_nodes_and_edges(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """Batch insert nodes and edges into SQLite."""
        if not nodes and not edges:
            return

        with self._get_connection() as conn:
            for n in nodes:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nodes
                    (id, name, node_type, filename, file_type, start_line, end_line, page, section, sha256, doc_id, snippet)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        n.id,
                        n.name,
                        n.node_type,
                        n.filename,
                        n.file_type,
                        n.start_line,
                        n.end_line,
                        n.page,
                        n.section,
                        n.sha256,
                        n.doc_id,
                        n.snippet,
                    ),
                )

            for e in edges:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO edges
                    (id, source_id, target_id, relation, filename, line_number, snippet)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e.id,
                        e.source_id,
                        e.target_id,
                        e.relation,
                        e.filename,
                        e.line_number,
                        e.snippet,
                    ),
                )
            conn.commit()

    def delete_by_filename(self, filename: str) -> int:
        """Removes all nodes and edges associated with a given filename."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM edges WHERE filename = ?", (filename,))
            edges_deleted = cursor.rowcount
            cursor2 = conn.execute("DELETE FROM nodes WHERE filename = ?", (filename,))
            nodes_deleted = cursor2.rowcount
            conn.commit()
            return nodes_deleted + edges_deleted

    def find_nodes_by_name(self, name: str) -> list[GraphNode]:
        """Finds nodes matching exact name or substring."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM nodes WHERE name = ? OR name LIKE ? LIMIT 20",
                (name, f"%{name}%"),
            ).fetchall()
            return [self._row_to_node(r) for r in rows]

    def find_node_by_id(self, node_id: str) -> GraphNode | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
            return self._row_to_node(row) if row else None

    def get_outgoing_edges(self, node_id: str, relation: str | None = None) -> list[GraphEdge]:
        query = "SELECT * FROM edges WHERE source_id = ?"
        params = [node_id]
        if relation:
            query += " AND relation = ?"
            params.append(relation)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_edge(r) for r in rows]

    def get_incoming_edges(self, node_id: str, relation: str | None = None) -> list[GraphEdge]:
        query = "SELECT * FROM edges WHERE target_id = ?"
        params = [node_id]
        if relation:
            query += " AND relation = ?"
            params.append(relation)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_edge(r) for r in rows]

    def traverse_multi_hop(
        self,
        start_identifier: str,
        max_hops: int = 2,
        direction: str = "both",
    ) -> list[GraphEvidence]:
        """
        Performs multi-hop BFS traversal from an entity name or ID,
        returning structured evidence with provenance and citations.
        """
        start_nodes = self.find_nodes_by_name(start_identifier)
        if not start_nodes:
            # Check by ID
            single = self.find_node_by_id(start_identifier)
            if single:
                start_nodes = [single]

        if not start_nodes:
            return []

        visited_nodes: set[str] = set()
        visited_edges: set[str] = set()
        evidence_list: list[GraphEvidence] = []

        # Queue contains tuples: (current_node, current_hop)
        queue: deque[tuple[GraphNode, int]] = deque()
        for s in start_nodes:
            queue.append((s, 0))
            visited_nodes.add(s.id)

        while queue:
            current_node, hop = queue.popleft()
            if hop >= max_hops:
                continue

            # Outgoing edges
            if direction in ("out", "both"):
                out_edges = self.get_outgoing_edges(current_node.id)
                for edge in out_edges:
                    if edge.id in visited_edges:
                        continue
                    visited_edges.add(edge.id)

                    target_node = self.find_node_by_id(edge.target_id)
                    if target_node:
                        citation = f"{edge.filename}:L{edge.line_number}"
                        evidence_list.append(
                            GraphEvidence(
                                source_node=current_node,
                                relation=edge.relation,
                                target_node=target_node,
                                hop_depth=hop + 1,
                                citation=citation,
                                provenance_line=edge.line_number,
                                snippet=edge.snippet or f"{current_node.name} {edge.relation} {target_node.name}",
                            )
                        )
                        if target_node.id not in visited_nodes and hop + 1 < max_hops:
                            visited_nodes.add(target_node.id)
                            queue.append((target_node, hop + 1))

            # Incoming edges
            if direction in ("in", "both"):
                in_edges = self.get_incoming_edges(current_node.id)
                for edge in in_edges:
                    if edge.id in visited_edges:
                        continue
                    visited_edges.add(edge.id)

                    source_node = self.find_node_by_id(edge.source_id)
                    if source_node:
                        citation = f"{edge.filename}:L{edge.line_number}"
                        evidence_list.append(
                            GraphEvidence(
                                source_node=source_node,
                                relation=edge.relation,
                                target_node=current_node,
                                hop_depth=hop + 1,
                                citation=citation,
                                provenance_line=edge.line_number,
                                snippet=edge.snippet or f"{source_node.name} {edge.relation} {current_node.name}",
                            )
                        )
                        if source_node.id not in visited_nodes and hop + 1 < max_hops:
                            visited_nodes.add(source_node.id)
                            queue.append((source_node, hop + 1))

        return evidence_list

    def reset(self) -> None:
        """
        Clears all nodes and edges from the knowledge graph.
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM nodes")
            conn.commit()

    def count_nodes(self) -> int:
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    def count_edges(self) -> int:
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def _row_to_node(self, row: sqlite3.Row) -> GraphNode:
        return GraphNode(
            id=row["id"],
            name=row["name"],
            node_type=row["node_type"],
            filename=row["filename"],
            file_type=row["file_type"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            page=row["page"],
            section=row["section"],
            sha256=row["sha256"],
            doc_id=row["doc_id"],
            snippet=row["snippet"] or "",
        )

    def _row_to_edge(self, row: sqlite3.Row) -> GraphEdge:
        return GraphEdge(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation=row["relation"],
            filename=row["filename"],
            line_number=row["line_number"],
            snippet=row["snippet"] or "",
        )


_kg_instance: KnowledgeGraph | None = None


def get_knowledge_graph() -> KnowledgeGraph:
    global _kg_instance
    if _kg_instance is None:
        _kg_instance = KnowledgeGraph()
    return _kg_instance
