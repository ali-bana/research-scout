from research_radar.config import Settings
from research_radar.ingest.openalex import OpenAlexConnector
from research_radar.ingest.semantic_scholar import SemanticScholarConnector


def test_semantic_scholar_not_configured() -> None:
    connector = SemanticScholarConnector(Settings(semantic_scholar_api_key=""))
    result = connector.get_paper_metadata("arXiv:1234.5678")
    assert result.status == "not_configured"


def test_openalex_not_configured() -> None:
    connector = OpenAlexConnector(
        Settings(openalex_email="", openalex_api_key="", openalex_token="")
    )
    result = connector.get_recommendations(["W123"])
    assert result.status == "not_configured"
