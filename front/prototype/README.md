# Prototype front — jetable

Maquette fonctionnelle de la page publique du baromètre, pour juger si l'idée mérite d'être
poursuivie. **Pas du code de production** : pas de tests, Tailwind chargé depuis son CDN de
développement, graphiques SVG écrits à la main.

```sh
make prototype        # exporte data.js depuis la base puis sert la page sur http://127.0.0.1:8765
```

- `export_data.py` lit `data/barometre.sqlite` (après `make rebuild`) et écrit `data.js`
  (généré, non versionné).
- `index.html` : page unique (Tailwind, Font Awesome, Source Serif 4), clair / sombre.

Partis pris : ton informatif plutôt qu'alarmant ; pas de seuils tant que le comité ne les a
pas fixés — la jauge situe la valeur actuelle dans la distribution historique (depuis 1959)
au lieu de la qualifier ; aucun nom de parti ni de personne.
