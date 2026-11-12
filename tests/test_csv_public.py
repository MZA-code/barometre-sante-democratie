from storage.csv_public import ligne_sure, neutraliser


def test_cellules_formules_neutralisees():
    for v in ('=HYPERLINK("x")', "+1", "-2+3", "@SUM(A1)", "\tx", "\rx"):
        assert neutraliser(v) == "'" + v
    assert neutraliser("Décret n° 2025-12") == "Décret n° 2025-12"
    assert neutraliser(-2.5) == -2.5 and neutraliser(None) is None
    assert ligne_sure({"titre": "=1+1", "date": "2025-01-01"}) == {
        "titre": "'=1+1",
        "date": "2025-01-01",
    }
