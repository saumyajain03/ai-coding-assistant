"""
RAG Security & Anti-Injection Guardrails
Treats all retrieved context as untrusted data.
Implements complex prompt-injection pattern detection, delimiter breakout defense,
sanitization, and security audit logging.
"""

import base64
import html
import re
import unicodedata

from src.sandbox.audit import get_audit_logger

# Known prompt-injection regex attack patterns
PROMPT_INJECTION_PATTERNS = [
    (
        re.compile(
            r"(?i)(ignore|disregard|forget|bypass)\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)"
        ),
        "DIRECT_INSTRUCTION_OVERRIDE",
    ),
    (
        re.compile(r"(?i)disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)"),
        "DIRECT_PROMPT_DISREGARD",
    ),
    (
        re.compile(r"(?i)(system\s+override|admin\s+override|developer\s+mode|jailbreak\s+mode)"),
        "PRIVILEGE_ESCALATION",
    ),
    (
        re.compile(
            r"(?i)(you\s+are\s+now|act\s+as)\s+(in\s+developer\s+mode|unrestricted|an\s+adversary|evilbot|dan\b|[a-z0-9_-]*bot\b|a\s+hacker|an\s+unfiltered)"
        ),
        "PERSONA_HIJACK",
    ),
    (re.compile(r"(?i)<\/?untrusted_document_context>"), "DELIMITER_BREAKOUT_ATTEMPT"),
    (re.compile(r"(?i)(\[system\]|<system>|system:\s*)"), "SYSTEM_PROMPT_EMULATION"),
    (re.compile(r"(?i)(send|post|exfiltrate)\s+.*(to|at)\s+https?:\/\/"), "DATA_EXFILTRATION_INTENT"),
    (re.compile(r"(?i)eval\s*\(\s*compile\s*\("), "DYNAMIC_CODE_EXECUTION"),
]

INVISIBLE_CHARS = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad\u2060\u200e\u200f]")
BASE64_TOKEN_PATTERN = re.compile(r"\b[A-Za-z0-9+/]{16,}={0,2}\b")


def scan_for_prompt_injection(text: str) -> tuple[bool, list[str], float]:
    """
    Scans document or query text for prompt-injection and jailbreak patterns.
    Handles Unicode zero-width obfuscation and Base64 encoded payloads.

    Returns:
        (is_detected, list_of_threat_categories, risk_score_from_0_to_1)
    """
    detected_threats: list[str] = []
    risk_score = 0.0

    # 1. Normalize Unicode and strip invisible characters
    normalized = unicodedata.normalize("NFKD", text)
    has_invisible = bool(INVISIBLE_CHARS.search(normalized))
    cleaned_text = INVISIBLE_CHARS.sub("", normalized)

    # 2. Check direct pattern matches
    for pattern, threat_name in PROMPT_INJECTION_PATTERNS:
        if pattern.search(cleaned_text):
            if threat_name not in detected_threats:
                detected_threats.append(threat_name)
                risk_score += 0.35

    if has_invisible and detected_threats:
        if "OBFUSCATED_UNICODE_INJECTION" not in detected_threats:
            detected_threats.append("OBFUSCATED_UNICODE_INJECTION")
            risk_score += 0.2

    # 3. Check for Base64 encoded injection payloads
    for match in BASE64_TOKEN_PATTERN.finditer(cleaned_text):
        candidate = match.group(0)
        try:
            decoded_bytes = base64.b64decode(candidate, validate=True)
            decoded_str = decoded_bytes.decode("utf-8", errors="ignore").strip()
            if len(decoded_str) >= 8:
                decoded_normalized = INVISIBLE_CHARS.sub("", unicodedata.normalize("NFKD", decoded_str))
                for pattern, threat_name in PROMPT_INJECTION_PATTERNS:
                    if pattern.search(decoded_normalized):
                        if threat_name not in detected_threats:
                            detected_threats.append(threat_name)
                        if "OBFUSCATED_BASE64_PAYLOAD" not in detected_threats:
                            detected_threats.append("OBFUSCATED_BASE64_PAYLOAD")
                        risk_score += 0.4
                        break
        except Exception:
            pass

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
        clean_text = INVISIBLE_CHARS.sub("", unicodedata.normalize("NFKD", safe_text))
        for pattern, _ in PROMPT_INJECTION_PATTERNS:
            clean_text = pattern.sub(r"[DEFUSED_INJECTION_ATTEMPT: \g<0>]", clean_text)
        safe_text = clean_text

    # 3. Construct defensive container
    return (
        f'<untrusted_document_context source="{html.escape(source_citation)}" score="{score}"{threat_warning}>\n'
        f"{safe_text}\n"
        f"</untrusted_document_context>"
    )
