"""Envoie la page publique (front/publication/web/) vers l'hébergement web.

La collecte et les calculs restent sur la machine qui a l'archive brute ; l'hébergement ne
reçoit que des fichiers statiques : la page, ses données, ses polices (`assets/`) et les fichiers
de référencement. Configuration locale, hors git,
dans `config/deploiement.local` (lignes CLE=valeur) :

    # SSH (rsync) : la clé SSH doit être autorisée sur l'hébergement
    MODE=rsync
    DESTINATION=utilisateur@serveur:public_html/barometre/

    # ou FTP chiffré (FTPS) ; mot de passe dans ~/.netrc (machine <hôte> login ... password ...)
    MODE=ftps
    HOTE=ftp.exemple.fr
    UTILISATEUR=utilisateur
    DOSSIER=public_html/barometre
    # facultatif : certificats intermédiaires que le serveur n'envoie pas (PEM), ajoutés à la
    # vérification ; la chaîne doit toujours remonter à une racine de confiance du système
    INTERMEDIAIRES=config/deploiement.intermediaires.pem

    # ou copie locale, quand la collecte tourne sur le serveur qui héberge le site
    MODE=local
    DESTINATION=/home/utilisateur/barometre-democratique

    # adresse publique du site, une fois le domaine choisi (URL canonique, sitemap.xml)
    SITE_URL=https://exemple.fr/

Sans fichier de configuration, rien n'est envoyé (étape sans effet, code 0). En FTPS, chaque
fichier est d'abord envoyé sous un nom temporaire puis renommé : un visiteur ne voit jamais
une page à moitié envoyée. `data.js` part avant `index.html`.

Usage :
    python -m ops.deployer [--config CHEMIN] [--source DOSSIER]
"""

from __future__ import annotations

import argparse
import contextlib
import ftplib
import netrc
import os
import shutil
import ssl
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "deploiement.local"
SOURCE = ROOT / "front" / "publication" / "web"
# Données et fichiers annexes d'abord, page ensuite ; sitemap.xml seulement si le domaine est connu.
FICHIERS = (
    "data.js",
    "barometre.md",
    "indicateurs.csv",
    "llms.txt",
    "robots.txt",
    "favicon.svg",
    "sitemap.xml",
    "apercu.png",
    "404.html",
    ".htaccess",
    "index.html",
)
OBLIGATOIRES = ("data.js", "index.html")


def presents(source: Path) -> list[str]:
    """Fichiers à envoyer, chemins relatifs : polices et icônes (`assets/`), puis FICHIERS."""
    assets = sorted(
        p.relative_to(source).as_posix() for p in (source / "assets").rglob("*") if p.is_file()
    )
    return assets + [name for name in FICHIERS if (source / name).exists()]


def lire_config(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    conf = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            conf[key.strip().upper()] = value.strip()
    return conf


def envoi_rsync(source: Path, destination: str, run=subprocess.run) -> None:
    for name in presents(source):  # un appel par fichier : l'ordre est garanti
        # « /./ » + --relative : les sous-dossiers (assets/…) sont recréés à destination.
        run(
            ["rsync", "-az", "--relative", "--chmod=D755,F644", f"{source}/./{name}", destination],
            check=True,
        )


def envoi_local(source: Path, destination: str) -> None:
    """Copie dans un dossier du même serveur : chaque fichier est écrit sous un nom temporaire puis
    renommé (opération atomique), données avant la page."""
    dest = Path(destination).expanduser()
    for name in presents(source):
        cible = dest / name
        cible.parent.mkdir(parents=True, exist_ok=True)
        temp = cible.with_name(cible.name + ".envoi")
        shutil.copyfile(source / name, temp)
        temp.chmod(0o644)
        os.replace(temp, cible)


def envoi_ftps(
    source: Path,
    hote: str,
    utilisateur: str,
    dossier: str,
    ftp_factory=None,
    password: str | None = None,
    intermediaires: str | None = None,
) -> None:
    if password is None:
        auth = netrc.netrc().authenticators(hote)
        if not auth:
            raise SystemExit(f"[deployer] pas de mot de passe pour {hote} dans ~/.netrc")
        password = auth[2]
    if ftp_factory is None:
        # Certificat et nom d'hôte vérifiés avant l'envoi du mot de passe (le contexte par
        # défaut de FTP_TLS ne vérifie rien). HOTE doit être le nom inscrit dans le certificat.
        contexte = ssl.create_default_context()
        if intermediaires:
            contexte.load_verify_locations(cafile=intermediaires)
        ftp = ftplib.FTP_TLS(hote, timeout=60, context=contexte)
    else:
        ftp = ftp_factory(hote, timeout=60)
    try:
        ftp.login(utilisateur, password)
        if hasattr(ftp, "prot_p"):
            ftp.prot_p()  # canal de données chiffré
        ftp.cwd(dossier)
        crees = set()
        for name in presents(source):
            parties = name.split("/")[:-1]
            for i in range(1, len(parties) + 1):
                sous = "/".join(parties[:i])
                if sous not in crees:
                    with contextlib.suppress(ftplib.error_perm):  # dossier déjà présent
                        ftp.mkd(sous)
                    crees.add(sous)
            with open(source / name, "rb") as f:
                ftp.storbinary(f"STOR {name}.envoi", f)
            ftp.rename(f"{name}.envoi", name)
    finally:
        ftp.quit()


def deploy(config: Path = CONFIG, source: Path = SOURCE, **kw) -> str:
    conf = lire_config(config)
    if conf is None:
        return f"aucune configuration ({config.name}) : rien envoyé"
    for name in OBLIGATOIRES:
        if not (source / name).exists():
            raise SystemExit(f"[deployer] {source / name} absent : lancer make publication-web")
    mode = conf.get("MODE", "rsync")
    if mode == "rsync":
        envoi_rsync(source, conf["DESTINATION"], **kw)
        return f"envoyé par rsync vers {conf['DESTINATION']}"
    if mode == "local":
        envoi_local(source, conf["DESTINATION"])
        return f"copié dans {conf['DESTINATION']}"
    if mode == "ftps":
        envoi_ftps(
            source,
            conf["HOTE"],
            conf["UTILISATEUR"],
            conf.get("DOSSIER", "."),
            intermediaires=conf.get("INTERMEDIAIRES") or None,
            **kw,
        )
        return f"envoyé par FTPS vers {conf['HOTE']}:{conf.get('DOSSIER', '.')}"
    raise SystemExit(f"[deployer] MODE inconnu : {mode!r} (rsync, ftps ou local)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ops.deployer")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args(argv)
    print(f"[deployer] {deploy(args.config, args.source)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
