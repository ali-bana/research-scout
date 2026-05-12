from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from research_radar.models import Base, Paper, utcnow
from research_radar.ranking.scorer import score_and_rank


def test_scoring_creates_selection_reason() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    profile = {
        "current_projects": ["tool-using agents"],
        "high_priority_topics": ["retrieval", "reasoning"],
        "broader_watchlist": [],
        "negative_topics": ["cryptocurrency trading"],
        "seed_papers_i_like": [],
        "authors_labs_to_watch": ["Example Lab"],
    }
    with Session() as session:
        paper = Paper(
            title="Tool-Using Agents for Retrieval Reasoning",
            authors="Example Lab",
            abstract="We study retrieval and reasoning for long-horizon agents.",
            categories="cs.AI",
            published_at=utcnow(),
            url="https://example.test/paper",
        )
        session.add(paper)
        session.commit()
        scored = score_and_rank(session, [paper], profile, "long-horizon agents")
        assert scored[0].score > 0
        assert scored[0].fallback_reason.startswith("Chosen because")
        assert "keyword_topic_match" in scored[0].breakdown
