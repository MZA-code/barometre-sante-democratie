"""Archives JORF -> calendrier des scrutins et textes électoraux (indicateurs D1.1 et D1.2).

Lecture dédiée des archives JORF (cache `dila_scrutins_1`), qui relève deux sortes d'objets :

1. **Convocations** : articles (fichiers JORFARTI) des décrets dont le titre porte
   « convocation des électeurs » ou « convoquant les électeurs », et résumés (champ SM) des
   mêmes décrets. La date du premier tour est la première date citée par la phrase de
   convocation (« Les électeurs sont convoqués le dimanche 9 juin 2024 »), celle du second
   tour la date qui suit « second tour ». Type de scrutin lu dans le titre du décret.
2. **Textes électoraux** : lois, lois organiques, ordonnances et décrets dont le titre touche
   au mode de scrutin, au découpage des circonscriptions ou au calendrier électoral (report,
   prorogation de mandats). Le classement en catégories est fait à l'extraction, pas à la
   lecture : le cache garde tout texte dont le titre mentionne une élection.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import tarfile
from pathlib import Path

import yaml
from defusedxml import ElementTree as ET

from extract.common import FactDraft, latest_documents

SOURCE_ID = "dila_jorf"
SCAN_VERSION = "dila_scrutins_5"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / "data" / "cache"
RATTACHEMENTS_PATH = ROOT / "config" / "scrutins_reportes.yaml"

# « convocation des électeurs », « des collèges électoraux » (législatives anciennes), et décret
# « décidant de soumettre un projet de loi au référendum », qui convoque le corps électoral.
CONVOCATION = re.compile(
    r"convo(?:cation|quant)\s+(?:des|les)\s+(?:électeurs|collèges\s+électoraux)"
    r"|soumettre\s.{0,120}?\bau\s+référendum",
    re.IGNORECASE,
)
# Filtre large de lecture : un titre de report peut ne contenir ni « élection » ni « mandat »
# (« portant report du renouvellement général des conseils départementaux, des conseils
# régionaux… », loi n° 2021-191 ; « du congrès et des assemblées de province »).
ELECTORAL = re.compile(
    r"élect|scrutin|circonscription|mandat|référendum|consultation\s+des\s+électeurs"
    r"|renouvellement|conseils?\s+(?:municipaux|généraux|départementaux|régionaux)"
    r"|congrès|assemblées?\s+de\s+province|calendrier|concomitance",
    re.IGNORECASE,
)
NATURES = ("LOI", "LOI_ORGANIQUE", "ORDONNANCE", "DECRET")


def text_of(node) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


# D1.2 : report de scrutin inscrit dans le corps d'une loi ou d'une ordonnance au titre
# général (loi n° 2020-290 d'urgence pour faire face à l'épidémie de covid-19, qui reporte le
# second tour des municipales). Phrase d'article retenue si elle reporte un tour, une élection
# ou un renouvellement général (REPORT_ELECTION), ou proroge le mandat d'élus
# (PROROGATION_MANDAT), et que le passage cité vise une élection politique (POLITIQUE).
REPORT_ELECTION = re.compile(
    r"\b(?:tour|renouvellement\s+général|élections?)\b[^.;]{0,300}?\b(?:est|sont)\s+reporté",
    re.IGNORECASE,
)
PROROGATION_MANDAT = re.compile(
    r"\bmandats?\s+(?:en\s+cours\s+)?(?:des?|du)\s+(?:conseillers?|membres|sénateurs|députés)"
    r"[^.;]{0,160}?\b(?:est|sont)\s+prorogés?",
    re.IGNORECASE,
)
# Mandats prorogés qui ne sont pas des mandats électifs politiques (représentants d'élus dans
# des comités, ordres professionnels) et reports de dates budgétaires.
REPORT_EXCLU = re.compile(
    r"interrégionaux|ordre|Conseil\s+national|représentants\s+des\s+élus|organismes|comité"
    r"|notification",
    re.IGNORECASE,
)


def passages_report(body: str) -> list[str]:
    """Passages d'un article qui reportent un scrutin politique ou prorogent des mandats élus."""
    found = []
    for rx in (REPORT_ELECTION, PROROGATION_MANDAT):
        for m in rx.finditer(body):
            passage = m.group(0)
            if POLITIQUE.search(passage) and not REPORT_EXCLU.search(passage):
                found.append(passage)
    return found


def parse_report_article(root) -> dict | None:
    """Article d'une loi ou ordonnance contenant un report de scrutin (D1.2)."""
    texte = root.find("CONTEXTE/TEXTE")
    if texte is None or texte.get("nature") not in NATURES_REGLES:
        return None
    passages = passages_report(text_of(root.find("BLOC_TEXTUEL")))
    if not passages:
        return None
    return {
        "kind": "report_article",
        "cid": texte.get("cid"),
        "num": texte.get("num") or None,
        "nature": texte.get("nature"),
        "date_publi": texte.get("date_publi"),
        "titre": text_of(texte.find("TITRE_TXT")),
        "passages": [p[:400] for p in passages],
    }


def parse_article(data: bytes) -> dict | None:
    """Article d'un décret de convocation, ou d'une loi reportant un scrutin (D1.2)."""
    if b"report" in data or b"prorog" in data:
        root = ET.fromstring(data)
        record = parse_report_article(root)
        if record is not None:
            return record
    if b"onvoqu" not in data and b"f\xc3\xa9rendum" not in data:
        return None
    root = ET.fromstring(data)
    texte = root.find("CONTEXTE/TEXTE")
    if texte is None or texte.get("nature") != "DECRET":
        return None
    titre = text_of(texte.find("TITRE_TXT"))
    if not CONVOCATION.search(titre):
        return None
    body = text_of(root.find("BLOC_TEXTUEL"))
    if "convoqu" not in body and "référendum" not in body:
        return None
    return {
        "kind": "convocation",
        "cid": texte.get("cid"),
        "num": texte.get("num") or None,
        "date_publi": texte.get("date_publi"),
        "titre": titre,
        "texte": body[:1500],
    }


def parse_texte(data: bytes) -> dict | None:
    """Texte (TEXTE_VERSION) dont le titre mentionne une élection ou un scrutin."""
    if not any(f"<NATURE>{n}</NATURE>".encode() in data for n in NATURES):
        return None
    root = ET.fromstring(data)
    nature = root.findtext("META/META_COMMUN/NATURE")
    version = root.find("META/META_SPEC/META_TEXTE_VERSION")
    chronicle = root.find("META/META_SPEC/META_TEXTE_CHRONICLE")
    if nature not in NATURES or version is None or chronicle is None:
        return None
    titre = (version.findtext("TITREFULL") or version.findtext("TITRE") or "").strip()
    if not ELECTORAL.search(titre):
        return None
    record = {
        "kind": "texte",
        "cid": chronicle.findtext("CID"),
        "nature": nature,
        "num": chronicle.findtext("NUM") or None,
        "date_texte": chronicle.findtext("DATE_TEXTE"),
        "date_publi": chronicle.findtext("DATE_PUBLI"),
        "titre": titre,
    }
    if CONVOCATION.search(titre):
        record["sm"] = text_of(root.find("SM"))[:1500]
    return record


def scan_archive(path: Path) -> list[dict]:
    found = []
    with tarfile.open(path) as tar:
        for member in tar:
            name = member.name.rsplit("/", 1)[-1]
            if not (member.isfile() and name.endswith(".xml")):
                continue
            if name.startswith("JORFARTI"):
                record = parse_article(tar.extractfile(member).read())
            elif name.startswith("JORFTEXT") and "/texte/version/" in member.name:
                record = parse_texte(tar.extractfile(member).read())
            else:
                continue
            if record is not None:
                found.append(record)
    return found


def cached_scan(raw_dir: Path, doc: sqlite3.Row, cache_dir: Path) -> list[dict]:
    cache = cache_dir / f"{doc['sha256']}.{SCAN_VERSION}.jsonl"
    if cache.exists():
        return [json.loads(line) for line in cache.read_text("utf-8").splitlines()]
    found = scan_archive(raw_dir / doc["path"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in found), "utf-8")
    tmp.replace(cache)
    return found


def read_all(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, list[dict]]]:
    """Textes électoraux par identifiant, articles de convocation par décret, et articles de
    lois ou d'ordonnances reportant un scrutin (D1.2) par texte.

    Archives lues dans l'ordre (dump complet puis incréments) : la dernière version l'emporte.
    """
    docs = sorted(
        latest_documents(conn, SOURCE_ID),
        key=lambda d: (not d["external_id"].startswith("Freemium"), d["external_id"]),
    )
    textes: dict[str, dict] = {}
    articles: dict[str, list[dict]] = {}
    reports: dict[str, list[dict]] = {}
    for doc in docs:
        for record in cached_scan(raw_dir, doc, cache_dir):
            if not record.get("cid"):
                continue
            record = {**record, "raw_id": doc["id"]}
            if record["kind"] == "report_article":
                reports.setdefault(record["cid"], []).append(record)
            elif record["kind"] == "texte":
                previous = textes.get(record["cid"])
                ids = (previous["raw_ids"] if previous else set()) | {doc["id"]}
                textes[record["cid"]] = {**record, "raw_ids": ids}
            else:
                articles.setdefault(record["cid"], []).append(record)
    return textes, articles, reports


# --- Classement ---------------------------------------------------------------------------

EXTRACTOR = "jorf_scrutins/1"
INDICATOR_D11 = "D1.regles_electorales_avant_scrutin"
INDICATOR_D12 = "D1.scrutins_reportes"
NATIONAUX = ("presidentielle", "legislatives", "europeennes", "referendum")
LEGIFRANCE = "https://www.legifrance.gouv.fr/jorf/id/{cid}"
MOIS = {
    m: i
    for i, m in enumerate(
        [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ],
        1,
    )
}
DATE = re.compile(r"(\d{1,2})(?:er)?\s+(" + "|".join(MOIS) + r")\s+(\d{4})", re.IGNORECASE)
TYPES = (  # ordre : du plus précis au plus général
    ("presidentielle", r"Président\s+de\s+la\s+République|élection\s+présidentielle"),
    ("europeennes", r"Parlement\s+européen"),
    ("referendum", r"référendum|projet\s+de\s+loi\s+soumis"),
    ("senatoriales", r"sénateurs|sénatoriales"),
    ("legislatives", r"députés|Assemblée\s+nationale|élections?\s+législatives"),
    ("regionales", r"régionaux|régionales|assemblée\s+de\s+(?:Corse|Guyane|Martinique)"),
    ("departementales", r"départementaux|départementales|cantonales|conseillers\s+généraux"),
    ("municipales", r"municipaux|municipales|conseillers\s+communautaires"),
    ("consultation", r"consultation"),
)
# Élection partielle : « élection de députés », « de deux députés », « du député de la 6e
# circonscription » ; une élection générale dit « élection des députés ». Décrets annulant
# une convocation : écartés.
PARTIELLE = re.compile(
    r"partielles?|d['’]un\s+(?:député|sénateur)|élection\s+(?:de|du)\s+(?:\w+\s+)?députés?\b"
    r"|annulant\s+la\s+convocation",
    re.IGNORECASE,
)
CATEGORIES = {
    "calendrier": re.compile(
        r"\breport\w*|prorog\w*|durée\s+du\s+mandat|date\s+(?:du|des)\s+(?:scrutin|élection|renouvellement)"
        r"|calendrier\s+électoral|concomitance",
        re.IGNORECASE,
    ),
    "decoupage": re.compile(
        r"délimitation\s+des\s+circonscriptions|circonscriptions\s+(?:législatives|électorales)"
        r"|découpage|répartition\s+des\s+sièges|nombre\s+des?\s+(?:députés|sénateurs)",
        re.IGNORECASE,
    ),
    "mode_scrutin": re.compile(
        r"mode\s+de\s+scrutin|mode\s+d['’]élection|relati(?:f|fs|ve|ves)\s+à\s+l['’]élection\s+d"
        r"|modalités\s+(?:de\s+l['’]élection|du\s+scrutin)"
        r"|règles\s+applicables\s+à\s+l['’]élection",
        re.IGNORECASE,
    ),
}
EXCLU = re.compile(
    r"convo(?:cation|quant)\s+(?:des|les)\s+électeurs|rectificatif|portant\s+publication"
    r"|dépenses|remboursement|plafond",
    re.IGNORECASE,
)
# Élections politiques (suffrage universel ou assemblées élues) : seules visées par D1.2. Les
# « prorogations du mandat » de conseils d'administration, d'ordres professionnels ou de
# commissions consultatives, très nombreuses au JORF, ne sont pas des reports de scrutin.
POLITIQUE = re.compile(
    r"conseill(?:ers?|ère)s?\s+(?:municipaux|communautaires|généraux|départementaux|régionaux"
    r"|territoriaux|consulaires|des\s+Français\s+de\s+l['’]étranger|à\s+l['’]Assemblée)"
    r"|conseils?\s+(?:municipaux|généraux|départementaux|régionaux)|sénateurs|députés"
    r"|Président\s+de\s+la\s+République|Parlement\s+européen|Assemblée\s+des\s+Français"
    r"|assemblées?\s+(?:de\s+(?:Corse|Guyane|Martinique|la\s+Polynésie)|de\s+province"
    r"|territoriale)|congrès|provinces?\s+de\s+la\s+Nouvelle-Calédonie"
    r"|élections?\s+(?:municipales|cantonales|régionales|législatives|sénatoriales|européennes"
    r"|présidentielle|provinciales)|renouvellement\s+(?:général|triennal|partiel|de\s+la\s+série)"
    r"|calendrier\s+électoral",
    re.IGNORECASE,
)
# Décret d'application : son titre recopie celui de la loi appliquée (« portant application de
# la loi n° 2013-403 […] modifiant le calendrier électoral ») sans rien reporter lui-même.
APPLICATION = re.compile(r"(?:portant|pris\s+pour\s+l['’])\s*application\s+d", re.IGNORECASE)
# D1.1 : le « régime électoral des assemblées » relève de la loi (article 34 de la Constitution).
# Seuls les lois, lois organiques et ordonnances sont retenus ; les décrets d'organisation pris
# avant chaque scrutin (commission de propagande, décrets d'application) ne le sont pas.
NATURES_REGLES = ("LOI", "LOI_ORGANIQUE", "ORDONNANCE")
REPORT = re.compile(
    r"\breport\w*|(?:prorog|prolong)\w*\s+(?:du|des|(?:de\s+)?la\s+durée\s+d[ue]s?)\s+mandats?"
    r"|modifiant\s+le\s+calendrier\s+électoral",
    re.IGNORECASE,
)


def iso(day: str, month: str, year: str) -> str:
    return f"{year}-{MOIS[month.lower()]:02d}-{int(day):02d}"


def type_scrutin(titre: str) -> str | None:
    return next((t for t, rx in TYPES if re.search(rx, titre, re.IGNORECASE)), None)


def dates_tours(texte: str) -> tuple[str | None, str | None]:
    """Dates des tours : première date après « convoqu », puis après « second tour »."""
    # « Les électeurs sont convoqués le … » ; référendum : « … sera soumis au référendum le … »
    low = texte.lower()
    i = low.find("convoqu")
    if i < 0:
        i = low.find("référendum")
    m1 = DATE.search(texte, max(i, 0)) if i >= 0 else DATE.search(texte)
    j = texte.lower().find("second tour")
    m2 = DATE.search(texte, j) if j >= 0 else None
    return (iso(*m1.groups()) if m1 else None, iso(*m2.groups()) if m2 else None)


def calendrier(textes: dict[str, dict], articles: dict[str, list[dict]]) -> list[dict]:
    """Scrutins convoqués par décret, un par (type, date du premier tour en métropole)."""
    convocs = []
    cids = set(articles) | {c for c, t in textes.items() if "sm" in t}
    for cid in sorted(cids):
        arts = articles.get(cid, [])
        titre = arts[0]["titre"] if arts else textes[cid]["titre"]
        source = " ".join(a["texte"] for a in arts) or textes.get(cid, {}).get("sm", "")
        t1, t2 = dates_tours(source)
        kind = type_scrutin(titre)
        if not t1 or not kind or PARTIELLE.search(titre):
            continue
        raw = {a["raw_id"] for a in arts} | textes.get(cid, {}).get("raw_ids", set())
        convocs.append(
            {"type": kind, "t1": t1, "t2": t2, "cid": cid, "titre": titre, "raw_ids": raw}
        )
    # Plusieurs décrets pour un même scrutin (outre-mer convoqué la veille, décret modificatif) :
    # regroupés par type et par proximité de date (8 jours), date retenue = la plus tardive.
    convocs.sort(key=lambda c: (c["type"], c["t1"]))
    scrutins: list[dict] = []
    for c in convocs:
        last = scrutins[-1] if scrutins else None
        if last and last["type"] == c["type"] and _jours(last["t1_min"], c["t1"]) <= 8:
            last["decrets"].append(c["cid"])
            last["raw_ids"] |= c["raw_ids"]
            if c["t1"] > last["t1"]:
                last.update(t1=c["t1"], t2=c["t2"] or last["t2"], titre=c["titre"], cid=c["cid"])
        else:
            scrutins.append({**c, "t1_min": c["t1"], "decrets": [c["cid"]]})
    return scrutins


def _jours(a: str, b: str) -> int:
    return abs((dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days)


def types_vises(titre: str) -> list[str]:
    """Tous les types de scrutin nommés par un titre (« élection des députés et sénateurs »)."""
    return [t for t, rx in TYPES if re.search(rx, titre, re.IGNORECASE)]


def categories(titre: str) -> list[str]:
    if EXCLU.search(titre):
        return []
    return [k for k, rx in CATEGORIES.items() if rx.search(titre)]


def load_rattachements(path: Path = RATTACHEMENTS_PATH) -> dict[str, list[str]]:
    """Texte de report -> scrutins reportés (table manuelle, variante D1.2 par scrutin)."""
    if not path.exists():
        return {}
    textes = yaml.safe_load(path.read_text(encoding="utf-8")).get("textes") or {}
    return {str(ref): list(v["scrutins"]) for ref, v in textes.items()}


def scrutins_reportes(ref: str, table: dict[str, list[str]]) -> dict:
    """Scrutins rattachés à un texte ; à défaut, le texte compte pour un scrutin à rattacher."""
    if ref in table:
        return {"scrutins_reportes": table[ref], "rattachement": "table"}
    return {"scrutins_reportes": [f"texte-{ref}"], "rattachement": "a_rattacher"}


def extract(
    conn: sqlite3.Connection, raw_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[FactDraft]:
    textes, articles, reports = read_all(conn, raw_dir, cache_dir)
    if not textes and not articles and not reports:
        return []
    scrutins = calendrier(textes, articles)
    drafts = []
    for s in scrutins:
        drafts.append(
            FactDraft(
                indicator_id="contexte.calendrier_scrutins",
                fact_type="scrutin",
                occurred_on=s["t1"],
                title=s["titre"],
                official_ref=f"{s['type']} {s['t1']}",
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted(s["raw_ids"])),
                attributes={
                    "type": s["type"],
                    "national": s["type"] in NATIONAUX,
                    "t1": s["t1"],
                    "t2": s["t2"],
                    "decrets": s["decrets"],
                    "url": LEGIFRANCE.format(cid=s["cid"]),
                },
            )
        )
    nationaux = {t: sorted(s["t1"] for s in scrutins if s["type"] == t) for t in NATIONAUX}
    rattachements = load_rattachements()
    reports_par_titre: set[str] = set()
    for cid in sorted(textes):
        t = textes[cid]
        cats = categories(t["titre"])
        if not cats or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["date_publi"] or ""):
            continue
        vises = types_vises(t["titre"])
        common = {
            "nature": t["nature"],
            "categories": cats,
            "types_scrutin": vises,
            "url": LEGIFRANCE.format(cid=cid),
        }
        if (
            "calendrier" in cats
            and REPORT.search(t["titre"])
            and POLITIQUE.search(t["titre"])
            and not APPLICATION.search(t["titre"])
        ):
            reports_par_titre.add(cid)
            drafts.append(
                FactDraft(
                    indicator_id=INDICATOR_D12,
                    fact_type="report_scrutin",
                    occurred_on=t["date_publi"],
                    title=t["titre"],
                    official_ref=t["num"] or cid,
                    extraction_method=EXTRACTOR,
                    raw_document_ids=tuple(sorted(t["raw_ids"])),
                    attributes={
                        **common,
                        **scrutins_reportes(t["num"] or cid, rattachements),
                        "detection": "titre",
                        # « modifiant le calendrier électoral » peut avancer comme reculer un
                        # scrutin : à vérifier (loi n° 2013-403 : élections de 2014 en 2015).
                        "modification_calendrier": not re.search(
                            r"report|prorog|prolong", t["titre"], re.IGNORECASE
                        ),
                    },
                )
            )
        cibles = [v for v in vises if v in NATIONAUX]
        if cibles and t["nature"] in NATURES_REGLES:
            publie = dt.date.fromisoformat(t["date_publi"])
            suivants = [d for v in cibles for d in nationaux[v] if d > t["date_publi"]]
            suivant = min(suivants) if suivants else None
            jours = (dt.date.fromisoformat(suivant) - publie).days if suivant else None
            drafts.append(
                FactDraft(
                    indicator_id=INDICATOR_D11,
                    fact_type="texte_electoral",
                    occurred_on=t["date_publi"],
                    title=t["titre"],
                    official_ref=t["num"] or cid,
                    extraction_method=EXTRACTOR,
                    raw_document_ids=tuple(sorted(t["raw_ids"])),
                    attributes={
                        **common,
                        "scrutin_suivant": suivant,
                        "jours_avant_scrutin": jours,
                        "moins_d_un_an": jours is not None and jours <= 365,
                    },
                )
            )
    drafts.extend(reports_dans_le_corps(reports, reports_par_titre, rattachements))
    return drafts


def reports_dans_le_corps(
    reports: dict[str, list[dict]], deja: set[str], rattachements: dict[str, list[str]]
) -> list[FactDraft]:
    """D1.2 : lois et ordonnances au titre général dont un article reporte un scrutin.

    Repérage automatique dans le texte des articles, à vérifier (`a_verifier`) ; les textes déjà
    retenus par leur titre ne sont pas comptés deux fois.
    """
    drafts = []
    for cid, records in sorted(reports.items()):
        latest = records[-1]
        if cid in deja or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", latest["date_publi"] or ""):
            continue
        passages = list(dict.fromkeys(p for r in records for p in r["passages"]))
        ref = latest["num"] or cid
        drafts.append(
            FactDraft(
                indicator_id=INDICATOR_D12,
                fact_type="report_scrutin",
                occurred_on=latest["date_publi"],
                title=latest["titre"],
                official_ref=ref,
                extraction_method=EXTRACTOR,
                raw_document_ids=tuple(sorted({r["raw_id"] for r in records})),
                attributes={
                    "nature": latest["nature"],
                    "detection": "corps_du_texte",
                    "passages": passages[:5],
                    "a_verifier": True,
                    "modification_calendrier": False,
                    **scrutins_reportes(ref, rattachements),
                    "url": LEGIFRANCE.format(cid=cid),
                },
            )
        )
    return drafts
