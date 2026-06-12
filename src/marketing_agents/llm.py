from __future__ import annotations

import json
import os
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict

from marketing_agents.contracts import BrandFacts, CampaignRequest, ResearchBrief, StrategyBrief
from marketing_agents.json_contracts import dict_value, extract_json_object, list_value, require_keys
from marketing_agents.prompts import PromptLibrary


class MarketingModel(ABC):
    @abstractmethod
    def research(self, request: CampaignRequest, brand_facts: BrandFacts) -> ResearchBrief:
        raise NotImplementedError

    @abstractmethod
    def strategy(self, request: CampaignRequest, research: ResearchBrief) -> StrategyBrief:
        raise NotImplementedError

    @abstractmethod
    def content(self, request: CampaignRequest, research: ResearchBrief, strategy: StrategyBrief) -> dict[str, object]:
        raise NotImplementedError


class RuleBasedMarketingModel(MarketingModel):
    """Deterministic local model for V7 development and tests."""

    def research(self, request: CampaignRequest, brand_facts: BrandFacts) -> ResearchBrief:
        product = request.product
        audience = request.audience
        priorities = brand_facts.customer_priorities or ["saving time", "getting reliable outcomes", "reducing friction"]
        primary_priority = priorities[0]
        avoid = brand_facts.avoid or ["unsupported claims"]
        style = brand_facts.content_style or brand_facts.voice or [request.tone]
        return ResearchBrief(
            brand_facts=brand_facts,
            audience_insights=[
                f"{audience} care about {primary_priority}, so the campaign should make that benefit concrete quickly.",
                f"They will respond better to {', '.join(style[:2])} content than broad product claims.",
                f"Messaging should connect '{request.goal}' to a low-friction next step that feels useful, not pushy.",
            ],
            competitors=[
                "manual planning habits",
                "generic productivity tools",
                "status-quo workflows that feel easier than trying another app",
            ],
            pain_points=[
                f"difficulty maintaining consistency around {primary_priority}",
                "too many disconnected notes, reminders, or tools",
                "skepticism toward products that promise too much",
            ],
            opportunities=[
                f"Position {product} around {brand_facts.value_proposition}",
                f"Respect avoid rules: {', '.join(avoid[:3])}.",
                "Create channel-specific variants while keeping one clear promise.",
            ],
            assumptions=[
                "The campaign should optimise for a first signup or demo action, not final purchase.",
                "The strongest claims should come from the retrieved brand context or user request.",
            ],
            citations=brand_facts.citations,
            # Placeholder — ResearchAgent.run() will override this via goal_translator.
            translated_goal=request.goal,
        )

    def strategy(self, request: CampaignRequest, research: ResearchBrief) -> StrategyBrief:
        priority = research.brand_facts.customer_priorities[0] if research.brand_facts.customer_priorities else "saving time"
        voice = ", ".join(research.brand_facts.voice[:3]) or request.tone
        channels = research.brand_facts.preferred_channels or request.channels
        return StrategyBrief(
            positioning=(
                f"{request.product} helps {request.audience} {request.goal} by making {priority} easier to act on."
            ),
            messaging_pillars=[
                f"Make {priority} feel achievable",
                "Reduce the mental load before the next action",
                f"Speak in a {voice} voice",
            ],
            channel_plan=[
                self._channel_plan_line(channel, request, research)
                for channel in channels
            ],
            funnel_steps=[
                "Awareness: name the urgent pain",
                "Consideration: show the practical habit improvement",
                "Conversion: invite a low-friction signup with a specific use case",
            ],
            success_metrics=[
                "conversion rate",
                "signup rate",
                "channel engagement rate",
                "activation rate after signup",
            ],
            rejected_angles=[
                "Fear-based urgency",
                "Unrealistic outcome guarantees",
                "Corporate language that does not match the audience",
            ],
            risk_flags=[
                f"Avoid: {', '.join(research.brand_facts.avoid[:3])}" if research.brand_facts.avoid else "Avoid unsupported claims.",
                "Keep claims grounded in retrieved context or the campaign request.",
            ],
            hypothesis=f"If the campaign makes {priority} feel achievable in a {voice} voice, more {request.audience} will take the next step.",
        )

    def content(self, request: CampaignRequest, research: ResearchBrief, strategy: StrategyBrief) -> dict[str, object]:
        priority = research.brand_facts.customer_priorities[0] if research.brand_facts.customer_priorities else "saving time"
        voice_str = ", ".join(research.brand_facts.voice[:2]) if research.brand_facts.voice else ""
        content_style_str = ", ".join(research.brand_facts.content_style[:2]) if research.brand_facts.content_style else ""
        style = ", ".join(filter(None, [content_style_str, voice_str])) or request.tone
        avoid_note = research.brand_facts.avoid[0] if research.brand_facts.avoid else "unsupported claims"
        channels = research.brand_facts.preferred_channels or request.channels
        # V7: use the customer-language translation instead of the raw business goal.
        translated = research.translated_goal
        is_student_campaign = any(
            marker in " ".join([request.audience, research.brand_facts.value_proposition]).lower()
            for marker in ("student", "study", "assignment", "exam", "academic")
        )
        if not is_student_campaign:
            return self._business_content(request, research, strategy, priority, style, avoid_note, channels, translated)

        return {
            "ad_variants": [
                {
                    "control": f"Plan your week before it gets messy. {request.product} helps {request.audience} make {priority} feel achievable.",
                    "variant": f"Turn deadline stress into one clear plan with {request.product}."
                },
                {
                    "control": f"Assignments, study time, and reminders in one calmer flow. Try {request.product}.",
                    "variant": f"See what needs attention today, then build a study plan you can actually follow."
                },
                {
                    "control": f"Build a steadier study habit one task at a time with {request.product}.",
                    "variant": f"Small study steps add up when your assignments and reminders stay visible."
                },
                {
                    "control": f"Join students using {request.product} to keep classes, deadlines, and exam prep organized.",
                    "variant": f"Study planning feels easier when your week has one shared rhythm."
                },
                {
                    "control": f"Start with your next deadline. {request.product} turns it into a practical study plan.",
                    "variant": f"Create your first study plan and take the next step with less scrambling."
                },
            ],
            "social_posts": [
                self._social_post(channel, request, strategy, priority, style)
                for channel in channels
            ],
            "email_drafts": [
                {
                    "subject": "A calmer way to plan your study week",
                    "body": (
                        f"Hi there,\n\nIf your schedule keeps changing, {request.product} can help you organise "
                        f"assignments, study time, and reminders around {priority}.\n\n"
                        f"Start with one plan and adjust as your week changes.\n\nTry it → {translated}."
                    ),
                },
                {
                    "subject": "Less scrambling before exams",
                    "body": (
                        f"Hi there,\n\n{request.product} helps {request.audience} turn deadlines and exam prep "
                        "into a practical plan with reminders.\n\n"
                        f"Simple planning support for the next thing on your list.\n\nReply to {translated}."
                    ),
                },
                {
                    "subject": "Keep study plans consistent",
                    "body": (
                        f"Hi there,\n\nWhen classes, assignments, and personal life compete for attention, "
                        f"{request.product} helps keep the plan visible and manageable.\n\n"
                        f"Try it for your next study week — {translated}."
                    ),
                },
            ],
            "landing_page_copy": {
                "headline": f"Plan study weeks that feel easier to follow",
                "subheadline": (
                    f"{request.product} helps {request.audience} organise assignments, study schedules, "
                    f"and exam prep with {style} guidance, so {priority} feels easier to maintain."
                ),
                "primary_cta": "Create my study plan",
                "secondary_cta": "See how it works",
                "compliance_note": "Draft keeps claims specific, calm, and grounded.",
            },
            "revision_notes": ["Draft grounded in retrieved brand facts and channel plan."],
        }

    def _business_content(
        self,
        request: CampaignRequest,
        research: ResearchBrief,
        strategy: StrategyBrief,
        priority: str,
        style: str,
        avoid_note: str,
        channels: list[str],
        translated: str,
    ) -> dict[str, object]:
        return {
            "ad_variants": [
                {
                    "control": f"Turn scattered campaign work into a clearer plan. {request.product} helps {request.audience} make {priority} feel achievable.",
                    "variant": f"Give every campaign asset one focused promise before work spreads across channels."
                },
                {
                    "control": f"Keep strategy, copy, and review moving in the same direction with {request.product}.",
                    "variant": f"Align campaign ideas, channel copy, and review notes before message drift starts."
                },
                {
                    "control": f"Build a repeatable campaign habit around {priority} with {request.product}.",
                    "variant": f"Move from one-off campaign scrambles to a clearer weekly workflow."
                },
                {
                    "control": f"Help your team see the same campaign direction, from first brief to final copy.",
                    "variant": f"{request.product} gives {request.audience} a shared place to shape the message."
                },
                {
                    "control": f"Ready to {translated}? Start with a focused sample campaign from {request.product}.",
                    "variant": f"See the campaign workflow in action with a low-friction walkthrough."
                },
            ],
            "social_posts": [
                self._business_social_post(channel, request, strategy, priority, style)
                for channel in channels
            ],
            "email_drafts": [
                {
                    "subject": f"A clearer path to {translated}",
                    "body": (
                        f"Hi there,\n\nIf your team is working on {priority}, {request.product} can turn "
                        f"campaign ideas into practical assets while keeping the message focused.\n\n"
                        f"Want to {translated}? I can send a sample campaign package."
                    ),
                },
                {
                    "subject": "Keep every campaign asset aligned",
                    "body": (
                        f"Hi there,\n\n{request.audience} often lose time when strategy, copy, and review happen in separate places. "
                        f"{request.product} keeps the campaign direction clearer from the start.\n\n"
                        "Happy to share what that workflow looks like — reply to book 15 minutes."
                    ),
                },
                {
                    "subject": "More variants, less message drift",
                    "body": (
                        f"Hi there,\n\nEvery channel needs to carry the same promise. "
                        f"{request.product} helps create variants without losing the core idea.\n\n"
                        f"Can I send over an example? Reply or click to {translated}."
                    ),
                },
            ],
            "landing_page_copy": {
                "headline": f"Build campaigns that help {request.audience} {translated}",
                "subheadline": (
                    f"{request.product} helps teams turn strategy into ads, posts, emails, and landing page copy "
                    f"with {style} execution."
                ),
                "primary_cta": f"See it in action",
                "secondary_cta": "See sample output",
                "compliance_note": "Draft keeps claims specific, calm, and grounded.",
            },
            "revision_notes": ["Draft grounded in retrieved brand facts and channel plan."],
        }

    def _channel_plan_line(self, channel: str, request: CampaignRequest, research: ResearchBrief) -> str:
        channel_key = channel.lower()
        priority = research.brand_facts.customer_priorities[0] if research.brand_facts.customer_priorities else request.goal
        if "instagram" in channel_key:
            return f"{channel}: short relatable reels/carousels about {priority}"
        if "youtube" in channel_key:
            return f"{channel}: educational walkthroughs and study planning examples"
        if "discord" in channel_key:
            return f"{channel}: community prompts, reminders, and peer study routines"
        if "linkedin" in channel_key:
            return f"{channel}: practical credibility content for student outcomes and edtech partners"
        if "email" in channel_key:
            return f"{channel}: helpful onboarding sequence that supports {request.goal}"
        return f"{channel}: adapt the core promise for {request.audience}"

    def _social_post(
        self,
        channel: str,
        request: CampaignRequest,
        strategy: StrategyBrief,
        priority: str,
        style: str,
    ) -> dict[str, str]:
        channel_key = channel.lower()
        if "instagram" in channel_key:
            copy = f"POV: your assignments, exams, and reminders finally live in one plan. {request.product} helps with {priority}."
        elif "youtube" in channel_key:
            copy = f"Video idea: build a realistic study week in 5 minutes with {request.product}, from assignments to exam prep."
        elif "discord" in channel_key:
            copy = f"Prompt: drop your next deadline, then use {request.product} to turn it into a study plan you can stick with."
        elif "linkedin" in channel_key:
            copy = f"{strategy.positioning} The strongest student productivity tools reduce stress without promising unrealistic outcomes."
        else:
            copy = f"{request.product} helps {request.audience} work toward {request.goal} with {style} support."
        return {"channel": channel, "copy": copy}

    def _business_social_post(
        self,
        channel: str,
        request: CampaignRequest,
        strategy: StrategyBrief,
        priority: str,
        style: str,
    ) -> dict[str, str]:
        channel_key = channel.lower()
        if "linkedin" in channel_key:
            copy = f"{strategy.positioning} Strong campaigns start with a clear promise and practical review flow."
        elif "email" in channel_key:
            copy = f"Email angle: help {request.audience} move from campaign idea to approved assets while staying focused on {priority}."
        elif "social" in channel_key or "instagram" in channel_key:
            copy = f"One campaign idea. Multiple channel-ready variants. Less message drift for {request.audience}."
        else:
            copy = f"{request.product} helps {request.audience} work toward {request.goal} with {style} support."
        return {"channel": channel, "copy": copy}


class HttpJsonMarketingModel(MarketingModel):
    """Optional OpenAI-compatible JSON model adapter.

    This adapter is intentionally not used in tests. It expects an API key in
    MARKETING_AGENT_LLM_API_KEY, a base URL in config, and JSON-only responses.
    """

    def __init__(self, base_url: str, model: str, prompts: PromptLibrary, timeout: int = 600) -> None:
        if not base_url or not model:
            raise ValueError("HTTP LLM mode requires llm_base_url and llm_model in config")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompts = prompts
        self.timeout = timeout

    def research(self, request: CampaignRequest, brand_facts: BrandFacts) -> ResearchBrief:
        data = self._call_json(
            self.prompts.load("research_agent"),
            {
                "request": asdict(request),
                "brand_facts": asdict(brand_facts),
            },
        )
        require_keys(data, ["audience_insights", "competitors", "pain_points", "opportunities", "assumptions", "citations"])
        return ResearchBrief(
            brand_facts=brand_facts,
            audience_insights=list_value(data, "audience_insights"),
            competitors=list_value(data, "competitors"),
            pain_points=list_value(data, "pain_points"),
            opportunities=list_value(data, "opportunities"),
            assumptions=list_value(data, "assumptions"),
            citations=list_value(data, "citations", brand_facts.citations),
            # Placeholder — ResearchAgent.run() will override with translate_goal().
            translated_goal=request.goal,
        )

    def strategy(self, request: CampaignRequest, research: ResearchBrief) -> StrategyBrief:
        data = self._call_json(
            self.prompts.load("strategy_agent"),
            {
                "request": asdict(request),
                "research": asdict(research),
            },
        )
        require_keys(
            data,
            [
                "positioning",
                "messaging_pillars",
                "channel_plan",
                "funnel_steps",
                "success_metrics",
                "rejected_angles",
                "risk_flags",
                "hypothesis",
            ],
        )
        return StrategyBrief(
            positioning=str(data["positioning"]),
            messaging_pillars=list_value(data, "messaging_pillars"),
            channel_plan=list_value(data, "channel_plan"),
            funnel_steps=list_value(data, "funnel_steps"),
            success_metrics=list_value(data, "success_metrics"),
            rejected_angles=list_value(data, "rejected_angles"),
            risk_flags=list_value(data, "risk_flags"),
            hypothesis=str(data["hypothesis"]),
        )

    def content(self, request: CampaignRequest, research: ResearchBrief, strategy: StrategyBrief) -> dict[str, object]:
        data = self._call_json(
            self.prompts.load("content_agent"),
            {
                "request": asdict(request),
                "research": asdict(research),
                "strategy": asdict(strategy),
            },
        )
        require_keys(data, ["ad_variants", "social_posts", "email_drafts", "landing_page_copy"])
        return {
            "ad_variants": list_value(data, "ad_variants"),
            "social_posts": list_value(data, "social_posts"),
            "email_drafts": list_value(data, "email_drafts"),
            "landing_page_copy": dict_value(data, "landing_page_copy"),
            "revision_notes": list_value(data, "revision_notes", ["Generated by HTTP JSON model."]),
        }

    def _call_json(self, system_prompt: str, payload: dict[str, object]) -> dict[str, object]:
        api_key = os.environ.get("MARKETING_AGENT_LLM_API_KEY")
        if not api_key:
            raise RuntimeError("Set MARKETING_AGENT_LLM_API_KEY to use HTTP LLM mode")

        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
                ],
                "temperature": 0.4,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LLM API returned HTTP {exc.code}: {exc.reason}\n{body}"
            ) from exc

        content = response_data["choices"][0]["message"]["content"]
        return extract_json_object(content)


class OllamaMarketingModel(HttpJsonMarketingModel):
    """Adapter for a locally running Ollama instance.

    Uses Ollama's OpenAI-compatible endpoint at /v1/chat/completions so
    it can reuse all of HttpJsonMarketingModel's JSON parsing logic.
    No API key is required for local Ollama.

    Usage in config.yaml:
        model_mode: ollama
        ollama_model: qwen2.5:3b
        ollama_base_url: http://localhost:11434

    This enables A/B comparison runs: point the same pipeline at the
    rule-based model and an Ollama model to compare output quality side
    by side in the JSONL log via RunDiagnostics.
    """

    def __init__(self, base_url: str, model: str, prompts: PromptLibrary) -> None:
        # Ensure we always hit the OpenAI-compatible endpoint
        url = base_url.rstrip("/")
        if not url.endswith("/v1/chat/completions"):
            url = f"{url}/v1/chat/completions"
        # Use a longer timeout for local models — large models (e.g. qwen2.5:7b)
        # need time to load into memory on a cold start.
        super().__init__(url, model, prompts, timeout=1800)

    def _call_json(self, system_prompt: str, payload: dict[str, object]) -> dict[str, object]:
        """Override to skip the API key requirement — Ollama runs locally."""
        # Temporarily set a dummy key so the parent's Authorization header is populated.
        # Ollama ignores the Bearer token for local instances.
        original_key = os.environ.get("MARKETING_AGENT_LLM_API_KEY")
        if not original_key:
            os.environ["MARKETING_AGENT_LLM_API_KEY"] = "ollama-local"
        try:
            return super()._call_json(system_prompt, payload)
        finally:
            if not original_key:
                del os.environ["MARKETING_AGENT_LLM_API_KEY"]


class OpenAIMarketingModel(HttpJsonMarketingModel):
    """Adapter for OpenAI's API.
    
    Expects OPENAI_API_KEY to be set. Uses the standard chat completions endpoint.
    """

    def __init__(self, model: str, prompts: PromptLibrary) -> None:
        super().__init__(
            base_url="https://api.openai.com/v1/chat/completions",
            model=model,
            prompts=prompts,
        )

    def _call_json(self, system_prompt: str, payload: dict[str, object]) -> dict[str, object]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Set OPENAI_API_KEY to use the openai model mode")
        
        # Temporarily swap keys for the parent class
        original = os.environ.get("MARKETING_AGENT_LLM_API_KEY")
        os.environ["MARKETING_AGENT_LLM_API_KEY"] = api_key
        try:
            return super()._call_json(system_prompt, payload)
        finally:
            if original is not None:
                os.environ["MARKETING_AGENT_LLM_API_KEY"] = original
            else:
                del os.environ["MARKETING_AGENT_LLM_API_KEY"]


class GeminiMarketingModel(HttpJsonMarketingModel):
    """Adapter for Gemini's OpenAI-compatible API.
    
    Expects GEMINI_API_KEY to be set.
    """

    def __init__(self, model: str, prompts: PromptLibrary) -> None:
        super().__init__(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            model=model,
            prompts=prompts,
        )

    def _call_json(self, system_prompt: str, payload: dict[str, object]) -> dict[str, object]:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY to use the gemini model mode")

        original = os.environ.get("MARKETING_AGENT_LLM_API_KEY")
        os.environ["MARKETING_AGENT_LLM_API_KEY"] = api_key
        try:
            return self._call_with_retry(system_prompt, payload)
        finally:
            if original is not None:
                os.environ["MARKETING_AGENT_LLM_API_KEY"] = original
            else:
                del os.environ["MARKETING_AGENT_LLM_API_KEY"]

    def _call_with_retry(
        self, system_prompt: str, payload: dict[str, object], max_attempts: int = 3
    ) -> dict[str, object]:
        """Call the parent _call_json with automatic 429 retry.

        Reads the retryDelay field from the Gemini error response body and
        waits exactly that long (plus a 2-second buffer) before retrying.
        Falls back to exponential backoff if the field is absent.
        """
        import re

        for attempt in range(1, max_attempts + 1):
            try:
                return super()._call_json(system_prompt, payload)
            except RuntimeError as exc:
                body = str(exc)
                if "429" not in body or attempt == max_attempts:
                    raise

                # Try to read the suggested retryDelay from the Gemini response.
                wait = 60  # default fallback
                match = re.search(r'"retryDelay":\s*"(\d+)', body)
                if match:
                    wait = int(match.group(1)) + 2  # add 2s buffer
                else:
                    wait = min(15 * (2 ** (attempt - 1)), 120)  # 15s, 30s, 60s…

                print(
                    f"[GeminiMarketingModel] rate-limited (attempt {attempt}/{max_attempts}). "
                    f"Waiting {wait}s before retry…"
                )
                time.sleep(wait)
