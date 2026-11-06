import pytest

from icml.domain.provenance import (
    ProvenanceCategory,
    legacy_provenance_map,
    resolve_legacy_labels,
)
from icml.domain.territories import (
    UrbanDomainKind,
    load_territories,
    load_urban_domains,
    territory_codes,
)


def test_33_territories_with_bogota_and_cundinamarca_separate():
    codes = territory_codes()
    assert len(codes) == 33
    assert 11 in codes and 25 in codes
    capitals = [t for t in load_territories() if t.is_capital_district]
    assert [t.dane_code for t in capitals] == [11]


def test_urban_domains_have_exactly_one_synthetic_signal():
    domains = load_urban_domains()
    assert len(domains) == 33
    synthetic = [d for d in domains if d.is_synthetic]
    assert [d.dane_code for d in synthetic] == [25]
    assert synthetic[0].kind is UrbanDomainKind.SYNTHETIC_SIGNAL


def test_urban_codes_are_territory_codes():
    assert {d.dane_code for d in load_urban_domains()} <= set(
        territory_codes()
    )


def test_provenance_map_uses_closed_categories():
    for provenance in legacy_provenance_map().values():
        assert isinstance(provenance.category, ProvenanceCategory)


def test_unknown_provenance_label_is_rejected():
    with pytest.raises(KeyError, match="NOT_A_LABEL"):
        resolve_legacy_labels(["geih_observado", "NOT_A_LABEL"])


def test_provisional_flag_is_parsed():
    resolved = resolve_legacy_labels(["PREDICCION_PROVISIONAL_2026"])
    assert resolved["PREDICCION_PROVISIONAL_2026"].is_provisional
