from scoring.indice import HISTORIQUE_MIN_MOIS, composer, dans_indice, indice, position


def dim(id_, actuel, valeurs, **kw):
    return {"id": id_, "actuel": actuel, "mensuel": [{"v": v} for v in valeurs], **kw}


def test_position_ex_aequo():
    valeurs = [0, 0, 0, 1]
    assert position(valeurs, 0) == 0.375
    assert position(valeurs, 0, "bas") == 0.0
    assert position(valeurs, 0, "haut") == 0.75
    assert position(valeurs, 2) == 1.0


def test_composer_series_courtes_et_contre_pouvoir():
    long_ = [0.0] * HISTORIQUE_MIN_MOIS
    dims = [
        dim("D2.contournement_parlement", 0, long_),
        dim("D5.temps_parole_executif", 0, [0.0] * (HISTORIQUE_MIN_MOIS - 1)),
        dim("D3.lois_censurees", 0, long_),
        dim("D7.libertes_en_pratique", 0, [0.0], hors_indice="reprise en cours"),
        dim("D5.journalistes_inquietes", 0, long_, fin_couverture="2025-12-31"),
    ]
    composer(dims)
    assert [dans_indice(d) for d in dims] == [True, False, False, False, False]
    assert "4,9 ans" in dims[1]["hors_indice"]
    assert dims[2]["contre_pouvoir"] and "contre-pouvoir" in dims[2]["hors_indice"]
    assert dims[3]["hors_indice"] == "reprise en cours"  # raison existante conservée
    assert not dims[4].get("hors_indice")


def test_indice_ecart_et_fourchette():
    dims = [
        dim("D1.a", 0, [0, 0, 0, 1]),  # 37,5 (bas 0, haut 75)
        dim("D1.b", 5, [0, 1, 2, 5]),  # 87,5 (bas 75, haut 100)
        dim("D2.c", 1, [0, 1, 2, 3]),  # 37,5 (bas 25, haut 50)
    ]
    r = indice(dims)
    assert r["valeur"] == 54.2 and r["ecart"] == 4 and r["nb_indicateurs"] == 3
    v = {x["id"]: x["valeur"] for x in r["variantes"]}
    assert v["mediane"] == 37.5
    assert v["par_dimension"] == 50.0  # D1 : 62,5 ; D2 : 37,5
    assert v["ex_aequo_bas"] == 33.3 and v["ex_aequo_haut"] == 75.0
    assert (r["ecart_min"], r["ecart_max"]) == (-17, 25)
