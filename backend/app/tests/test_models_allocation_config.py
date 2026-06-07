"""Unit tests for allocation_config_id columns + relationships (shared quota pools, Phase 1).

Pure model-mapper assertions — no DB session needed. Verifies the new FK
columns exist with the contract shape and the CollegeRankingItem.allocation_config
relationship is wired.
"""

from sqlalchemy import inspect as sa_inspect

from app.models.application import Application
from app.models.college_review import CollegeRankingItem
from app.models.payment_roster import PaymentRoster, PaymentRosterItem
from app.models.scholarship import ScholarshipConfiguration


def _column(model, name):
    return sa_inspect(model).columns.get(name)


def test_college_ranking_item_has_allocation_config_id_fk():
    col = _column(CollegeRankingItem, "allocation_config_id")
    assert col is not None, "CollegeRankingItem.allocation_config_id column missing"
    assert col.nullable is True
    fk = next(iter(col.foreign_keys))
    assert fk.column.table.name == "scholarship_configurations"


def test_college_ranking_item_allocation_config_relationship():
    rels = sa_inspect(CollegeRankingItem).relationships
    assert "allocation_config" in rels, "allocation_config relationship missing"
    assert rels["allocation_config"].mapper.class_ is ScholarshipConfiguration
