from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from research_radar.config import Settings
from research_radar.digest.daily import generate_daily_digest
from research_radar.models import Base, DigestItem, Paper, utcnow


def test_daily_digest_stores_selection_reason(tmp_path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        """
current_projects:
  - tool-using agents
high_priority_topics:
  - retrieval
broader_watchlist: []
negative_topics: []
seed_papers_i_like: []
authors_labs_to_watch: []
""".strip(),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    settings = Settings(
        database_url="sqlite:///:memory:",
        profile_path=str(profile_path),
        llm_provider="mock",
        daily_max_papers=10,
    )
    with Session() as session:
        session.add(
            Paper(
                title="Retrieval for Tool-Using Agents",
                authors="Researcher",
                abstract="A paper about retrieval for tool-using agents.",
                categories="cs.AI",
                published_at=utcnow(),
                url="https://example.test/retrieval-agents",
            )
        )
        session.commit()
        digest = generate_daily_digest(session, settings)
        item = session.scalar(select(DigestItem).where(DigestItem.digest_id == digest.id))
        assert digest.item_count == 1
        assert item is not None
        assert item.selection_reason.startswith("Chosen because")
        assert item.short_explanation
