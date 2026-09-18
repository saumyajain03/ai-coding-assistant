"""
RAG Security & Anti-Injection Guardrails
Treats all retrieved context as untrusted data.
Implements complex prompt-injection pattern detection, delimiter breakout defense,
sanitization, and security audit logging.
"""

import html
import re

from src.sandbox.audit import get_audit_logger

# Known prompt-injection regex attack patterns
PROMPT_INJECTION_PATTERNS = [
    (re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+(instructions|prompts|rules)"), "DIRECT_INSTRUCTION_OVERRIDE"),
    (re.compile(r"(?i)disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)"), "DIRECT_PROMPT_DISREGARD"),
    (re.compile(r"(?i)(system\s+override|admin\s+override|developer\s+mode|jailbreak\s+mode)"), "PRIVILEGE_ESCALATION"),
    (re.compile(r"(?i)you\s+are\s+now\s+(in\s+developer\s+mode|unrestricted|an\s+adversary)"), "PERSONA_HIJACK"),
    (re.compile(r"(?i)<\/?untrusted_document_context>"), "DELIMITER_BREAKOUT_ATTEMPT"),
    (re.compile(r"(?i)(\[system\]|<system>|system:\s*)"), "SYSTEM_PROMPT_EMULATION"),
    (re.compile(r"(?i)(send|post|exfiltrate)\s+.*(to|at)\s+https?:\/\/"), "DATA_EXFILTRATION_INTENT"),
    (re.compile(r"(?i)eval\s*\(\s*compile\s*\("), "DYNAMIC_CODE_EXECUTION"),
]


def scan_for_prompt_injection(text: str) -> tuple[bool, list[str], float]:
    """
    Scans document or query text for prompt-injection and jailbreak patterns.

    Returns:
        (is_detected, list_of_threat_categories, risk_score_from_0_to_1)
    """
    detected_threats: list[str] = []
    risk_score = 0.0

    for pattern, threat_name in PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            detected_threats.append(threat_name)
            risk_score += 0.35

    risk_score = min(1.0, round(risk_score, 2))
    is_detected = len(detected_threats) > 0

    if is_detected:
        # Record security audit event
        audit = get_audit_logger()
        audit.record(
            event_type="INJECTION_ATTEMPT_DETECTED",
            caller="rag_guardrails",
            details={
                "threats": detected_threats,
                "risk_score": risk_score,
                "sample_preview": text[:100],
            },
            risk_level="HIGH" if risk_score >= 0.7 else "MEDIUM",
        )

    return is_detected, detected_threats, risk_score


def sanitize_content_for_context(
    raw_content: str,
    source_citation: str,
    score: float,
) -> str:
    """
    Sanitizes retrieved snippets and wraps them inside protective delimiters,
    neutralizing delimiter breakouts and warning the LLM that this is passive data.
    """
    # 1. Defend against delimiter breakouts by escaping closing tags
    safe_text = raw_content.replace("</untrusted_document_context>", "&lt;/untrusted_document_context&gt;")
    safe_text = safe_text.replace("<untrusted_document_context>", "&lt;untrusted_document_context&gt;")

    # 2. Check for injection markers
    is_detected, threats, _ = scan_for_prompt_injection(raw_content)
    threat_warning = ""
    if is_detected:
        threat_warning = f' security_alert="POTENTIAL_INJECTION_DETECTED: {", ".join(threats)}"'
        # Defuse known commands inside the snippet
        for pattern, _ in PROMPT_INJECTION_PATTERNS:
            safe_text = pattern.sub(r"[DEFUSED_INJECTION_ATTEMPT: \g<0>]", safe_text)

    # 3. Construct defensive container
    return (
        f'<untrusted_document_context source="{html.escape(source_citation)}" score="{score}"{threat_warning}>\n'
        f"{safe_text}\n"
        f"</untrusted_document_context>"
    )
