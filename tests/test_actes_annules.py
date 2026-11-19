from extract import actes_annules


def decision(texte, solution="Satisfaction totale", type_decision="Décision", recours=None):
    recours = recours or "Excès de pouvoir"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document><Donnees_Techniques><Identification>DCE_1_20250128.xml</Identification>
</Donnees_Techniques><Dossier><Code_Juridiction>CE</Code_Juridiction>
<Numero_Dossier>465835</Numero_Dossier><Date_Lecture>2025-01-28</Date_Lecture>
<Numero_ECLI>ECLI:FR:CECHR:2025:465835.20250128</Numero_ECLI>
<Type_Decision>{type_decision}</Type_Decision><Type_Recours>{recours}</Type_Recours>
<Solution>{solution}</Solution></Dossier>
<Audience><Formation_Jugement>3ème - 8ème chambres réunies</Formation_Jugement></Audience>
<Decision><Texte_Integral><p>Vu la procédure suivante :</p>
<p>Par une requête, l'association X demande au Conseil d'Etat : {texte}</p>
</Texte_Integral></Decision></Document>""".encode()


def test_decret_annule():
    m = actes_annules.scan_xml(decision("1°) d'annuler pour excès de pouvoir le décret n° 1 ;"))
    assert m["nature"] == "décret"
    assert m["solution"] == "Satisfaction totale"
    assert m["conclusions"] == "annuler pour excès de pouvoir le décret n° 1"


def test_arrete_et_circulaire_d_un_ministre_seulement():
    arrete = "d'annuler pour excès de pouvoir l'arrêté du 3 août 2023 du ministre de l'intérieur ;"
    assert actes_annules.scan_xml(decision(arrete, "Rejet"))["nature"] == "arrêté ministériel"
    cnam = "d'annuler pour excès de pouvoir la circulaire du 11 juillet 2024 de la CNAM ;"
    assert actes_annules.scan_xml(decision(cnam)) is None
    prefet = "d'annuler pour excès de pouvoir l'arrêté du 2 mai 2023 du préfet de police ;"
    assert actes_annules.scan_xml(decision(prefet)) is None


def test_decisions_ecartees():
    texte = "d'annuler pour excès de pouvoir le décret n° 1 ;"
    assert actes_annules.scan_xml(decision(texte, solution="Non-lieu")) is None
    assert actes_annules.scan_xml(decision(texte, type_decision="Ordonnance")) is None
    assert actes_annules.scan_xml(decision(texte, recours="Plein contentieux")) is None
