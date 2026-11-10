"""Instantanés des issues GitHub et fiches du Défenseur des droits -> faits D7.

Deux voies (spec docs/superpowers/specs/2026-11-10-libertes-en-pratique-design.md) :

1. `fait_presse_valide` : une issue `d7` (instantané archivé par collectors/github_d7.py) porte
   l'étiquette `validé`, posée par un compte de config/validateurs_d7.yaml, et exactement une
   étiquette `cat:<clé>` connue de la grille. Le fait est daté du jour indiqué en fin de titre
   (`[D7] <catégorie> · <lieu> · <AAAA-MM-JJ>`, issues ouvertes par ops/issues_d7.py) ou, pour
   un signalement manuel, des lignes `Date :` et `Lieu :` du corps. Statuts possibles d'une
   issue : `en_attente`, `valide`, `rejete`, `doublon` (le fait est compté dans une autre
   issue), `a_corriger` (étiquette posée par un compte non validateur, étiquettes
   contradictoires, catégorie absente, multiple ou inconnue, date illisible) : seul `valide`
   compte. Aucun nom de personne n'est repris : catégorie, lieu, numéro d'issue, validateur.

2. `constat_institutionnel` : fiche du Défenseur des droits de type « Décisions » dont le
   résumé constate un manquement (une phrase qui contient « manquement » sans négation : « ne
   retient pas de manquement », « pas de manquement », « aucun manquement », « absence de
   manquement » ne comptent pas). Datée du jour de la fiche (fin d'année si l'année seule est
   connue). Catégorie `force` si un mot-clé parle de force ou de violence, sinon `reunion`
   (la base suivie ne couvre que les manifestations et le maintien de l'ordre). La date de
   l'acte n'est pas lisible de façon fiable : `date_acte` vaut null.
   Constaté sur l'archive du 2026-11-10 : 91 décisions, 30 résumés citent un manquement, dont
   une partie en négation (anciens avis de la CNDS, 2007-2010, hors période D7).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

import yaml

from collectors.ddd import BASE as DDD_BASE
from collectors.ddd import SOURCE_ID as DDD
from collectors.github_d7 import SOURCE_ID as GITHUB
from extract.common import FactDraft, latest_documents
from extract.d7_candidats import INDICATOR, categories_d7
from extract.ddd import ANNEE, DATE, lire_fiche

ROOT = Path(__file__).resolve().parent.parent
VALIDATEURS_PATH = ROOT / "config" / "validateurs_d7.yaml"
EXTRACTOR = "d7/1"
DECISIONS = ("validé", "rejeté", "doublon")
STATUTS = {"validé": "valide", "rejeté": "rejete", "doublon": "doublon"}
MARQUEUR = re.compile(
    r"<!--\s*d7:gdelt:([\w-]+)\s*-->|(?:Identifiant D7|Événement GDELT)\s*:\s*([\w-]+)"
)
TITRE = re.compile(r"^\[D7\]\s.*?\s·\s(.+)\s·\s(\d{4}-\d{2}-\d{2})\s*$")
LIGNE_DATE = re.compile(r"^\s*Date\s*:\s*(\d{4}-\d{2}-\d{2})\s*$", re.M)
LIGNE_LIEU = re.compile(r"^\s*Lieu\s*:\s*(.+?)\s*$", re.M)
# Négations courantes, y compris à distance (« n'a pas relevé de manquement », « n'est pas en
# mesure de relever un manquement », « ne peut retenir de manquement », « un quelconque
# manquement »). Règle prudente : un doute écarte le constat (il n'est relu par personne).
NEGATION = re.compile(
    r"\b(?:ne|n['’])\s*[^.]{0,60}?\b(?:pas|aucun|aucune|nullement|jamais|peut|pu)\b[^.]{0,60}?manquement"
    r"|\b(?:aucun|absence\s+de|sans|quelconque)\b[^.]{0,30}?manquement",
    re.I,
)
REPRISE_MARGE_JOURS = 30


def _config_validateurs(path: Path = VALIDATEURS_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validateurs(path: Path = VALIDATEURS_PATH) -> set[str]:
    return set(_config_validateurs(path)["validateurs"])


def comptes_serveur(path: Path = VALIDATEURS_PATH) -> set[str]:
    """Comptes qui peuvent poser l'étiquette `cat:` d'origine (le serveur qui ouvre l'issue)."""
    return set(_config_validateurs(path).get("comptes_serveur") or [])


def decision(
    inst: dict, comptes: set[str], categories: dict | None = None, serveur: set[str] = frozenset()
):
    """(statut, catégorie, motif) d'une issue ; motif renseigné si `a_corriger`."""
    categories = categories if categories is not None else categories_d7()
    etiquettes = inst["etiquettes"]
    cats = [e[4:] for e in etiquettes if e.startswith("cat:")]
    cat = cats[0] if len(cats) == 1 and cats[0] in categories else None
    poses = [d for d in DECISIONS if d in etiquettes]
    if not poses:
        return "en_attente", cat, None
    if len(poses) > 1:
        return "a_corriger", cat, "étiquettes contradictoires"
    if inst["poses"].get(poses[0], {}).get("par") not in comptes:
        return "a_corriger", cat, "étiquette posée par un compte non validateur"
    if poses[0] == "validé" and cat is None:
        return "a_corriger", None, "aucune ou plusieurs étiquettes cat:"
    poseur_cat = inst["poses"].get(f"cat:{cat}", {}).get("par")
    if poses[0] == "validé" and poseur_cat is not None and poseur_cat not in comptes | serveur:
        return "a_corriger", cat, "étiquette cat: posée par un compte non autorisé"
    return STATUTS[poses[0]], cat, None


def evenement_de(corps: str) -> str | None:
    m = MARQUEUR.search(corps or "")
    return (m.group(1) or m.group(2)) if m else None


def lire_titre(titre: str) -> tuple[str, str] | None:
    m = TITRE.match(titre.strip())
    return (m.group(1).strip(), m.group(2)) if m else None


def lire_corps_manuel(corps: str) -> tuple[str, str] | None:
    d, lieu = LIGNE_DATE.search(corps or ""), LIGNE_LIEU.search(corps or "")
    return (lieu.group(1) if lieu else "", d.group(1)) if d else None


def lieu_et_date(inst: dict) -> tuple[str, str] | None:
    lu = lire_titre(inst["titre"]) or lire_corps_manuel(inst["corps"])
    if lu is None:
        return None
    try:
        dt.date.fromisoformat(lu[1])
    except ValueError:
        return None
    return lu


MODIFIEE = "issue modifiée après la validation : revalider"


def issues_figees(conn: sqlite3.Connection, raw_dir: Path) -> list[tuple[int, dict]]:
    """(document brut, dernier instantané) de chaque issue, par numéro. Une issue validée est
    marquée `_modifiee` si son titre ou son corps diffère de ce que le validateur a vu : le
    dernier instantané pris AVANT la pose de `validé` (à défaut, le premier qui la porte).
    Sur un dépôt public, l'auteur d'une issue peut la modifier après coup ; il faut alors
    revalider (retirer puis reposer `validé`). Limite : une issue ouverte, validée et
    modifiée dans la même heure, sans instantané intermédiaire, n'est pas détectée."""
    versions: dict[str, list[tuple[int, str, dict]]] = {}
    for row in conn.execute(
        "SELECT id, external_id, fetched_at, path FROM raw_documents WHERE source_id = ?"
        " ORDER BY fetched_at, id",
        (GITHUB,),
    ):
        inst = json.loads((raw_dir / row["path"]).read_text(encoding="utf-8"))
        versions.setdefault(row["external_id"], []).append((row["id"], row["fetched_at"], inst))
    out = []
    for vs in versions.values():
        doc_id, _, dernier = vs[-1]
        pose = dernier["poses"].get("validé")
        if "validé" in dernier["etiquettes"] and pose:
            avant = [i for _, quand, i in vs if quand < pose["le"]]
            ref = (
                avant[-1]
                if avant
                else next(i for _, _, i in vs if i["poses"].get("validé") == pose)
            )
            if (ref["titre"], ref["corps"]) != (dernier["titre"], dernier["corps"]):
                dernier = {**dernier, "_modifiee": True}
        out.append((doc_id, dernier))
    return sorted(out, key=lambda di: di[1]["numero"])


def statut_complet(inst: dict, comptes: set[str], categories: dict, serveur=frozenset()):
    """Comme `decision`, plus la date illisible d'une issue validée et l'issue modifiée après
    sa validation (`a_corriger`)."""
    statut, cat, motif = decision(inst, comptes, categories, serveur)
    if statut == "valide" and inst.get("_modifiee"):
        return "a_corriger", cat, MODIFIEE
    if statut == "valide" and lieu_et_date(inst) is None:
        return "a_corriger", cat, "date illisible (titre ou ligne « Date : AAAA-MM-JJ »)"
    return statut, cat, motif


def constate_manquement(resume: str) -> bool:
    for phrase in re.split(r"(?<=[.;])\s+", resume or ""):
        if "manquement" in phrase.lower():
            reste = NEGATION.sub("", phrase)
            if "manquement" in reste.lower():
                return True
    return False


def faits_presse(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    comptes, categories, serveur = validateurs(), categories_d7(), comptes_serveur()
    out = []
    for doc_id, inst in issues_figees(conn, raw_dir):
        statut, cat, _ = statut_complet(inst, comptes, categories, serveur)
        if statut != "valide":
            continue
        lieu, jour = lieu_et_date(inst)
        pose = inst["poses"]["validé"]
        out.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="fait_presse_valide",
                occurred_on=jour,
                title=f"{categories[cat]['libelle']} · {lieu}",
                official_ref=f"github#{inst['numero']}",
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc_id,),
                attributes={
                    "categorie": cat,
                    "lieu": lieu,
                    "issue": inst["numero"],
                    "valide_par": pose["par"],
                    "valide_le": pose["le"],
                },
            )
        )
    return out


def constats(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    out = []
    for doc in latest_documents(conn, DDD):
        f = lire_fiche((raw_dir / doc["path"]).read_text(encoding="utf-8", errors="replace"))
        if f["type"] != "Décisions" or not constate_manquement(f["resume"] or ""):
            continue
        m, a = DATE.match(f["date"]), ANNEE.match(f["date"])
        if m:
            jour, precision = f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "jour"
        elif a:
            jour, precision = f"{a.group(1)}-12-31", "année"
        else:
            continue  # date illisible : extract/ddd.py signale déjà l'anomalie
        force = any(re.search(r"force|violence", k, re.I) for k in f["mots_cles"])
        out.append(
            FactDraft(
                indicator_id=INDICATOR,
                fact_type="constat_institutionnel",
                occurred_on=jour,
                title=f["titre"],
                official_ref=f"{DDD_BASE}index.php?lvl=notice_display&id={doc['external_id']}",
                extraction_method=EXTRACTOR,
                raw_document_ids=(doc["id"],),
                attributes={
                    "categorie": "force" if force else "reunion",
                    "date_acte": None,
                    "numero": f["numero"],
                    "precision_date": precision,
                },
            )
        )
    return out


def extract(conn: sqlite3.Connection, raw_dir: Path) -> list[FactDraft]:
    return faits_presse(conn, raw_dir) + constats(conn, raw_dir)


def etat_reprise(
    candidats: list[tuple[str, str]],
    statuts: dict[str, str],
    aujourd_hui: dt.date,
    couverture_debut: dt.date | None = None,
) -> dict:
    """La reprise couvre les candidats de plus de 30 jours (les récents suivent le flux
    normal). `reprise_relue_jusqu_au` : en remontant le temps, jour le plus ancien jusqu'où
    tous les candidats ont une décision."""
    limite = str(aujourd_hui - dt.timedelta(days=REPRISE_MARGE_JOURS))
    anciens = sorted((c for c in candidats if c[1] < limite), key=lambda c: c[1], reverse=True)
    decide = {"valide", "rejete", "doublon"}
    relue, sans = None, 0
    for evt, jour in anciens:
        if statuts.get(evt) in decide:
            if sans == 0:
                relue = jour
        else:
            sans += 1
    from collectors.gdelt import DEPUIS_TRADUCTION

    # Complète seulement si la collecte du passé est remontée jusqu'au début de la reprise :
    # sans cela, « aucun candidat ancien en attente » veut seulement dire « pas encore collecté ».
    collectee = couverture_debut is not None and couverture_debut <= DEPUIS_TRADUCTION
    return {
        "reprise_complete": sans == 0 and collectee,
        "reprise_relue_jusqu_au": relue,
        "candidats_sans_decision": sans,
        "reprise_collectee_depuis": str(couverture_debut) if couverture_debut else None,
    }


def etat_d7(conn: sqlite3.Connection, raw_dir: Path, aujourd_hui: dt.date) -> dict:
    """État de la validation, pour le site et la publication des issues."""
    from extract.d7_candidats import candidats

    comptes, categories, serveur = validateurs(), categories_d7(), comptes_serveur()
    statuts: dict[str, str] = {}
    en_attente, a_corriger = 0, []
    insts = issues_figees(conn, raw_dir)
    for _, inst in insts:
        statut, _, motif = statut_complet(inst, comptes, categories, serveur)
        if evt := evenement_de(inst["corps"]):
            statuts[evt] = statut
        en_attente += statut == "en_attente"
        if statut == "a_corriger":
            a_corriger.append((inst["numero"], motif))
    cands = [(c.evenement_id, c.jour) for c in candidats(conn, raw_dir)]
    from collectors.gdelt import SOURCE_ID_TRADUCTION

    row = conn.execute(
        "SELECT min(substr(external_id, 1, 10)) FROM raw_documents"
        " WHERE source_id = ? AND external_id LIKE '____-__-__.tsv.gz'",
        (SOURCE_ID_TRADUCTION,),
    ).fetchone()
    couverture = dt.date.fromisoformat(row[0]) if row and row[0] else None
    return {
        "instantanes": len(insts),
        "en_attente": en_attente,
        "a_corriger": a_corriger,
        "validateurs": len(comptes),
        **etat_reprise(cands, statuts, aujourd_hui, couverture),
    }


def empreinte_decisions(conn: sqlite3.Connection, raw_dir: Path) -> str:
    """Empreinte de tout ce que les issues font compter (statut, catégorie, lieu, date) : la
    tâche horaire republie quand elle change, quel que soit le passage qui l'a changée."""
    import hashlib
    import json

    comptes, categories, serveur = validateurs(), categories_d7(), comptes_serveur()
    lignes = []
    for _, inst in issues_figees(conn, raw_dir):
        statut, cat, motif = statut_complet(inst, comptes, categories, serveur)
        lignes.append([inst["numero"], statut, cat, motif, lieu_et_date(inst)])
    return hashlib.sha256(json.dumps(lignes, ensure_ascii=False).encode()).hexdigest()
