from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class ResearchSettings:
    max_searches: int = 3
    max_pages: int = 6
    max_link_depth: int = 1
    timeout: int = 240
    page_concurrency: int = 2
    page_timeout: int = 25
    cache_lifetime: int = 3600
    browser_provider: str = "auto"
    search_provider: str = "ddgs"
    search_endpoint: str = ""
    default_save_to_knowledge: bool = False
    depth: str = "Standard"

    @classmethod
    def validated(cls, value=None):
        value = {} if value is None else value
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError("Unknown Research setting")
        result = cls(**value)
        for name, bounds in {
            "max_searches": (1, 10),
            "max_pages": (1, 30),
            "max_link_depth": (0, 3),
            "timeout": (15, 900),
            "page_concurrency": (1, 4),
            "page_timeout": (5, 60),
            "cache_lifetime": (0, 604800),
        }.items():
            number = getattr(result, name)
            if type(number) is not int or not bounds[0] <= number <= bounds[1]:
                raise ValueError(f"{name} must be an integer between {bounds[0]} and {bounds[1]}")
        if not isinstance(result.browser_provider, str) or result.browser_provider not in {
            "auto",
            "http",
            "playwright",
        }:
            raise ValueError("Unknown browser provider")
        if not isinstance(result.search_provider, str) or result.search_provider not in {"ddgs", "searxng"}:
            raise ValueError("Unknown search provider")
        if not isinstance(result.depth, str) or result.depth not in {"Quick", "Standard", "Deep"}:
            raise ValueError("Unknown Research depth")
        if type(result.default_save_to_knowledge) is not bool:
            raise ValueError("Save preference must be boolean")
        if not isinstance(result.search_endpoint, str):
            raise ValueError("Search endpoint must be text")
        return result

    def to_dict(self):
        return asdict(self)

    def limits(self):
        searches, pages = {"Quick": (1, 3), "Standard": (3, 8), "Deep": (10, 30)}[self.depth]
        return min(searches, self.max_searches), min(pages, self.max_pages)
