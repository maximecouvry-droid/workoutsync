# Workout Sync — PWA v0.2

Cette version transforme la base initiale en première interface réellement utilisable.

## Fonctionnalités

- identifiants mémorisés localement dans le navigateur ;
- réglages FTP, puissance IM et allures ;
- chargement des séances Notion `Status = To do` ;
- exclusion de la natation ;
- ajout manuel d’une séance ;
- sélection multiple ;
- édition locale du texte source, du script et du payload ;
- compilation par le parseur Python existant ;
- validation vert / bleu / orange / rouge ;
- blocage de l’envoi en présence d’une ligne rouge ;
- envoi groupé vers Intervals.icu ;
- passage de Notion à `Sync` après envoi ;
- PWA installable sur Windows et Android ;
- onglet d’aide Syntaxe Intervals.

## Lancer localement

```powershell
npm install
npm run dev
```

Ouvrir ensuite :

```text
http://localhost:3000
```

## Mettre à jour le dépôt GitHub

Après avoir remplacé le contenu du dossier local par cette version :

```powershell
git add .
git commit -m "Build usable PWA interface"
git push
```

## Déploiement Vercel

Importer le dépôt GitHub dans Vercel. Aucun secret serveur n’est requis :
les identifiants restent stockés dans le navigateur de chaque appareil.
