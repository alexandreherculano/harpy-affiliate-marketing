"""Standalone Script Agent — generate short-form video scripts, captions, and hashtags.

Uses DeepSeek API with affiliate-skills (tiktok-script-writer, viral-post-writer).
Outputs ready-to-film scripts for TikTok and Instagram Reels.
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
class ScriptOutput:
    title: str = ""
    hook: str = ""
    script: str = ""
    duration: str = ""
    cta: str = ""
    raw: str = ""


@dataclass
class CaptionOutput:
    primary: str = ""
    alternatives: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class HashtagOutput:
    tags: list[str] = field(default_factory=list)
    grouped: dict[str, list[str]] = field(default_factory=dict)
    raw: str = ""


@dataclass
class ScriptResult:
    niche: str
    product_name: str
    script_tiktok: ScriptOutput = field(default_factory=ScriptOutput)
    script_instagram: ScriptOutput = field(default_factory=ScriptOutput)
    captions: CaptionOutput = field(default_factory=CaptionOutput)
    hashtags: HashtagOutput = field(default_factory=HashtagOutput)
    summary: str = ""


class ScriptAgent:
    """Generates short-form video scripts, captions, and hashtags for affiliate content."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config(require_api_key=False)
        self.client = DeepSeekClient(self.config)
        self.loader = SkillLoader(self.config.skills_dir)

    def generate_script(
        self,
        product_name: str,
        niche: str,
        platforms: list[str] | None = None,
        research_context: str = "",
        dry_run: bool = False,
        language: str = "en",
    ) -> dict[str, ScriptOutput]:
        """Generate short-form video scripts for each target platform.

        Uses skill: tiktok-script-writer
        """
        if platforms is None:
            platforms = ["tiktok", "instagram"]

        skill = self.loader.get("tiktok-script-writer")
        if not skill:
            raise RuntimeError("Skill 'tiktok-script-writer' not found.")

        results: dict[str, ScriptOutput] = {}
        is_pt = language.startswith("pt")

        for platform in platforms:
            if dry_run:
                results[platform] = self._mock_script(niche, product_name, platform, language)
                continue

            if is_pt:
                prompt = (
                    f"Escreva um roteiro de vídeo curto para **{platform.upper()}** "
                    f"(compatível com {'Instagram Reels' if platform == 'tiktok' else 'TikTok'}).\n\n"
                    f"**Produto:** {product_name}\n"
                    f"**Nicho:** {niche}\n"
                    f"**Formato:** 9:16 vertical, 15-60 segundos\n"
                )
                if research_context:
                    prompt += f"\n**Dados da pesquisa:**\n{research_context}\n"

                prompt += (
                    f"\nCrie um roteiro com estas seções:\n"
                    f"1. **GANCHO** (3 primeiros segundos — pare o scroll)\n"
                    f"2. **PROBLEMA** (qual dor {product_name} resolve)\n"
                    f"3. **DEMONSTRAÇÃO** (mostre o produto em ação)\n"
                    f"4. **RESULTADO** (transformação ou benefício)\n"
                    f"5. **CTA** (chamada para ação — link na bio, etc.)\n\n"
                    f"Inclua:\n"
                    f"- Direções visuais [entre colchetes]\n"
                    f"- Tempo estimado por seção\n"
                    f"- Boas práticas para {platform}\n\n"
                    f"Responda em português brasileiro. Após o roteiro, gere um bloco JSON:\n"
                    f'{{"title": "...", "hook": "...", "duration": "...", "cta": "...", '
                    f'"script": "texto completo do roteiro"}}'
                )
            else:
                prompt = (
                    f"Write a short-form video script for **{platform.upper()}** "
                    f"(also compatible with {'Instagram Reels' if platform == 'tiktok' else 'TikTok'}).\n\n"
                    f"**Product:** {product_name}\n"
                    f"**Niche:** {niche}\n"
                    f"**Target format:** 9:16 vertical, 15-60 seconds\n"
                )
                if research_context:
                    prompt += f"\n**Research data:**\n{research_context}\n"

                prompt += (
                    f"\nCreate a script with these sections clearly labeled:\n"
                    f"1. **HOOK** (first 3 seconds — stop the scroll)\n"
                    f"2. **PROBLEM** (what pain point does {product_name} solve)\n"
                    f"3. **DEMO** (show the product in action, key benefit)\n"
                    f"4. **RESULT** (transformation or outcome)\n"
                    f"5. **CTA** (call to action — check bio, link below, etc.)\n\n"
                    f"Include:\n"
                    f"- Visual directions [in brackets]\n"
                    f"- Estimated timing per section\n"
                    f"- Platform-specific best practices for {platform}\n\n"
                    f"After your script, output a JSON block:\n"
                    f'{{"title": "...", "hook": "...", "duration": "...", "cta": "...", '
                    f'"script": "full script text"}}'
                )

            raw = self._call_skill(skill, prompt)
            parsed = self._parse_json(raw)

            results[platform] = ScriptOutput(
                title=parsed.get("title", f"{product_name} — {platform}"),
                hook=parsed.get("hook", ""),
                script=parsed.get("script", raw),
                duration=parsed.get("duration", "30s"),
                cta=parsed.get("cta", "Link in bio!"),
                raw=raw,
            )

        return results

    def generate_captions(
        self,
        product_name: str,
        script_text: str = "",
        niche: str = "",
        dry_run: bool = False,
        language: str = "en",
    ) -> CaptionOutput:
        """Generate Instagram/TikTok caption options using viral-post-writer.

        Uses skill: viral-post-writer
        """
        skill = self.loader.get("viral-post-writer")
        if not skill:
            raise RuntimeError("Skill 'viral-post-writer' not found.")

        if dry_run:
            return self._mock_captions(product_name, language)

        is_pt = language.startswith("pt")

        if is_pt:
            prompt = (
                f"Escreva 3 opções de legenda para Instagram/TikTok promovendo **{product_name}**.\n\n"
                f"Nicho: {niche}\n"
            )
        else:
            prompt = (
                f"Write 3 Instagram/TikTok caption options for a video promoting **{product_name}**.\n\n"
                f"Niche: {niche}\n"
            )
        if script_text:
            prompt += f"Contexto do roteiro:\n```\n{script_text[:1000]}\n```\n\n"

        if is_pt:
            prompt += (
                "Gere:\n"
                "1. **Legenda principal** — otimizada com emojis, quebras de linha e CTA suave\n"
                "2. **Alternativa A** — mais curta, com pergunta impactante\n"
                "3. **Alternativa B** — formato história, mais longa com valor educativo\n\n"
                "Inclua divulgação de afiliado (FTC) em cada legenda.\n\n"
                "Responda em português brasileiro. Após as legendas, gere um bloco JSON:\n"
                '{"primary": "...", "alternatives": ["...", "..."]}'
            )
        else:
            prompt += (
                "Generate:\n"
                "1. **Primary caption** — optimized with emojis, line breaks, and a soft CTA\n"
                "2. **Alternative A** — shorter, punchy, question-based hook\n"
                "3. **Alternative B** — story-driven, longer form with value teaching\n\n"
                "Include FTC-compliant affiliate disclosure in each caption.\n\n"
                "After your captions, output a JSON block:\n"
                '{"primary": "...", "alternatives": ["...", "..."]}'
            )

        raw = self._call_skill(skill, prompt)
        parsed = self._parse_json(raw)

        return CaptionOutput(
            primary=parsed.get("primary", raw),
            alternatives=parsed.get("alternatives", []),
            raw=raw,
        )

    def generate_hashtags(
        self,
        topic: str,
        niche: str = "",
        platform: str = "tiktok",
        dry_run: bool = False,
        language: str = "en",
    ) -> HashtagOutput:
        """Generate optimized hashtag sets for TikTok and Instagram.

        No specific skill slug — uses prompt engineering with DeepSeek directly.
        """
        if dry_run:
            return self._mock_hashtags(topic, platform, language)

        is_pt = language.startswith("pt")

        if is_pt:
            prompt = (
                f"Gere uma estratégia de hashtags para um post no **{platform.upper()}** "
                f"sobre **{topic}**.\n\n"
                f"Nicho: {niche}\n\n"
                "Gere hashtags agrupadas por categoria:\n"
                "1. **AMPLAS** — 3-5 tags grandes (1M+ posts) para alcance\n"
                "2. **NICHO** — 5-8 tags médias (50K-500K) para descoberta\n"
                "3. **ESPECÍFICAS** — 3-5 tags pequenas (<50K) para fidelidade do algoritmo\n\n"
                f"Total: 12-18 hashtags otimizadas para {platform}.\n"
                "Responda em português brasileiro.\n\n"
                "Após as tags, gere um bloco JSON:\n"
                '{"tags": ["..."], "grouped": {"broad": ["..."], "niche": ["..."], "specific": ["..."]}}'
            )
            system_prompt = (
                "Você é um estrategista de hashtags para marketing de afiliados. "
                "Gere hashtags otimizadas para cada plataforma que maximizem alcance "
                "e descoberta. Responda em português brasileiro com JSON estruturado."
            )
        else:
            prompt = (
                f"Generate an optimized hashtag strategy for a **{platform.upper()}** post "
                f"about **{topic}**.\n\n"
                f"Niche: {niche}\n\n"
                "Generate hashtags grouped by category:\n"
                "1. **BROAD** — 3-5 large tags (1M+ posts) for reach\n"
                "2. **NICHE** — 5-8 medium tags (50K-500K) for targeted discovery\n"
                "3. **SPECIFIC** — 3-5 small tags (<50K) for algorithm loyalty\n\n"
                f"Total: 12-18 hashtags optimized for {platform}.\n\n"
                "After your tags, output a JSON block:\n"
                '{"tags": ["..."], "grouped": {"broad": ["..."], "niche": ["..."], "specific": ["..."]}}'
            )
            system_prompt = (
                "You are a hashtag strategist for social media affiliate marketing. "
                "Generate optimized, platform-specific hashtag sets that maximize reach "
                "and discovery. Output clean, structured JSON."
            )

        response = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt,
        )

        parsed = self._parse_json(response.content)

        return HashtagOutput(
            tags=parsed.get("tags", []),
            grouped=parsed.get("grouped", {}),
            raw=response.content,
        )

    def run_full_script(
        self,
        product_name: str,
        niche: str,
        platforms: list[str] | None = None,
        research_context: str = "",
        dry_run: bool = False,
        language: str = "en",
    ) -> ScriptResult:
        """Run all script generation steps and return consolidated output."""
        if platforms is None:
            platforms = ["tiktok", "instagram"]

        logger.info(
            "ScriptAgent starting — product=%s niche=%s dry_run=%s lang=%s",
            product_name,
            niche,
            dry_run,
            language,
        )

        scripts = self.generate_script(
            product_name=product_name,
            niche=niche,
            platforms=platforms,
            research_context=research_context,
            dry_run=dry_run,
            language=language,
        )

        tiktok_script = scripts.get("tiktok", ScriptOutput())
        combined_text = tiktok_script.script or ""

        captions = self.generate_captions(
            product_name=product_name,
            script_text=combined_text,
            niche=niche,
            dry_run=dry_run,
            language=language,
        )

        hashtags = self.generate_hashtags(
            topic=product_name,
            niche=niche,
            platform=platforms[0],
            dry_run=dry_run,
            language=language,
        )

        summary_lines = [
            f"Scripts generated for {len(scripts)} platform(s): {', '.join(scripts.keys())}.",
        ]
        if platforms[0] and tiktok_script.hook:
            summary_lines.append(f"TikTok hook: \"{tiktok_script.hook}\"")
        if captions.primary:
            first_line = captions.primary.split("\n")[0][:100]
            summary_lines.append(f"Primary caption: \"{first_line}...\"")
        if hashtags.tags:
            summary_lines.append(f"Hashtags: {len(hashtags.tags)} tags generated")

        logger.info("ScriptAgent complete for: %s", product_name)
        return ScriptResult(
            niche=niche,
            product_name=product_name,
            script_tiktok=scripts.get("tiktok", ScriptOutput()),
            script_instagram=scripts.get("instagram", ScriptOutput()),
            captions=captions,
            hashtags=hashtags,
            summary="\n".join(summary_lines),
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
        import json
        import re

        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}

    def _mock_script(
        self, niche: str, product: str, platform: str, language: str = "en"
    ) -> ScriptOutput:
        platform_name = {"tiktok": "TikTok", "instagram": "Instagram Reels"}.get(
            platform, platform
        )
        is_pt = language.startswith("pt")

        if is_pt:
            return ScriptOutput(
                title=f"Review {product} — {platform_name}",
                hook=f"Pare de comprar produtos de {niche} que não funcionam. Eu achei O certo.",
                script=(
                    f"[GANCHO — 0-3s]\n"
                    f"🎬 【Texto: \"Pare de gastar dinheiro com {niche}\"】\n"
                    f"Voz: \"Testei 5 produtos de {niche}. Só UM entregou resultado.\"\n\n"
                    f"[PROBLEMA — 3-10s]\n"
                    f"【B-roll de usuário frustrado com produtos concorrentes】\n"
                    f"Voz: \"A maioria dos produtos de {niche} promete e não entrega.\"\n\n"
                    f"[DEMONSTRAÇÃO — 10-25s]\n"
                    f"【Gravação de tela do {product} em ação】\n"
                    f"Voz: \"Aí eu encontrei {product}. Olha o que aconteceu...\"\n\n"
                    f"[RESULTADO — 25-35s]\n"
                    f"【Tela dividida Antes/Depois】\n"
                    f"Voz: \"Em apenas 7 dias, tudo mudou.\"\n\n"
                    f"[CTA — 35-40s]\n"
                    f"【Apontar para baixo/comentários/bio】\n"
                    f"Voz: \"Link na bio pra garantir o seu {product}. De nada.\""
                ),
                duration="40s",
                cta="Link na bio pra garantir o seu!",
                raw="[DRY RUN] Roteiro simulado — sem chamada de API.",
            )

        return ScriptOutput(
            title=f"{product} Review — {platform_name}",
            hook=f"Stop buying {niche} products that don't work. I found THE one.",
            script=(
                f"[HOOK — 0-3s]\n"
                f"🎬 【Text overlay: \"Stop wasting money on {niche} gadgets\"】\n"
                f"Voice: \"I tested 5 {niche} devices. Only ONE actually delivered.\"\n\n"
                f"[PROBLEM — 3-10s]\n"
                f"【B-roll of frustrated user with competing products】\n"
                f"Voice: \"Most {niche} products overpromise and underdeliver.\"\n\n"
                f"[DEMO — 10-25s]\n"
                f"【Screen recording of {product} in action】\n"
                f"Voice: \"Then I found {product}. Here's what happened...\"\n\n"
                f"[RESULT — 25-35s]\n"
                f"【Before/After split screen】\n"
                f"Voice: \"In just 7 days, everything changed.\"\n\n"
                f"[CTA — 35-40s]\n"
                f"【Point down to comments/bio】\n"
                f"Voice: \"Link in bio to get {product}. You're welcome.\""
            ),
            duration="40s",
            cta="Link in bio to get yours!",
            raw="[DRY RUN] Mock script — no API call made.",
        )

    def _mock_captions(self, product: str, language: str = "en") -> CaptionOutput:
        is_pt = language.startswith("pt")

        if is_pt:
            return CaptionOutput(
                primary=(
                    f"🚨 Finalmente encontrei o {product} que funciona de verdade.\n\n"
                    f"Depois de testar 5 opções diferentes, esse se destaca. "
                    f"Olha o porquê 👇\n\n"
                    f"Review completa no link da bio.\n\n"
                    f"#publi #afiliado"
                ),
                alternatives=[
                    f"Qual é o melhor {product} que você recomendaria? "
                    f"O meu tá no link da bio. #afiliado",
                    f"Gastei R$500 testando alternativas de {product} pra você não precisar. "
                    f"O que eu aprendi... 🧵",
                ],
                raw="[DRY RUN] Legendas simuladas — sem chamada de API.",
            )

        return CaptionOutput(
            primary=(
                f"🚨 I finally found the {product} that actually works.\n\n"
                f"After testing 5 different options, this one stands out. "
                f"Here's why 👇\n\n"
                f"Full review in my bio.\n\n"
                f"#ad #affiliate"
            ),
            alternatives=[
                f"What's the ONE {product} you'd recommend to a friend? "
                f"Mine is linked in bio. #affiliate",
                f"I spent $500 testing {product} alternatives so you don't have to. "
                f"Here's what I learned... 🧵",
            ],
            raw="[DRY RUN] Mock captions — no API call made.",
        )

    def _mock_hashtags(self, topic: str, platform: str, language: str = "en") -> HashtagOutput:
        is_pt = language.startswith("pt")

        if is_pt:
            return HashtagOutput(
                tags=[
                    f"#{topic.replace(' ', '')}",
                    "#Review",
                    "#Tecnologia",
                    "#ReviewProduto",
                    "#CadeiraGamer",
                    "#SetupGamer",
                    "#DicaTech",
                    "#Imperdivel",
                    "#ReviewHonesta",
                ],
                grouped={
                    "broad": ["#Tecnologia", "#Review", "#DicaTech"],
                    "niche": [
                        f"#{topic.replace(' ', '')}",
                        "#SetupGamer",
                        "#CadeiraGamer",
                    ],
                    "specific": ["#ReviewProduto", "#Imperdivel", "#ReviewHonesta"],
                },
                raw="[DRY RUN] Hashtags simuladas — sem chamada de API.",
            )

        return HashtagOutput(
            tags=[
                f"#{topic.replace(' ', '')}",
                f"#{topic.replace(' ', '')}Review",
                "#TechReview",
                "#SmartHome",
                "#GadgetReview",
                "#TikTokMadeMeBuyIt",
                "#MustHave",
                "#HomeTech",
                "#LifeHack",
                "#ProductReview",
            ],
            grouped={
                "broad": ["#TechReview", "#SmartHome", "#GadgetReview"],
                "niche": [
                    f"#{topic.replace(' ', '')}",
                    f"#{topic.replace(' ', '')}Review",
                    "#TikTokMadeMeBuyIt",
                ],
                "specific": ["#HomeTech", "#LifeHack", "#ProductReview", "#MustHave"],
            },
            raw="[DRY RUN] Mock hashtags — no API call made.",
        )
