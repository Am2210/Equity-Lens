"""Typed research results shared by evidence retrieval and presentation."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Citation:
    company: str
    ticker: str
    fiscal_year: int
    period_start: str
    period_end: str
    filed: str
    accession: str
    url: str
    section: str
    metric: str = ""
    locator: str = ""
    form: str = "10-K"


@dataclass(frozen=True)
class Claim:
    kind: str
    text: str
    citations: tuple[Citation, ...]

    def __post_init__(self):
        if not self.citations:
            raise ValueError("An evidence claim requires at least one source citation.")


@dataclass
class Answer:
    question: str
    claims: list[Claim] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    context: list[str] = field(default_factory=list)
    status: str = "answered"
    mode: str = "deterministic_offline"

    def finish(self):
        if self.limitations and self.claims:
            self.status = "partial"
        elif self.limitations and self.status == "answered":
            self.status = "insufficient_evidence"
        return self

    def to_dict(self):
        return asdict(self)

    def markdown(self):
        paragraphs = []
        for claim in self.claims:
            links = []
            for source in claim.citations:
                start = f"{source.period_start}–{source.period_end}" if source.period_start else source.period_end
                subject = f"{source.metric} · " if source.metric else ""
                locator = f" · {source.locator}" if source.locator else ""
                label = (
                    f"{source.company} {subject}FY{source.fiscal_year} ({start}) · "
                    f"Form {source.form} filed {source.filed} · {source.section}{locator}"
                )
                links.append(f"[{label}]({source.url})")
            paragraphs.append(f"**{claim.kind}** — {claim.text} " + " ".join(links))
        paragraphs.extend(self.limitations)
        paragraphs.extend(self.context)
        return "\n\n".join(paragraphs)
