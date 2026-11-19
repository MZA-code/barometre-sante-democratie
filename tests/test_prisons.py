import io
import zipfile

from extract import prisons

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
NSR = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def classeur(feuilles: dict[str, list[list[str]]]) -> bytes:
    """Classeur xlsx minimal : cellules en texte inline, une feuille par entrée."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        sheets = "".join(
            f'<sheet name="{nom}" sheetId="{i}" r:id="rId{i}"/>'
            for i, nom in enumerate(feuilles, 1)
        )
        z.writestr("xl/workbook.xml", f"<workbook {NS} {NSR}><sheets>{sheets}</sheets></workbook>")
        rels = "".join(
            f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml" Type="x"/>'
            for i in range(1, len(feuilles) + 1)
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rels}</Relationships>",
        )
        for i, lignes in enumerate(feuilles.values(), 1):
            rows = "".join(
                "<row>"
                + "".join(f'<c t="inlineStr"><is><t>{c}</t></is></c>' for c in ligne)
                + "</row>"
                for ligne in lignes
            )
            z.writestr(
                f"xl/worksheets/sheet{i}.xml",
                f"<worksheet {NS}><sheetData>{rows}</sheetData></worksheet>",
            )
    return buf.getvalue()


def test_parse_mensuel_lit_le_tableau_6():
    data = classeur(
        {
            "Stat": [["Autre"]],
            "Tab6": [
                ["Tableau 6"],
                ["Effectifs actualisés au 1er septembre 2026"],
                ["Niveau", "Capacité norme circulaire", "Capacité opérationnelle", "Détenus"],
                ["Métropole", "59589.0", "58636.0", "82944.0"],
                ["Total France entière", "64328.0", "63348.0", "90020.0", "142,1 %"],
            ],
        }
    )
    assert prisons.parse_mensuel(data) == {
        "mois": "2026-09-01",
        "capacite": 63348,
        "detenus": 90020,
    }


def test_parse_eurostat_garde_les_pays_de_l_ue_complets():
    csv = (
        "DATAFLOW,LAST UPDATE,freq,indic_cr,unit,geo,TIME_PERIOD,OBS_VALUE,OBS_FLAG,CONF_STATUS\n"
        "E,1,A,PRIS_ACT_CAP,NR,FR,2024,80669,,\n"
        "E,1,A,PRIS_OFF_CAP,NR,FR,2024,62385,,\n"
        "E,1,A,PRIS_ACT_CAP,P_HTHAB,FR,2024,117.47,,\n"
        "E,1,A,PRIS_ACT_CAP,NR,NO,2024,3359,,\n"  # hors UE
        "E,1,A,PRIS_OFF_CAP,NR,NO,2024,3631,,\n"
        "E,1,A,PRIS_ACT_CAP,NR,DE,2024,58798,,\n"  # capacité absente
    )
    assert prisons.parse_eurostat(csv.encode()) == {
        ("FR", 2024): {"detenus": 80669, "capacite": 62385}
    }
