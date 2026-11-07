# ruff: noqa: E501
from pathlib import Path

import pytest

from ops import deployer


@pytest.fixture
def web(tmp_path):
    src = tmp_path / "web"
    src.mkdir()
    (src / "index.html").write_text("<!doctype html>")
    (src / "data.js").write_text("window.BAROMETRE={}")
    return src


def test_sans_configuration_rien_n_est_envoye(tmp_path, web):
    assert "rien envoyé" in deployer.deploy(tmp_path / "absent.local", web)


def test_rsync_envoie_les_donnees_avant_la_page(tmp_path, web):
    conf = tmp_path / "d.local"
    conf.write_text("# commentaire\nMODE=rsync\nDESTINATION=u@h:public_html/b/\n")
    calls = []
    deployer.deploy(conf, web, run=lambda cmd, check: calls.append(cmd))
    assert [c[-2].rsplit("/", 1)[1] for c in calls] == ["data.js", "index.html"]
    assert all(c[-1] == "u@h:public_html/b/" for c in calls)


class FakeFTP:
    def __init__(self, host, timeout):
        self.log = [("connect", host)]
        FakeFTP.last = self

    def login(self, user, password):
        self.log.append(("login", user, password))

    def prot_p(self):
        self.log.append(("prot_p",))

    def cwd(self, d):
        self.log.append(("cwd", d))

    def mkd(self, d):
        self.log.append(("mkd", d))

    def storbinary(self, cmd, f):
        self.log.append(("stor", cmd.split()[1], f.read()))

    def rename(self, a, b):
        self.log.append(("rename", a, b))

    def quit(self):
        self.log.append(("quit",))


def test_ftps_envoi_sous_nom_temporaire_puis_renommage(tmp_path, web):
    conf = tmp_path / "d.local"
    conf.write_text("MODE=ftps\nHOTE=ftp.exemple.fr\nUTILISATEUR=moi\nDOSSIER=public_html/b\n")
    deployer.deploy(conf, web, ftp_factory=FakeFTP, password="secret")
    log = FakeFTP.last.log
    assert ("prot_p",) in log and ("cwd", "public_html/b") in log
    renames = [e for e in log if e[0] == "rename"]
    assert renames == [
        ("rename", "data.js.envoi", "data.js"),
        ("rename", "index.html.envoi", "index.html"),
    ]
    assert log[-1] == ("quit",)


def test_mode_inconnu(tmp_path, web):
    conf = tmp_path / "d.local"
    conf.write_text("MODE=scp\n")
    with pytest.raises(SystemExit, match="MODE inconnu"):
        deployer.deploy(conf, web)


def test_ftps_verifie_le_certificat(monkeypatch, tmp_path, web):
    seen = {}

    class Capture(FakeFTP):
        def __init__(self, host, timeout, context=None):
            super().__init__(host, timeout)
            seen["context"] = context

    monkeypatch.setattr(deployer.ftplib, "FTP_TLS", Capture)
    deployer.envoi_ftps(web, "ftp.exemple.fr", "moi", ".", password="x")
    ctx = seen["context"]
    assert ctx.verify_mode == deployer.ssl.CERT_REQUIRED and ctx.check_hostname


def test_ftps_intermediaires_ajoutes_sans_relacher_la_verification(monkeypatch, web):
    seen = {}

    class Capture(FakeFTP):
        def __init__(self, host, timeout, context=None):
            super().__init__(host, timeout)
            seen["context"] = context

    monkeypatch.setattr(deployer.ftplib, "FTP_TLS", Capture)
    pem = Path(__file__).parent / "fixtures" / "letsencrypt_yr2.pem"
    base = deployer.ssl.create_default_context().cert_store_stats()["x509_ca"]
    deployer.envoi_ftps(web, "ftp.exemple.fr", "moi", ".", password="x", intermediaires=str(pem))
    ctx = seen["context"]
    assert ctx.verify_mode == deployer.ssl.CERT_REQUIRED and ctx.check_hostname
    assert ctx.cert_store_stats()["x509_ca"] == base + 1


def test_ftps_cree_les_sous_dossiers_et_envoie_les_polices_avant_la_page(tmp_path, web):
    (web / "assets" / "fa" / "css").mkdir(parents=True)
    (web / "assets" / "fa" / "css" / "solid.min.css").write_text("x")
    (web / "assets" / "polices.css").write_text("y")
    deployer.envoi_ftps(web, "h", "u", ".", ftp_factory=FakeFTP, password="p")
    log = FakeFTP.last.log
    assert [e[1] for e in log if e[0] == "mkd"] == ["assets", "assets/fa", "assets/fa/css"]
    stors = [e[1] for e in log if e[0] == "stor"]
    assert stors == [
        "assets/fa/css/solid.min.css.envoi",
        "assets/polices.css.envoi",
        "data.js.envoi",
        "index.html.envoi",
    ]


def test_rsync_recree_les_sous_dossiers(tmp_path, web):
    (web / "assets").mkdir()
    (web / "assets" / "p.woff2").write_bytes(b"0")
    calls = []
    deployer.envoi_rsync(web, "u@h:b/", run=lambda cmd, check: calls.append(cmd))
    assert calls[0][-2] == f"{web}/./assets/p.woff2" and "--relative" in calls[0]


def test_copie_locale_atomique_avec_sous_dossiers(tmp_path, web):
    (web / "assets" / "fa").mkdir(parents=True)
    (web / "assets" / "fa" / "x.css").write_text("css")
    conf = tmp_path / "d.local"
    dest = tmp_path / "site"
    conf.write_text(f"MODE=local\nDESTINATION={dest}\n")
    assert "copié" in deployer.deploy(conf, web)
    assert (dest / "index.html").read_text() == "<!doctype html>"
    assert (dest / "assets" / "fa" / "x.css").read_text() == "css"
    assert not list(dest.rglob("*.envoi"))
