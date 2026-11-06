# Publication du prototype

Version consultable en ligne du prototype (`front/prototype/`), publiée comme page Artifact
privée sur claude.ai : https://claude.ai/artifact/Wd69scryvAZ4Yiggq1c5AF

```sh
make publication      # régénère data.js depuis la base puis écrit front/publication/dist/
```

`build.py` adapte la page aux règles des pages publiées : pas d'enveloppe `<html>` (ajoutée à
la publication), pas de Font Awesome (feuilles de style externes bloquées : icônes masquées,
chevrons et bouton de thème dessinés en CSS), encadré « Documents de travail » (dossier des
seuils, document de vérification). Le prototype local n'est pas modifié.

La page publiée ne se met pas à jour seule : après une collecte, relancer `make publication`
puis republier `front/publication/dist/index.html` avec `data.js` (depuis une session Claude
Code, sur la même adresse). `dist/` est généré et non versionné.
