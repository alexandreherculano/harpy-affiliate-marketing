"""Standalone Research Agent — discover trends, find programs, analyze traffic.

Uses DeepSeek API with affiliate-skills as system prompts.
Can run independently or as S1 of the full Harpy flywheel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config import Config, load_config
from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.skill_loader import Skill, SkillLoader

logger = get_logger()


@dataclass
class TrendResult:
    niche: str
    top_format: str = ""
    avg_engagement: float = 0.0
    best_hook: str = ""
    content_gap: str = ""
    benchmark_views: int = 0
    raw: str = ""


@dataclass
class ProgramResult:
    product_name: str = ""
    slug: str = ""
    commission: str = ""
    cookie_days: int = 0
    stars: int = 0
    traffic_score: int = 0
    justification: str = ""
    raw: str = ""


@dataclass
class TrafficResult:
    product_name: str = ""
    monthly_visits: str = ""
    global_rank: str = ""
    bounce_rate: str = ""
    top_sources: list[str] = field(default_factory=list)
    score: int = 0
    verdict: str = ""
    raw: str = ""


@dataclass
class ResearchOutput:
    niche: str
    trends: TrendResult | None = None
    program: ProgramResult | None = None
    traffic: TrafficResult | None = None
    summary: str = ""


class ResearchAgent:
    """Executes S1 research skills: trends → programs → traffic analysis."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        self.client = DeepSeekClient(self.config)
        self.loader = SkillLoader(self.config.skills_dir)

    def discover_trends(self, niche: str, dry_run: bool = False, language: str = "en") -> TrendResult:
        """Scout trending content on TikTok, YouTube, Reddit, Instagram for the niche.

        Uses skill: trending-content-scout
        """
        skill = self.loader.get("trending-content-scout")
        if not skill:
            raise RuntimeError("Skill 'trending-content-scout' not found.")

        if dry_run:
            return self._mock_trends(niche, language)

        if language.startswith("pt"):
            prompt = (
                f"Pesquise conteúdo em alta no nicho: **{niche}**.\n\n"
                f"Plataformas: TikTok, Instagram Reels, YouTube Shorts, Reddit.\n"
                f"Encontre:\n"
                f"1. Formato de conteúdo com melhor desempenho (comparação, demo, tutorial, react)\n"
                f"2. Média de engajamento\n"
                f"3. Melhor gancho (hook)\n"
                f"4. Lacunas de conteúdo (o que ninguém está cobrindo)\n"
                f"5. Visualizações de referência para o top 10%\n\n"
                f"Responda em português brasileiro. Após a análise, gere um bloco JSON:\n"
                f'{{"top_format": "...", "avg_engagement": number, "best_hook": "...", '
                f'"content_gap": "...", "benchmark_views": number}}'
            )
        else:
            prompt = (
                f"Research trending content for the niche: **{niche}**.\n\n"
                f"Target platforms: TikTok, Instagram Reels, YouTube Shorts, Reddit.\n"
                f"Find:\n"
                f"1. Top performing content format (comparison, demo, tutorial, reaction)\n"
                f"2. Average engagement metrics\n"
                f"3. Best performing hook or angle\n"
                f"4. Content gaps (what nobody is covering)\n"
                f"5. Benchmark views needed to reach top 10%\n\n"
                f"After your analysis, output a JSON block with these exact fields:\n"
                f'{{"top_format": "...", "avg_engagement": number, "best_hook": "...", '
                f'"content_gap": "...", "benchmark_views": number}}'
            )

        raw = self._call_skill(skill, prompt)
        parsed = self._parse_json(raw)

        return TrendResult(
            niche=niche,
            top_format=parsed.get("top_format", ""),
            avg_engagement=float(parsed.get("avg_engagement", 0)),
            best_hook=parsed.get("best_hook", ""),
            content_gap=parsed.get("content_gap", ""),
            benchmark_views=int(parsed.get("benchmark_views", 0)),
            raw=raw,
        )

    def find_affiliate_programs(self, query: str, dry_run: bool = False, language: str = "en") -> ProgramResult:
        """Search for high-commission affiliate programs matching the query.

        Uses skill: affiliate-program-search
        """
        skill = self.loader.get("affiliate-program-search")
        if not skill:
            raise RuntimeError("Skill 'affiliate-program-search' not found.")

        if dry_run:
            return self._mock_program(query, language)

        if language.startswith("pt"):
            prompt = (
                f"Encontre o melhor programa de afiliados para: **{query}**.\n\n"
                f"Use a API openaffiliate.dev ou busca web para encontrar programas.\n"
                f"Compare taxas de comissão, duração de cookies, avaliações.\n"
                f"Recomende o melhor programa para promover.\n\n"
                f"Responda em português brasileiro. Após a análise, gere um bloco JSON:\n"
                f'{{"product_name": "...", "slug": "...", "commission": "...", '
                f'"cookie_days": number, "stars": number, "traffic_score": number, '
                f'"justification": "..."}}'
            )
        else:
            prompt = (
                f"Find the best affiliate program for: **{query}**.\n\n"
                f"Use the openaffiliate.dev API or web search to find programs.\n"
                f"Compare commission rates, cookie duration, star ratings.\n"
                f"Recommend the SINGLE best program to promote.\n\n"
                f"After your analysis, output a JSON block:\n"
                f'{{"product_name": "...", "slug": "...", "commission": "...", '
                f'"cookie_days": number, "stars": number, "traffic_score": number, '
                f'"justification": "..."}}'
            )

        raw = self._call_skill(skill, prompt)
        parsed = self._parse_json(raw)

        return ProgramResult(
            product_name=parsed.get("product_name", query),
            slug=parsed.get("slug", ""),
            commission=parsed.get("commission", ""),
            cookie_days=int(parsed.get("cookie_days", 0)),
            stars=int(parsed.get("stars", 0)),
            traffic_score=int(parsed.get("traffic_score", 0)),
            justification=parsed.get("justification", ""),
            raw=raw,
        )

    def analyze_traffic(self, product: str, dry_run: bool = False, language: str = "en") -> TrafficResult:
        """Analyze website traffic and advertiser health for a product/domain.

        Uses skill: traffic-analyzer
        """
        skill = self.loader.get("traffic-analyzer")
        if not skill:
            raise RuntimeError("Skill 'traffic-analyzer' not found.")

        if dry_run:
            return self._mock_traffic(product, language)

        if language.startswith("pt"):
            prompt = (
                f"Analise o tráfego do site: **{product}**.\n\n"
                f"Avalie:\n"
                f"1. Estimativa de visitas mensais\n"
                f"2. Ranking global\n"
                f"3. Taxa de rejeição\n"
                f"4. Principais fontes de tráfego\n"
                f"5. Nota geral (0-100) e veredito\n\n"
                f"Responda em português brasileiro. Após a análise, gere um bloco JSON:\n"
                f'{{"product_name": "...", "monthly_visits": "...", "global_rank": "...", '
                f'"bounce_rate": "...", "top_sources": ["..."], "score": number, '
                f'"verdict": "..."}}'
            )
        else:
            prompt = (
                f"Analyze website traffic and health for: **{product}**.\n\n"
                f"Evaluate:\n"
                f"1. Monthly visits estimate\n"
                f"2. Global rank\n"
                f"3. Bounce rate\n"
                f"4. Top traffic sources\n"
                f"5. Overall score (0-100) and verdict on whether it's worth promoting\n\n"
                f"After your analysis, output a JSON block:\n"
                f'{{"product_name": "...", "monthly_visits": "...", "global_rank": "...", '
                f'"bounce_rate": "...", "top_sources": ["..."], "score": number, '
                f'"verdict": "..."}}'
            )

        raw = self._call_skill(skill, prompt)
        parsed = self._parse_json(raw)

        return TrafficResult(
            product_name=parsed.get("product_name", product),
            monthly_visits=parsed.get("monthly_visits", ""),
            global_rank=parsed.get("global_rank", ""),
            bounce_rate=parsed.get("bounce_rate", ""),
            top_sources=parsed.get("top_sources", []),
            score=int(parsed.get("score", 0)),
            verdict=parsed.get("verdict", ""),
            raw=raw,
        )

    def run_full_research(
        self,
        niche: str,
        dry_run: bool = False,
        language: str = "en",
    ) -> ResearchOutput:
        """Run all 3 research steps and return consolidated output."""
        logger.info("ResearchAgent starting for niche: %s (dry_run=%s, lang=%s)", niche, dry_run, language)

        trends = self.discover_trends(niche, dry_run=dry_run, language=language)

        program_query = niche
        if trends.top_format:
            program_query = f"{niche} {trends.top_format} tools"

        program = self.find_affiliate_programs(program_query, dry_run=dry_run, language=language)

        product_name = program.product_name or niche
        traffic = self.analyze_traffic(product_name, dry_run=dry_run, language=language)

        summary = self._build_summary(trends, program, traffic, language)

        logger.info("ResearchAgent complete for: %s", niche)
        return ResearchOutput(
            niche=niche,
            trends=trends,
            program=program,
            traffic=traffic,
            summary=summary,
        )

    def _call_skill(self, skill: Skill, prompt: str) -> str:
        logger.info("Calling skill: %s", skill.slug)
        response = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=skill.system_prompt,
        )
        logger.info(
            "Skill %s complete — %d tokens",
            skill.slug,
            response.usage.total_tokens,
        )
        return response.content

    def _parse_json(self, raw: str) -> dict[str, Any]:
        import re

        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}

    def _build_summary(
        self,
        trends: TrendResult,
        program: ProgramResult,
        traffic: TrafficResult,
        language: str = "en",
    ) -> str:
        parts: list[str] = []
        is_pt = language.startswith("pt")

        if trends.top_format:
            if is_pt:
                parts.append(
                    f"Nicho **{trends.niche}**: melhor formato é **{trends.top_format}** "
                    f"(engajamento médio {trends.avg_engagement:.1f}). "
                    f"Melhor gancho: \"{trends.best_hook}\"."
                )
            else:
                parts.append(
                    f"Niche **{trends.niche}**: top format is **{trends.top_format}** "
                    f"(avg engagement {trends.avg_engagement:.1f}). "
                    f"Best hook: \"{trends.best_hook}\"."
                )

        if program.product_name:
            if is_pt:
                parts.append(
                    f"Recomendado: **{program.product_name}** — "
                    f"comissão de {program.commission}, "
                    f"cookie de {program.cookie_days} dias, "
                    f"{program.stars} estrelas."
                )
            else:
                parts.append(
                    f"Recommended: **{program.product_name}** — "
                    f"{program.commission} commission, "
                    f"{program.cookie_days}-day cookie, "
                    f"{program.stars} stars."
                )

        if traffic.verdict:
            if is_pt:
                parts.append(
                    f"Tráfego: {traffic.monthly_visits} visitas/mês, "
                    f"nota {traffic.score}/100. {traffic.verdict}"
                )
            else:
                parts.append(
                    f"Traffic: {traffic.monthly_visits} visits/mo, "
                    f"score {traffic.score}/100. {traffic.verdict}"
                )

        if program.justification:
            if is_pt:
                parts.append(f"Motivo: {program.justification}")
            else:
                parts.append(f"Why: {program.justification}")

        if trends.content_gap:
            if is_pt:
                parts.append(f"Lacuna: {trends.content_gap}")
            else:
                parts.append(f"Gap: {trends.content_gap}")

        return "\n\n".join(parts)

    # Mock data for dry-run mode

    def _mock_trends(self, niche: str, language: str = "en") -> TrendResult:
        is_pt = language.startswith("pt")
        return TrendResult(
            niche=niche,
            top_format="comparação" if is_pt else "comparison",
            avg_engagement=35.2,
            best_hook=(
                f"Testei os 3 melhores produtos de {niche} pra você não precisar"
                if is_pt else
                f"I tested the top 3 {niche} tools so you don't have to"
            ),
            content_gap=(
                f"Ninguém está fazendo comparações honestas de {niche} no TikTok"
                if is_pt else
                f"No one is doing honest side-by-side {niche} comparisons on TikTok"
            ),
            benchmark_views=18000,
            raw="[DRY RUN] Dados simulados — sem chamada de API." if is_pt else "[DRY RUN] Mock trend data — no API call made.",
        )

    def _mock_program(self, query: str, language: str = "en") -> ProgramResult:
        is_pt = language.startswith("pt")
        return ProgramResult(
            product_name=f"Melhor Programa de {query.title()}" if is_pt else f"Top {query} Program",
            slug=query.lower().replace(" ", "-"),
            commission="30% recorrente" if is_pt else "30% recurring",
            cookie_days=60,
            stars=127,
            traffic_score=85,
            justification=(
                f"Maior comissão no nicho de {query} com modelo recorrente e cookie longo."
                if is_pt else
                f"Highest commission in the {query} space with recurring model and long cookie window."
            ),
            raw="[DRY RUN] Dados simulados — sem chamada de API." if is_pt else "[DRY RUN] Mock program data — no API call made.",
        )

    def _mock_traffic(self, product: str, language: str = "en") -> TrafficResult:
        is_pt = language.startswith("pt")
        return TrafficResult(
            product_name=product,
            monthly_visits="2,1M" if is_pt else "2.1M",
            global_rank="#45.230",
            bounce_rate="42%",
            top_sources=(
                ["Direto (35%)", "Busca Orgânica (28%)", "Social (18%)"]
                if is_pt else
                ["Direct (35%)", "Organic Search (28%)", "Social (18%)"]
            ),
            score=82,
            verdict=(
                "Anunciante forte — mix de tráfego saudável e baixa taxa de rejeição. Vale promover."
                if is_pt else
                "Strong advertiser — healthy traffic mix and low bounce rate. Worth promoting."
            ),
            raw="[DRY RUN] Dados simulados — sem chamada de API." if is_pt else "[DRY RUN] Mock traffic data — no API call made.",
        )
