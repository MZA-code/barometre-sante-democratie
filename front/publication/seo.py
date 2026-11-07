"""Référencement de la version web : contenu lisible sans JavaScript, métadonnées, fichiers pour
les moteurs de recherche (SEO) et pour les assistants d'IA (GEO).

La page du prototype construit tout son contenu chiffré en JavaScript ; un robot qui ne
l'exécute pas ne verrait aucun chiffre. On écrit donc dans le HTML, avant publication :
  - le titre, la description, les balises Open Graph et une description schema.org (Dataset) ;
  - l'indice illustratif, sa phrase d'explication et la vue d'ensemble des 13 indicateurs
    (le JavaScript remplace ces contenus au chargement, avec les mêmes chiffres).
Et on écrit à côté de la page :
  - `barometre.md` : résumé en texte simple, chaque chiffre avec sa source ;
  - `indicateurs.csv` : les 13 indicateurs, valeur actuelle et position dans leur historique ;
  - `llms.txt` : point d'entrée pour les assistants d'IA (format llmstxt.org) ;
  - `robots.txt`, et `sitemap.xml` si l'adresse du site est connue (`SITE_URL`) ;
  - `.htaccess` (Apache, hébergement mutualisé) : fichiers texte servis en UTF-8 et, si
    `SITE_URL` est en https, redirection permanente vers cette adresse (http et www).

Les positions sont calculées comme dans la page (`position` dans index.html) : part des mois
plus bas plus la moitié des mois égaux ; indice = moyenne simple × 100.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

TITRE = "Baromètre de la santé démocratique en France"
CODE = {
    "D2.contournement_parlement": "D2.1",
    "D2.procedure_acceleree": "D2.2",
    "D3.regimes_exception": "D3.1",
    "D3.lois_censurees": "D3.2",
    "D4.interdictions_manifester_juge": "D4.2*",
    "D6.traitements_malgre_reserves": "D6.2",
    "D5.temps_parole_executif": "D5.1",
    "D1.regles_electorales_avant_scrutin": "D1.1",
    "D1.scrutins_reportes": "D1.2",
    "D5.classement_rsf": "D5.3",
    "D5.journalistes_inquietes": "D5.2",
    "D6.techniques_renseignement": "D6.1",
    "D4.dissolutions_administratives": "D4.1",
}
ANCRE = {
    "D2.contournement_parlement": "t-evolution",
    "D2.procedure_acceleree": "d2-2",
    "D3.regimes_exception": "d3",
    "D3.lois_censurees": "d3-2",
    "D4.interdictions_manifester_juge": "d4-2",
    "D6.traitements_malgre_reserves": "d6-2",
    "D5.temps_parole_executif": "d5-1",
    "D1.regles_electorales_avant_scrutin": "d1",
    "D1.scrutins_reportes": "d1-table",
    "D5.classement_rsf": "d5-3",
    "D5.journalistes_inquietes": "d5-2",
    "D6.techniques_renseignement": "d6-1",
    "D4.dissolutions_administratives": "d4",
}
UNITE = {
    "nb_decrets_malgre_reserves": "décret",
    "nb_textes_electoraux_avant_scrutin": "loi",
    "nb_reports_scrutin": "report",
    "nb_journalistes_mesures": "journaliste",
    "jours_exception": "jour",
    "nb_dissolutions": "dissolution",
}
# Icône d'onglet : demi-cadran et repère, sans texte.
FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<path d="M4 24a12 12 0 0 1 24 0" fill="none" stroke="#2a78d6" stroke-width="5"/>'
    '<path d="M16 24 21 13" stroke="#0b0b0b" stroke-width="3" stroke-linecap="round"/>'
    "</svg>\n"
)
MOIS = [
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
]


def lire_donnees(data_js: str) -> dict:
    return json.loads(data_js[data_js.index("{") : data_js.rstrip().rstrip(";").rindex("}") + 1])


def position(d: dict) -> float:
    v = [m["v"] for m in d["mensuel"]]
    plus_bas = sum(1 for x in v if x < d["actuel"])
    egaux = sum(1 for x in v if x == d["actuel"])
    return (plus_bas + 0.5 * egaux) / len(v)


def indice(dimensions: list[dict]) -> int:
    return round(100 * sum(position(d) for d in dimensions) / len(dimensions))


def date_longue(iso: str) -> str:
    d = dt.date.fromisoformat(iso[:10])
    return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]} {d.year}"


def nombre(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def valeur(d: dict) -> str:
    m, v = d["metrique"], d["actuel"]
    if m.startswith(("ratio_", "part_")):
        return f"{round(v * 100)} %"
    if m == "rang_rsf":
        return "1er" if round(v) == 1 else f"{round(v)}e"
    if m == "personnes_surveillees":
        return f"{nombre(v)} personnes surveillées"
    if m in UNITE:
        return f"{nombre(v)} {UNITE[m]}{'s' if v > 1 else ''}"
    return nombre(v)


def lecture(score: int) -> str:
    if abs(score - 50) <= 5:
        return "dans l'ensemble, une situation proche de l'habitude"
    return f"dans l'ensemble, plus {'haut' if score > 50 else 'bas'} que d'habitude"


def lignes(data: dict) -> list[dict]:
    out = []
    for d in data["dimensions"]:
        out.append(
            {
                "code": CODE.get(d["id"], d["code"]),
                "id": d["id"],
                "indicateur": d["label"],
                "valeur": valeur(d),
                "valeur_brute": d["actuel"],
                "fin_couverture": d.get("fin_couverture") or "",
                "position": round(100 * position(d)),
                "mois_observes": len(d["mensuel"]),
                "depuis": d["debut_historique"][:4],
                "ancre": ANCRE.get(d["id"], ""),
            }
        )
    return sorted(out, key=lambda r: (-r["position"], r["code"]))


def description(data: dict) -> str:
    score = indice(data["dimensions"])
    jour = date_longue(data["fin_donnees"])
    return (
        "13 indicateurs sourcés sur l'état de la démocratie en France (Parlement, "
        "contre-pouvoirs, libertés, pluralisme, surveillance, élections), recalculés "
        "chaque jour depuis les données officielles. "
        f"Indice illustratif au {jour} : {score} sur 100 (50 = niveau habituel)."
    )


def json_ld(data: dict, site_url: str | None) -> str:
    rows = lignes(data)
    dataset = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": TITRE,
        "description": description(data),
        "inLanguage": "fr",
        "spatialCoverage": {"@type": "Place", "name": "France"},
        "dateModified": data["fin_donnees"],
        "isAccessibleForFree": True,
        "keywords": [
            "démocratie",
            "État de droit",
            "Parlement",
            "49.3",
            "libertés publiques",
            "liberté de la presse",
            "manifestations",
            "France",
        ],
        "variableMeasured": [
            {
                "@type": "PropertyValue",
                "name": f"{r['code']} {r['indicateur']}",
                "value": r["valeur"],
                "description": f"Position {r['position']} sur 100 dans son historique "
                f"(depuis {r['depuis']})",
            }
            for r in rows
        ],
        "isBasedOn": [s["url"] for s in data["sources"] if s["url"].startswith("http")],
        "distribution": [
            {
                "@type": "DataDownload",
                "encodingFormat": "text/csv",
                "contentUrl": "indicateurs.csv",
            },
            {
                "@type": "DataDownload",
                "encodingFormat": "text/markdown",
                "contentUrl": "barometre.md",
            },
        ],
    }
    if site_url:
        dataset["url"] = site_url
        for dist in dataset["distribution"]:
            dist["contentUrl"] = site_url.rstrip("/") + "/" + dist["contentUrl"]
    return json.dumps(dataset, ensure_ascii=False, indent=1).replace("</", "<\\/")


def entete(data: dict, site_url: str | None) -> str:
    desc = html.escape(description(data), quote=True)
    titre = html.escape(f"{TITRE} — 13 indicateurs sourcés", quote=True)
    tags = [
        f'<meta name="description" content="{desc}">',
        '<meta name="robots" content="index, follow">',
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="fr_FR">',
        f'<meta property="og:title" content="{titre}">',
        f'<meta property="og:description" content="{desc}">',
        '<meta name="twitter:card" content="summary">',
        '<link rel="icon" href="favicon.svg" type="image/svg+xml">',
        '<link rel="alternate" type="text/markdown" href="barometre.md" title="Résumé en texte">',
        '<link rel="alternate" type="text/csv" href="indicateurs.csv" title="Indicateurs (CSV)">',
    ]
    if site_url:
        tags += [
            f'<link rel="canonical" href="{html.escape(site_url)}">',
            f'<meta property="og:url" content="{html.escape(site_url)}">',
        ]
    tags.append(f'<script type="application/ld+json">\n{json_ld(data, site_url)}\n</script>')
    return "\n  ".join(tags)


def vue_statique(data: dict) -> tuple[str, str, str]:
    """Contenus de #t-indice, #indice-text et #overview, écrits avant le JavaScript."""
    score = indice(data["dimensions"])
    titre = f"{score} sur 100 : {lecture(score)}"
    texte = (
        f"Pour chacun des 13 indicateurs, position des douze derniers mois dans toute son "
        f"histoire : 0 au plus bas jamais observé, 100 au plus haut, 50 à un niveau habituel. "
        f"L'indice est la moyenne simple de ces positions. Au {date_longue(data['fin_donnees'])}."
    )
    items = "".join(
        f'<li><a href="#{r["ancre"]}"><strong>{html.escape(r["code"])}</strong> '
        f"{html.escape(r['indicateur'])} : position {r['position']} sur 100, "
        f"valeur actuelle {html.escape(r['valeur'])}</a></li>"
        for r in lignes(data)
    )
    return html.escape(titre), html.escape(texte), items


def appliquer(page: str, data: dict, site_url: str | None) -> str:
    page = re.sub(
        r"<title>.*?</title>",
        f"<title>{html.escape(TITRE)} — 13 indicateurs sourcés</title>",
        page,
        count=1,
        flags=re.S,
    )
    page = page.replace("</title>", "</title>\n  " + entete(data, site_url), 1)
    titre, texte, items = vue_statique(data)
    for ancre, contenu in (
        ('<h2 id="t-indice"', titre),
        ('<p id="indice-text"', texte),
        ('<ol id="overview"', items),
    ):
        motif = re.compile(re.escape(ancre) + r"([^>]*)></(h2|p|ol)>")
        page, n = motif.subn(
            lambda m, a=ancre, c=contenu: f"{a}{m.group(1)}>{c}</{m.group(2)}>", page
        )
        if n != 1:
            raise ValueError(f"emplacement {ancre} introuvable dans la page")
    return page


def resume_md(data: dict, site_url: str | None) -> str:
    score = indice(data["dimensions"])
    base = site_url.rstrip("/") + "/" if site_url else ""
    out = io.StringIO()
    w = out.write
    w(f"# {TITRE}\n\n")
    w(f"Données arrêtées au {date_longue(data['fin_donnees'])}. Prototype : la grille ")
    w("d'indicateurs est un brouillon, aucun seuil ni aucune pondération n'est encore fixé par ")
    w("le comité de méthode ; aucune note officielle n'est produite.\n\n")
    w("## Indice illustratif\n\n")
    w(f"**{score} sur 100** : {lecture(score)}. Pour chacun des 13 indicateurs, on situe la ")
    w("valeur des douze derniers mois dans toute l'histoire de la série (0 = plus bas jamais ")
    w("observé, 50 = habituel, 100 = plus haut). L'indice est la moyenne simple de ces 13 ")
    w("positions, à poids égaux. Une position plus haute correspond à ce que la grille tient ")
    w(
        "pour plus défavorable. Cet indice aide à lire l'ensemble ; "
        "il ne qualifie pas le régime.\n\n"
    )
    w("## Les 13 indicateurs\n\n")
    w("| Code | Indicateur | Valeur actuelle | Position (sur 100) | Série depuis |\n")
    w("| --- | --- | --- | --- | --- |\n")
    for r in lignes(data):
        lien = f"[{r['indicateur']}]({base}#{r['ancre']})" if r["ancre"] else r["indicateur"]
        court = " (série courte)" if r["mois_observes"] < 36 else ""
        if r["fin_couverture"]:
            court += f" ; relevé arrêté au {date_longue(r['fin_couverture'])}"
        w(f"| {r['code']} | {lien} | {r['valeur']} | {r['position']}{court} | {r['depuis']} |\n")
    w("\n## Données de contexte (non notées)\n\n")
    w("Présentées à côté des indicateurs, sans entrer dans l'indice : temps de parole des partis ")
    w("à la télévision et à la radio (Arcom), journées de mobilisation nationale (décomptes du ")
    w("ministère de l'Intérieur et des organisateurs côte à côte), participation aux élections ")
    w("législatives, déclarations des organes de l'ONU sur la France (citées mot pour mot), ")
    w("couverture de la France par la presse étrangère (GDELT).\n\n")
    w("## Méthode\n\n")
    w("- Chaque document collecté est archivé tel quel (URL, date, empreinte SHA-256) ; chaque ")
    w("chiffre remonte aux documents officiels qui le justifient.\n")
    w("- Aucun nom de parti ni de personnalité n'intervient dans les calculs.\n")
    w("- Les relevés faits à la main (manifestants, journalistes, déclarations de l'ONU) citent ")
    w("une source vérifiée mot pour mot.\n\n")
    w("## Sources\n\n")
    for s in data["sources"]:
        lien = f"[{s['nom']}]({s['url']})" if s["url"].startswith("http") else s["nom"]
        w(f"- {lien} — {s['licence']}\n")
    w("\n## Fichiers\n\n")
    w(f"- [Page du baromètre]({base or './'})\n")
    w(f"- [Indicateurs au format CSV]({base}indicateurs.csv)\n")
    return out.getvalue()


def indicateurs_csv(data: dict) -> str:
    out = io.StringIO()
    cols = [
        "code",
        "id",
        "indicateur",
        "valeur",
        "valeur_brute",
        "position",
        "mois_observes",
        "depuis",
        "fin_couverture",
    ]
    writer = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(lignes(data))
    return out.getvalue()


def llms_txt(data: dict, site_url: str | None) -> str:
    base = site_url.rstrip("/") + "/" if site_url else ""
    score = indice(data["dimensions"])
    return (
        f"# {TITRE}\n\n"
        f"> Treize indicateurs sourcés sur l'état de la démocratie en France, recalculés chaque "
        f"jour depuis les données officielles (Assemblée nationale, Journal officiel, Conseil "
        f"constitutionnel, CNIL, justice administrative, Arcom, RSF, CNCTR). Prototype : aucun "
        f"seuil ni aucune pondération n'est encore fixé ; l'indice affiché ({score} sur 100 au "
        f"{date_longue(data['fin_donnees'])}, 50 = niveau habituel) est illustratif.\n\n"
        "Pour citer un chiffre, reprendre sa date et sa source ; ne pas présenter l'indice "
        "illustratif comme une note officielle.\n\n"
        "## Données\n\n"
        f"- [Résumé complet en texte]({base}barometre.md) : indice, 13 indicateurs, contexte, "
        "méthode, sources\n"
        f"- [Indicateurs (CSV)]({base}indicateurs.csv) : valeur actuelle et position dans "
        "l'historique\n"
        f"- [Page interactive]({base or './'}) : graphiques et listes de faits, chacun lié à "
        "sa source\n"
    )


def robots_txt(site_url: str | None) -> str:
    out = "User-agent: *\nAllow: /\n"
    if site_url:
        out += f"\nSitemap: {site_url.rstrip('/')}/sitemap.xml\n"
    return out


def sitemap_xml(site_url: str, lastmod: str) -> str:
    base = site_url.rstrip("/") + "/"
    urls = "".join(
        f"  <url><loc>{html.escape(base + p)}</loc><lastmod>{lastmod}</lastmod></url>\n"
        for p in ("", "barometre.md", "indicateurs.csv")
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )


def htaccess(site_url: str | None) -> str:
    out = (
        "# Généré par front/publication/seo.py\n"
        "AddDefaultCharset UTF-8\n"
        "<IfModule mod_mime.c>\n"
        "  AddType text/markdown .md\n"
        "  AddCharset UTF-8 .md .txt .csv .js .svg .xml\n"
        "</IfModule>\n"
    )
    parts = urlsplit(site_url or "")
    if parts.scheme == "https" and parts.hostname:
        hote = parts.hostname
        out += (
            "<IfModule mod_rewrite.c>\n"
            "  RewriteEngine On\n"
            "  # validations des certificats (Let's Encrypt) laissées telles quelles\n"
            "  RewriteCond %{REQUEST_URI} !^/\\.well-known/\n"
            "  RewriteCond %{HTTPS} off [OR]\n"
            f"  RewriteCond %{{HTTP_HOST}} !^{re.escape(hote)}$ [NC]\n"
            f"  RewriteRule ^ https://{hote}%{{REQUEST_URI}} [R=301,L]\n"
            "</IfModule>\n"
        )
    return out


def ecrire(dist: Path, page: str, data_js: str, site_url: str | None) -> str:
    data = lire_donnees(data_js)
    page = appliquer(page, data, site_url)
    (dist / "barometre.md").write_text(resume_md(data, site_url), encoding="utf-8")
    (dist / "indicateurs.csv").write_text(indicateurs_csv(data), encoding="utf-8")
    (dist / "llms.txt").write_text(llms_txt(data, site_url), encoding="utf-8")
    (dist / "robots.txt").write_text(robots_txt(site_url), encoding="utf-8")
    (dist / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    (dist / ".htaccess").write_text(htaccess(site_url), encoding="utf-8")
    sitemap = dist / "sitemap.xml"
    if site_url:
        sitemap.write_text(sitemap_xml(site_url, data["fin_donnees"]), encoding="utf-8")
    elif sitemap.exists():
        sitemap.unlink()
    return page
