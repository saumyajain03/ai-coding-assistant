"""
Structural Graph Builder
Extracts reliable, verifiable entities and relationships from parsed ASTs and documents.
Adheres strictly to the requirement: DO NOT invent relationships from text similarity.
"""

import ast
import re
from hashlib import sha256
from pathlib import Path

from src.rag.knowledge_graph import GraphEdge, GraphNode
from src.rag.parser import ParsedSection


def build_graph_for_document(
    filename: str,
    raw_content: str | bytes,
    file_hash: str,
    sections: list[ParsedSection],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """
    Extracts deterministic structural entities and relationships for a document.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    ext = Path(filename).suffix.lower()
    doc_id = f"doc_{file_hash[:12]}"
    file_node_id = f"file:{filename}"

    # 1. Create primary FILE / CONFIG node
    node_type = "CONFIG" if ext in (".json", ".yaml", ".yml", ".toml") else "FILE"
    file_node = GraphNode(
        id=file_node_id,
        name=filename,
        node_type=node_type,
        filename=filename,
        file_type=ext,
        start_line=1,
        end_line=sections[-1].end_line if sections else 1,
        sha256=file_hash,
        doc_id=doc_id,
        snippet=f"File {filename} ({ext})",
    )
    nodes.append(file_node)

    # 2. Extract format-specific structural entities
    if isinstance(raw_content, bytes):
        try:
            text = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_content.decode("latin-1", errors="replace")
    else:
        text = raw_content

    if ext == ".py":
        py_nodes, py_edges = _extract_python_structure(filename, text, file_node_id, file_hash, doc_id)
        nodes.extend(py_nodes)
        edges.extend(py_edges)

    elif ext in (".js", ".ts"):
        js_nodes, js_edges = _extract_js_ts_structure(filename, text, file_node_id, file_hash, doc_id, ext)
        nodes.extend(js_nodes)
        edges.extend(js_edges)

    elif ext == ".md":
        md_nodes, md_edges = _extract_markdown_structure(filename, text, file_node_id, file_hash, doc_id, sections)
        nodes.extend(md_nodes)
        edges.extend(md_edges)

    elif ext == ".json":
        json_nodes, json_edges = _extract_json_structure(filename, text, file_node_id, file_hash, doc_id)
        nodes.extend(json_nodes)
        edges.extend(json_edges)

    elif ext == ".pdf":
        pdf_nodes, pdf_edges = _extract_pdf_structure(filename, file_node_id, file_hash, doc_id, sections)
        nodes.extend(pdf_nodes)
        edges.extend(pdf_edges)

    return nodes, edges


def _extract_python_structure(
    filename: str,
    code: str,
    file_node_id: str,
    file_hash: str,
    doc_id: str,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    lines = code.splitlines()

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return nodes, edges

    # Track defined symbols in this file
    defined_symbols: dict[str, str] = {}  # name -> node_id

    # 1. Extract Imports (IMPORTS relationship)
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name
                target_id = f"module:{mod_name}"
                nodes.append(
                    GraphNode(
                        id=target_id,
                        name=mod_name,
                        node_type="MODULE",
                        filename=filename,
                        file_type=".py",
                        start_line=node.lineno,
                        end_line=node.lineno,
                        sha256=file_hash,
                        doc_id=doc_id,
                        snippet=f"import {mod_name}",
                    )
                )
                edges.append(
                    GraphEdge(
                        id=f"edge_{sha256((file_node_id + target_id + 'IMPORTS' + str(node.lineno)).encode()).hexdigest()[:12]}",
                        source_id=file_node_id,
                        target_id=target_id,
                        relation="IMPORTS",
                        filename=filename,
                        line_number=node.lineno,
                        snippet=f"import {mod_name}",
                    )
                )

        elif isinstance(node, ast.ImportFrom):
            mod_name = node.module or ""
            for alias in node.names:
                target_name = f"{mod_name}.{alias.name}" if mod_name else alias.name
                target_id = f"symbol:{target_name}"
                nodes.append(
                    GraphNode(
                        id=target_id,
                        name=alias.name,
                        node_type="SYMBOL",
                        filename=filename,
                        file_type=".py",
                        start_line=node.lineno,
                        end_line=node.lineno,
                        sha256=file_hash,
                        doc_id=doc_id,
                        snippet=f"from {mod_name} import {alias.name}",
                    )
                )
                edges.append(
                    GraphEdge(
                        id=f"edge_{sha256((file_node_id + target_id + 'IMPORTS' + str(node.lineno)).encode()).hexdigest()[:12]}",
                        source_id=file_node_id,
                        target_id=target_id,
                        relation="IMPORTS",
                        filename=filename,
                        line_number=node.lineno,
                        snippet=f"from {mod_name} import {alias.name}",
                    )
                )

    # 2. Extract Classes, Methods, Functions (DEFINES and INHERITS relationships)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_id = f"class:{filename}:{node.name}"
            defined_symbols[node.name] = class_id
            start = node.lineno
            end = getattr(node, "end_lineno", start + 20)
            class_snippet = "\n".join(lines[start - 1 : min(start + 5, len(lines))])

            nodes.append(
                GraphNode(
                    id=class_id,
                    name=node.name,
                    node_type="CLASS",
                    filename=filename,
                    file_type=".py",
                    start_line=start,
                    end_line=end,
                    sha256=file_hash,
                    doc_id=doc_id,
                    snippet=class_snippet,
                )
            )
            edges.append(
                GraphEdge(
                    id=f"edge_{sha256((file_node_id + class_id + 'DEFINES').encode()).hexdigest()[:12]}",
                    source_id=file_node_id,
                    target_id=class_id,
                    relation="DEFINES",
                    filename=filename,
                    line_number=start,
                    snippet=f"class {node.name}",
                )
            )

            # Class Inheritance (INHERITS relationship)
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_name = base.id
                    base_id = f"class_ref:{base_name}"
                    edges.append(
                        GraphEdge(
                            id=f"edge_{sha256((class_id + base_id + 'INHERITS').encode()).hexdigest()[:12]}",
                            source_id=class_id,
                            target_id=base_id,
                            relation="INHERITS",
                            filename=filename,
                            line_number=start,
                            snippet=f"class {node.name}({base_name})",
                        )
                    )

            # Class Methods
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_id = f"method:{filename}:{node.name}:{item.name}"
                    m_start = item.lineno
                    m_end = getattr(item, "end_lineno", m_start + 10)
                    nodes.append(
                        GraphNode(
                            id=method_id,
                            name=f"{node.name}.{item.name}",
                            node_type="METHOD",
                            filename=filename,
                            file_type=".py",
                            start_line=m_start,
                            end_line=m_end,
                            sha256=file_hash,
                            doc_id=doc_id,
                            snippet="\n".join(lines[m_start - 1 : min(m_start + 4, len(lines))]),
                        )
                    )
                    edges.append(
                        GraphEdge(
                            id=f"edge_{sha256((class_id + method_id + 'DEFINES').encode()).hexdigest()[:12]}",
                            source_id=class_id,
                            target_id=method_id,
                            relation="DEFINES",
                            filename=filename,
                            line_number=m_start,
                            snippet=f"def {item.name}(self, ...)",
                        )
                    )

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_test = node.name.startswith("test_") or filename.startswith("test_")
            fn_type = "TEST" if is_test else "FUNCTION"
            fn_id = f"fn:{filename}:{node.name}"
            defined_symbols[node.name] = fn_id
            start = node.lineno
            end = getattr(node, "end_lineno", start + 10)

            nodes.append(
                GraphNode(
                    id=fn_id,
                    name=node.name,
                    node_type=fn_type,
                    filename=filename,
                    file_type=".py",
                    start_line=start,
                    end_line=end,
                    sha256=file_hash,
                    doc_id=doc_id,
                    snippet="\n".join(lines[start - 1 : min(start + 4, len(lines))]),
                )
            )
            edges.append(
                GraphEdge(
                    id=f"edge_{sha256((file_node_id + fn_id + 'DEFINES').encode()).hexdigest()[:12]}",
                    source_id=file_node_id,
                    target_id=fn_id,
                    relation="DEFINES",
                    filename=filename,
                    line_number=start,
                    snippet=f"def {node.name}(...)",
                )
            )

    # 3. Extract Explicit Calls (CALLS / TESTED_BY relationships)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            caller_id = defined_symbols.get(node.name, f"fn:{filename}:{node.name}")
            is_test = node.name.startswith("test_")

            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    called_name = None
                    if isinstance(sub.func, ast.Name):
                        called_name = sub.func.id
                    elif isinstance(sub.func, ast.Attribute):
                        called_name = sub.func.attr

                    if called_name and called_name != node.name:
                        target_id = defined_symbols.get(called_name, f"symbol:{called_name}")
                        rel = "TESTED_BY" if is_test else "CALLS"
                        source = target_id if is_test else caller_id
                        target = caller_id if is_test else target_id

                        edges.append(
                            GraphEdge(
                                id=f"edge_{sha256((source + target + rel + str(sub.lineno)).encode()).hexdigest()[:12]}",
                                source_id=source,
                                target_id=target,
                                relation=rel,
                                filename=filename,
                                line_number=sub.lineno,
                                snippet=f"{node.name} calls {called_name}()",
                            )
                        )

    return nodes, edges


def _extract_js_ts_structure(
    filename: str,
    code: str,
    file_node_id: str,
    file_hash: str,
    doc_id: str,
    ext: str,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    lines = code.splitlines()

    # 1. Imports: import { X } from 'Y'; import X from 'Y';
    import_regex = re.compile(r"import\s+(?:\{([^}]+)\}|([a-zA-Z0-9_$]+))\s+from\s+['\"]([^'\"]+)['\"]")
    for idx, line in enumerate(lines, start=1):
        match = import_regex.search(line)
        if match:
            symbols = match.group(1) or match.group(2) or ""
            module = match.group(3)
            target_id = f"module:{module}"
            nodes.append(
                GraphNode(
                    id=target_id,
                    name=module,
                    node_type="MODULE",
                    filename=filename,
                    file_type=ext,
                    start_line=idx,
                    end_line=idx,
                    sha256=file_hash,
                    doc_id=doc_id,
                    snippet=line.strip(),
                )
            )
            edges.append(
                GraphEdge(
                    id=f"edge_{sha256((file_node_id + target_id + 'IMPORTS' + str(idx)).encode()).hexdigest()[:12]}",
                    source_id=file_node_id,
                    target_id=target_id,
                    relation="IMPORTS",
                    filename=filename,
                    line_number=idx,
                    snippet=f"imports {symbols.strip()} from '{module}'",
                )
            )

    # 2. Functions, Classes, Interfaces (DEFINES relationship)
    decl_regex = re.compile(
        r"^(?:export\s+)?(?:async\s+)?(function|class|interface|type)\s+([a-zA-Z0-9_$]+)"
    )
    for idx, line in enumerate(lines, start=1):
        match = decl_regex.search(line.strip())
        if match:
            kind, name = match.group(1).upper(), match.group(2)
            entity_id = f"{kind.lower()}:{filename}:{name}"
            nodes.append(
                GraphNode(
                    id=entity_id,
                    name=name,
                    node_type=kind,
                    filename=filename,
                    file_type=ext,
                    start_line=idx,
                    end_line=idx + 10,
                    sha256=file_hash,
                    doc_id=doc_id,
                    snippet=line.strip(),
                )
            )
            edges.append(
                GraphEdge(
                    id=f"edge_{sha256((file_node_id + entity_id + 'DEFINES').encode()).hexdigest()[:12]}",
                    source_id=file_node_id,
                    target_id=entity_id,
                    relation="DEFINES",
                    filename=filename,
                    line_number=idx,
                    snippet=f"{kind.lower()} {name}",
                )
            )

    return nodes, edges


def _extract_markdown_structure(
    filename: str,
    text: str,
    file_node_id: str,
    file_hash: str,
    doc_id: str,
    sections: list[ParsedSection],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # 1. Section nodes
    for sec in sections:
        sec_id = f"section:{filename}:{sec.start_line}"
        nodes.append(
            GraphNode(
                id=sec_id,
                name=sec.section_name or f"Section L{sec.start_line}",
                node_type="DOC_SECTION",
                filename=filename,
                file_type=".md",
                start_line=sec.start_line,
                end_line=sec.end_line,
                section=sec.section_name,
                sha256=file_hash,
                doc_id=doc_id,
                snippet=sec.content[:150],
            )
        )
        edges.append(
            GraphEdge(
                id=f"edge_{sha256((file_node_id + sec_id + 'DEFINES').encode()).hexdigest()[:12]}",
                source_id=file_node_id,
                target_id=sec_id,
                relation="DEFINES",
                filename=filename,
                line_number=sec.start_line,
                snippet=sec.section_name or "section",
            )
        )

    # 2. Markdown File References: [link](target_file.py) or `code.py`
    link_regex = re.compile(r"\[([^\]]+)\]\(([^)]+\.(?:py|js|ts|json|md))\)")
    for line_idx, line in enumerate(text.splitlines(), start=1):
        for match in link_regex.finditer(line):
            target_ref = match.group(2)
            target_id = f"file:{target_ref}"
            edges.append(
                GraphEdge(
                    id=f"edge_{sha256((file_node_id + target_id + 'REFERENCES' + str(line_idx)).encode()).hexdigest()[:12]}",
                    source_id=file_node_id,
                    target_id=target_id,
                    relation="REFERENCES",
                    filename=filename,
                    line_number=line_idx,
                    snippet=f"references [{match.group(1)}]({target_ref})",
                )
            )

    return nodes, edges


def _extract_json_structure(
    filename: str,
    text: str,
    file_node_id: str,
    file_hash: str,
    doc_id: str,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    try:
        import json
        data = json.loads(text)
        if isinstance(data, dict):
            for idx, key in enumerate(data.keys(), start=1):
                key_id = f"config:{filename}:{key}"
                nodes.append(
                    GraphNode(
                        id=key_id,
                        name=key,
                        node_type="CONFIG_KEY",
                        filename=filename,
                        file_type=".json",
                        start_line=idx,
                        end_line=idx,
                        sha256=file_hash,
                        doc_id=doc_id,
                        snippet=f"Key '{key}'",
                    )
                )
                edges.append(
                    GraphEdge(
                        id=f"edge_{sha256((file_node_id + key_id + 'CONFIGURES').encode()).hexdigest()[:12]}",
                        source_id=file_node_id,
                        target_id=key_id,
                        relation="CONFIGURES",
                        filename=filename,
                        line_number=idx,
                        snippet=f"configures key: {key}",
                    )
                )
    except Exception:
        pass

    return nodes, edges


def _extract_pdf_structure(
    filename: str,
    file_node_id: str,
    file_hash: str,
    doc_id: str,
    sections: list[ParsedSection],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    for sec in sections:
        if sec.page is not None:
            page_id = f"page:{filename}:{sec.page}"
            nodes.append(
                GraphNode(
                    id=page_id,
                    name=f"Page {sec.page}",
                    node_type="DOC_SECTION",
                    filename=filename,
                    file_type=".pdf",
                    start_line=sec.start_line,
                    end_line=sec.end_line,
                    page=sec.page,
                    sha256=file_hash,
                    doc_id=doc_id,
                    snippet=sec.content[:150],
                )
            )
            edges.append(
                GraphEdge(
                    id=f"edge_{sha256((file_node_id + page_id + 'DEFINES').encode()).hexdigest()[:12]}",
                    source_id=file_node_id,
                    target_id=page_id,
                    relation="DEFINES",
                    filename=filename,
                    line_number=sec.start_line,
                    snippet=f"Page {sec.page}",
                )
            )

    return nodes, edges
