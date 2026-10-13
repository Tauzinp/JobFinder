from dataclasses import dataclass, field


@dataclass
class SearchProfile:
    name: str
    title_keywords: list[str] = field(default_factory=list)
    description_keywords: list[str] = field(default_factory=list)
    job_types: list[str] = field(default_factory=list)
    sites: list[str] = field(default_factory=list)
