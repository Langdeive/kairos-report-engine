"""Record != execution. Trusted evidence is separate from author-supplied claims.

Helpers must declare all semantic claims (including those introduced by review).
The legacy Portuguese guard is conservative defense in depth, not an NLP proof.
Never derive execution evidence or topic sample sizes from aggregate counts.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from selectolax.parser import HTMLParser, Node

from kairos_report.errors import KairosReportError
from kairos_report.schemas import QuestionTopicMetric, TopicSourcePeriod


class ProvenanceError(KairosReportError):
    """Sanitized reason only; never include source text or identities."""


class AnalysisClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "recorded",
        "execution",
        "practice",
        "study",
        "mastery",
        "topic_positive",
        "topic_attention",
        "percentage",
    ]
    scope: Literal["overall", "discipline", "topic"] = "overall"
    discipline: str | None = None
    topic: str | None = None
    value: float | None = None


def enrich_topic_metrics(
    html: str,
    topics: Sequence[QuestionTopicMetric],
    *,
    period_start: date,
    period_end: date,
) -> list[QuestionTopicMetric]:
    """Pure opt-in enrichment from caller-supplied individual launch HTML.

    Exact discipline/topic keys only. Summary cells and parent totals are never
    evidence. Each dated launch remains a *record*, not verified execution.
    Caller owns acquisition/identity/completeness of this HTML; no network here.
    """
    if period_start > period_end:
        raise ProvenanceError("topic_launch_invalid")
    tree = HTMLParser(html)
    result = []
    for topic in topics:
        launches: list[Node] = []
        has_non_launch_row = False
        for row in tree.css("tr"):
            cells = row.css("td")
            if len(cells) < 2:
                continue
            if (cells[0].text(strip=True), cells[1].text(strip=True)) != (
                topic.discipline,
                topic.topic,
            ):
                continue
            if len(cells) != 6:
                # Summaries alone stay unknown; mixed rows cannot prove completeness.
                has_non_launch_row = True
                if any(
                    key in a.attributes
                    for a in row.css("a")
                    for key in ("data-data", "data-questoes", "data-acertos")
                ):
                    raise ProvenanceError("topic_launch_invalid")
                continue
            row_launches = cells[5].css("a")
            # A six-cell detail row must not silently discard missing launch evidence.
            if not row_launches:
                raise ProvenanceError("topic_launch_invalid")
            launches.extend(row_launches)
        if launches and has_non_launch_row:
            raise ProvenanceError("topic_launch_invalid")
        data = topic.model_dump()
        data.update(
            total=None, correct=None, wrong=None, source_period=None, execution_status="unknown"
        )
        if launches:
            total = correct = 0
            seen_dates: set[date] = set()
            for launch in launches:
                attrs = launch.attributes
                try:
                    day_token = str(attrs["data-data"])
                    total_token = str(attrs["data-questoes"])
                    correct_token = str(attrs["data-acertos"])
                    if (
                        not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_token)
                        or not re.fullmatch(r"\d+", total_token)
                        or not re.fullmatch(r"\d+", correct_token)
                    ):
                        raise ValueError
                    day = date.fromisoformat(day_token)
                    launch_total, launch_correct = int(total_token), int(correct_token)
                    if launch_correct > launch_total:
                        raise ValueError
                except (KeyError, ValueError):
                    raise ProvenanceError("topic_launch_invalid") from None
                # No source row ID: repeated topic/date records are ambiguous.
                if day in seen_dates:
                    raise ProvenanceError("topic_launch_invalid")
                seen_dates.add(day)
                if period_start <= day <= period_end:
                    total += launch_total
                    correct += launch_correct
            if total == 0:
                result.append(QuestionTopicMetric.model_validate(data))
                continue
            derived_percent = round(100 * correct / total, 2)
            # 0.05 percentage points permits one-decimal source rounding only.
            # Never silently repair a conflicting canonical topic percentage.
            if abs(topic.accuracy_percent - derived_percent) > 0.05:
                raise ProvenanceError("topic_launch_percent_mismatch")
            data.update(
                total=total,
                correct=correct,
                wrong=total - correct,
                accuracy_percent=derived_percent,
                execution_status="recorded"
                if topic.execution_status != "placeholder"
                else "placeholder",
                source_period=TopicSourcePeriod(period_start=period_start, period_end=period_end),
            )
        result.append(QuestionTopicMetric.model_validate(data))
    return result


def _normalized(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)
    )


_EXECUTION = re.compile(
    r"\b(?:voce\s+(?:acertou|resolveu|estudou|praticou|treinou|dominou|domina)|"
    r"ter\s+(?:praticado|estudado|resolvido|acertado)|"
    r"sua\s+(?:pratica|execucao)|(?:dominio|maestria)\b)"
)


def validate_analysis(
    text: str,
    report_data: Mapping[str, Any],
    *,
    claims: Sequence[AnalysisClaim | Mapping[str, Any]] = (),
    verified_evidence: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Raise on unsupported claims; recorded-descriptive prose remains allowed.

    Authors cannot self-certify evidence. verified_evidence must come from a
    trusted verifier, never a draft, LLM response or decision file. This contract
    checks binding, not authenticity of external attestations. Runtime supplies
    no attestations until an independent verification integration exists.
    """
    declared = [
        c if isinstance(c, AnalysisClaim) else AnalysisClaim.model_validate(c) for c in claims
    ]
    normalized = _normalized(text)
    # Narrow, explicit caveats/questions are not assertions. Do not suppress
    # a whole message merely because it also contains a negated caveat.
    legacy = re.sub(
        r"\bnao (?:confirma|comprova|demonstra)\s+(?:dominio|maestria)\b", "", normalized
    )
    legacy = re.sub(r"\bnao da para afirmar que voce\s+(?:estudou|resolveu|praticou)\b", "", legacy)
    legacy = re.sub(r"\bcomo (?:esta|vai) sua (?:pratica|execucao)\s*\?", "", legacy)
    for match in _EXECUTION.finditer(legacy):
        assertion = match[0]
        kind: Literal["mastery", "study", "practice", "execution"] = (
            "mastery"
            if re.search(r"domina|dominou|dominio|maestria", assertion)
            else (
                "study"
                if re.search(r"estudou|estudado", assertion)
                else ("practice" if re.search(r"pratic|treinou", assertion) else "execution")
            )
        )
        declared.append(AnalysisClaim(kind=kind))
    identity = report_data.get("identity", {})
    questions = report_data.get("questions") or {}
    topics = questions.get("topics", [])
    # Conservative policy: >1 topic observations is a minimum for a descriptive
    # positive highlight, not proof of mastery or a statistically reliable sample.
    for topic in topics:
        if _normalized(str(topic.get("topic", ""))) in normalized and re.search(
            r"ponto forte|destaque|excelente|bom desempenho|otimo|mandou bem|"
            r"resultado positivo|acertos registrados em",
            normalized,
        ):
            declared.append(
                AnalysisClaim(
                    kind="topic_positive",
                    scope="topic",
                    discipline=topic["discipline"],
                    topic=topic["topic"],
                )
            )
    # Only infer a legacy percentage scope in a simple single-scope sentence.
    # Ambiguous multi-scope prose must use explicit claims; this is not NLP.
    for sentence in re.split(r"[;!?]|\.(?!\d)", normalized):
        values = re.findall(r"(\d+(?:[.,]\d+)?)\s*%", sentence)
        scoped = [("topic", t) for t in topics if _normalized(t["topic"]) in sentence]
        if not scoped:
            disciplines = questions.get("disciplines", [])
            scoped = [("discipline", d) for d in disciplines if _normalized(d["name"]) in sentence]
            if not scoped:
                scoped = [
                    ("discipline", d)
                    for d in disciplines
                    if re.search(
                        r"(?<!\w)"
                        + re.escape(re.split(r"\(| - ", _normalized(d["name"]))[0].strip())
                        + r"(?!\w)",
                        sentence,
                    )
                ]
                if (
                    len(scoped) > 1
                    and values
                    and not any(
                        c.kind == "percentage" and c.scope == "discipline" for c in declared
                    )
                ):
                    raise ProvenanceError("percentage_scope_ambiguous")
        if not scoped and len(values) == 1 and re.search(r"\bgeral\b", sentence):
            declared.append(
                AnalysisClaim(kind="percentage", value=float(values[0].replace(",", ".")))
            )
        if len(scoped) == 1 and len(values) == 1:
            scope, metric = scoped[0]
            declared.append(
                AnalysisClaim(
                    kind="percentage",
                    scope="topic" if scope == "topic" else "discipline",
                    discipline=metric.get("discipline", metric.get("name")),
                    topic=metric.get("topic"),
                    value=float(values[0].replace(",", ".")),
                )
            )
    for claim in declared:
        if claim.kind == "percentage":
            candidates = (
                [questions]
                if claim.scope == "overall"
                else (
                    [
                        d
                        for d in questions.get("disciplines", [])
                        if d.get("name") == claim.discipline
                    ]
                    if claim.scope == "discipline"
                    else [
                        t
                        for t in topics
                        if t.get("discipline") == claim.discipline and t.get("topic") == claim.topic
                    ]
                )
            )
            if (
                len(candidates) != 1
                or claim.value is None
                or not math.isfinite(claim.value)
                or candidates[0].get("accuracy_percent") is None
                or not math.isfinite(float(candidates[0]["accuracy_percent"]))
                or candidates[0].get("execution_status") in {"placeholder", "unknown"}
                or abs(float(candidates[0]["accuracy_percent"]) - claim.value) > 0.01
            ):
                raise ProvenanceError("percentage_scope_mismatch")
        if claim.kind in {"topic_positive", "topic_attention"}:
            matched = [
                t
                for t in topics
                if t.get("discipline") == claim.discipline and t.get("topic") == claim.topic
            ]
            if claim.scope != "topic" or len(matched) != 1:
                raise ProvenanceError("topic_highlight_insufficient_evidence")
            try:
                topic_metric = QuestionTopicMetric.model_validate(matched[0])
            except ValidationError:
                raise ProvenanceError("topic_highlight_insufficient_evidence") from None
            period = topic_metric.source_period
            if (
                topic_metric.total is None
                or topic_metric.total <= 1
                or topic_metric.execution_status not in {"recorded", "confirmed"}
                or period is None
                or str(period.period_start) != str(identity.get("period_start"))
                or str(period.period_end) != str(identity.get("period_end"))
            ):
                raise ProvenanceError("topic_highlight_insufficient_evidence")
        if claim.kind in {"execution", "practice", "study", "mastery"} and not any(
            e.get("execution_status") == "confirmed"
            and e.get("kind") == claim.kind
            and e.get("scope") == claim.scope
            and e.get("discipline") == claim.discipline
            and e.get("topic") == claim.topic
            and e.get("source_reference")
            and e.get("verified_by")
            and identity.get("report_id") is not None
            and e.get("report_id") == identity["report_id"]
            and identity.get("student_name")
            and e.get("student_name") == identity["student_name"]
            and ("student_id" not in identity or e.get("student_id") == identity["student_id"])
            and identity.get("period_start") is not None
            and identity.get("period_end") is not None
            and str(e.get("period_start")) == str(identity["period_start"])
            and str(e.get("period_end")) == str(identity["period_end"])
            for e in verified_evidence
        ):
            raise ProvenanceError("execution_evidence_required")
