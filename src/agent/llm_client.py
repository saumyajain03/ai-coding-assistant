"""
Multi-Provider LLM Client for SentinelForge Phase 4 Autonomous Agent Core.
Supports:
1. Local Ollama (e.g. http://localhost:11434/api/generate)
2. Groq Free Inference API
3. HuggingFace Free Inference API
4. Deterministic Mock Provider (offline, rule-based, zero-cost, reproducible CI/CD testing)
"""

import abc
import re

import httpx

from src.config import get_settings


class BaseLLMProvider(abc.ABC):
    """Abstract base class for all LLM inference providers."""

    @abc.abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Generates a text completion for the given prompt."""
        raise NotImplementedError


class DeterministicMockProvider(BaseLLMProvider):
    """
    Offline, deterministic rule-based LLM provider.
    Enables thorough unit/integration testing of the 7-stage loop, diff generator,
    and prompt flows without requiring external network connectivity or GPU resources.
    """

    def __init__(self, custom_responses: dict[str, str] | None = None):
        self.custom_responses = custom_responses or {}

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        # Check explicit custom responses first
        for pattern, response in self.custom_responses.items():
            if pattern.lower() in prompt.lower() or pattern.lower() in system_prompt.lower():
                return response

        # Deterministic responses based on stage keywords
        prompt_lower = prompt.lower()
        if "stage 1: task analysis" in prompt_lower or "stage 1" in prompt_lower:
            return (
                "### Task Analysis\n"
                "- Type: Code Modification / Verification\n"
                "- Target Scope: Identified relevant workspace files and potential regressions\n"
                "- Acceptance Criteria: Fix bug or implement feature with zero test failures\n"
                "- Security Impact: Low to Medium, subject to sandbox limits"
            )

        if "stage 2: plan generation" in prompt_lower or "stage 2" in prompt_lower:
            return (
                "### Implementation Plan\n"
                "1. Query RAG context for symbol definitions\n"
                "2. Synthesize unified diff fixing the issue\n"
                "3. Execute sandboxed test suite to verify correctness\n"
                "4. Formulate self-critique on test results"
            )

        if "stage 4: patch synthesis" in prompt_lower or "stage 4" in prompt_lower:
            # Extract target file if mentioned
            match = re.search(r"Target File:\s*([^\n]+)", prompt)
            target = match.group(1).strip() if match else "main.py"
            if "calculate_discount" in prompt_lower:
                return (
                    f"# Proposed patch for {target}\n"
                    "def calculate_discount(price: float, discount: float) -> float:\n"
                    "    return price - (price * discount)\n"
                )
            return f"# Proposed patch for {target}\n# Automated synthesis completed\ndef fixed_solution():\n    return 42\n"

        if "stage 6: self-critique" in prompt_lower or "stage 6" in prompt_lower:
            if "passed: false" in prompt_lower or "exit code: 1" in prompt_lower:
                return (
                    "### Self-Critique\n"
                    "- Test Status: FAILED. The test suite reported an error or regression.\n"
                    "- Risk Score: 7/10\n"
                    "- Recommendation: Review test trace and refine patch before human approval."
                )
            return (
                "### Self-Critique\n"
                "- Test Status: PASSED. Verified with empirical sandbox test execution.\n"
                "- Risk Score: 2/10\n"
                "- Recommendation: Safe for human review and explicit approval."
            )

        if "stage 7: final report" in prompt_lower or "stage 7" in prompt_lower:
            return (
                "### Final Execution Report\n"
                "1. **Analysis & Plan**: Completed successfully.\n"
                "2. **Retrieved Context**: Integrated cited workspace evidence.\n"
                "3. **Proposed Patch**: Unified diff staged for review.\n"
                "4. **Sandbox Tests**: Verified within execution limits.\n"
                "5. **Status**: PENDING_APPROVAL. Waiting for explicit human operator sign-off."
            )

        return "Deterministic response generated for prompt."


class OllamaProvider(BaseLLMProvider):
    """Local Ollama HTTP API provider."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")


class GroqFreeProvider(BaseLLMProvider):
    """Groq Free OpenAI-compatible inference API provider."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.GROQ_API_KEY or ""
        self.model = model or settings.LLM_MODEL or "llama-3.1-8b-instant"
        self.base_url = "https://api.groq.com/openai/v1"

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


class HuggingFaceFreeProvider(BaseLLMProvider):
    """HuggingFace Free Inference API provider."""

    def __init__(self, token: str | None = None, model: str | None = None):
        settings = get_settings()
        self.token = token or settings.HF_TOKEN or ""
        self.model = model or settings.LLM_MODEL or "Qwen/Qwen2.5-Coder-7B-Instruct"
        self.api_url = f"https://api-inference.huggingface.co/models/{self.model}"

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.token}" if self.token else "",
            "Content-Type": "application/json",
        }
        combined_prompt = f"{system_prompt}\n\nUser:\n{prompt}\n\nAssistant:\n" if system_prompt else prompt
        payload = {
            "inputs": combined_prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "return_full_text": False,
            },
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("generated_text", "")
            if isinstance(data, dict):
                return data.get("generated_text", "")
            return str(data)


class LLMClient:
    """
    Unified LLM Client factory and abstraction.
    Instantiates the configured provider (Ollama, Groq, HF, or Synthetic Mock)
    ensuring zero-cost operation and no hardcoded dependencies.
    """

    def __init__(self, provider: BaseLLMProvider | None = None, provider_name: str | None = None):
        settings = get_settings()
        selected_provider = provider_name or settings.LLM_PROVIDER

        if provider is not None:
            self._provider = provider
        elif selected_provider == "ollama":
            self._provider = OllamaProvider()
        elif selected_provider == "groq_free":
            self._provider = GroqFreeProvider()
        elif selected_provider == "hf_free":
            self._provider = HuggingFaceFreeProvider()
        else:
            self._provider = DeterministicMockProvider()

    @property
    def provider(self) -> BaseLLMProvider:
        return self._provider

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        return await self._provider.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
