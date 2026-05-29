from __future__ import annotations

import json
import os
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
    """Deterministic local model for v5 development and tests."""

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
                "The campaign should optimize for a first signup or demo action, not final purchase.",
                "The strongest claims should come from the retrieved brand context or user request.",
            ],
            citations=brand_facts.citations,
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
        style = ", ".join(research.brand_facts.content_style[:2]) or request.tone
        avoid_note = research.brand_facts.avoid[0] if research.brand_facts.avoid else "unsupported claims"
        channels = research.brand_facts.preferred_channels or request.channels
        is_student_campaign = any(
            marker in " ".join([request.audience, research.brand_facts.value_proposition]).lower()
            for marker in ("student", "study", "assignment", "exam", "academic")
        )
        if not is_student_campaign:
            return self._business_content(request, research, strategy, priority, style, avoid_note, channels)

        return {
            "ad_variants": [
                f"Plan your week before it gets messy. {request.product} helps {request.audience} make {priority} feel achievable.",
                f"Assignments, study time, and reminders in one calmer flow. Try {request.product}.",
                f"Make exam prep feel less scattered with a plan you can actually follow.",
                f"Built for {request.audience} who want {priority} without extra pressure.",
                f"Start with one plan today. Let {request.product} help you {request.goal}.",
            ],
            "social_posts": [
                self._social_post(channel, request, strategy, priority, style)
                for channel in channels
            ],
            "email_drafts": [
                {
                    "subject": "A calmer way to plan your study week",
                    "body": (
                        f"Hi there,\n\nIf your schedule keeps changing, {request.product} can help you organize "
                        f"assignments, study time, and reminders around {priority}.\n\n"
                        "Start with one plan and adjust as your week changes."
                    ),
                },
                {
                    "subject": "Less scrambling before exams",
                    "body": (
                        f"Hi there,\n\n{request.product} helps {request.audience} turn deadlines and exam prep "
                        "into a practical plan with reminders.\n\n"
                        "Simple planning support for the next thing on your list."
                    ),
                },
                {
                    "subject": "Keep study plans consistent",
                    "body": (
                        f"Hi there,\n\nWhen classes, assignments, and personal life compete for attention, "
                        f"{request.product} helps keep the plan visible and manageable.\n\n"
                        "Try it for your next study week."
                    ),
                },
            ],
            "landing_page_copy": {
                "headline": f"Plan study weeks that feel easier to follow",
                "subheadline": (
                    f"{request.product} helps {request.audience} organize assignments, study schedules, "
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
    ) -> dict[str, object]:
        return {
            "ad_variants": [
                f"Turn scattered campaign work into a clearer plan. {request.product} helps {request.audience} make {priority} feel achievable.",
                f"Keep strategy, copy, and review moving in the same direction with {request.product}.",
                f"Built for {request.audience} who need consistent campaigns without extra process.",
                f"Make {request.goal} easier to execute with messaging your team can review faster.",
                f"Start with one campaign promise, then adapt it across channels with {request.product}.",
            ],
            "social_posts": [
                self._business_social_post(channel, request, strategy, priority, style)
                for channel in channels
            ],
            "email_drafts": [
                {
                    "subject": f"A clearer path to {request.goal}",
                    "body": (
                        f"Hi there,\n\nIf your team is trying to {request.goal}, {request.product} can help turn "
                        f"campaign ideas into practical assets while keeping the message focused on {priority}.\n\n"
                        "Want to see a sample campaign package?"
                    ),
                },
                {
                    "subject": "Keep every campaign asset aligned",
                    "body": (
                        f"Hi there,\n\n{request.audience} often lose time when strategy, copy, and review happen in separate places. "
                        f"{request.product} keeps the campaign direction clearer from the start.\n\n"
                        "Happy to share what that workflow looks like."
                    ),
                },
                {
                    "subject": "More variants, less message drift",
                    "body": (
                        f"Hi there,\n\nWhen the goal is {request.goal}, every channel needs to carry the same promise. "
                        f"{request.product} helps create variants without losing the core idea.\n\n"
                        "Can I send over an example?"
                    ),
                },
            ],
            "landing_page_copy": {
                "headline": f"Build campaigns that help {request.audience} {request.goal}",
                "subheadline": (
                    f"{request.product} helps teams turn strategy into ads, posts, emails, and landing page copy "
                    f"with {style} execution."
                ),
                "primary_cta": "Generate my campaign",
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

    def __init__(self, base_url: str, model: str, prompts: PromptLibrary) -> None:
        if not base_url or not model:
            raise ValueError("HTTP LLM mode requires llm_base_url and llm_model in config")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompts = prompts

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
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))

        content = response_data["choices"][0]["message"]["content"]
        return extract_json_object(content)
