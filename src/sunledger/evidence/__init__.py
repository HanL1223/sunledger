"""AI evidence layer: facts from the warehouse, narrative from a pluggable narrator."""

from sunledger.evidence.llm import Narrator, narrator
from sunledger.evidence.packs import EvidencePack, build_pack, to_html, to_html_document

__all__ = ["EvidencePack", "Narrator", "build_pack", "narrator", "to_html", "to_html_document"]
