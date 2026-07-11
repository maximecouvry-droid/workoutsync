# Workout Sync

Première base PWA, sans modification de la base Notion ni du payload Intervals.

## Architecture
- Next.js pour l’interface installable sur Windows et Android.
- Fonction Python Flask sur Vercel.
- Parseur Python extrait de la V7.4.
- Identifiants conservés uniquement dans `localStorage` sur chaque appareil.

## Lancer en local
```bash
npm install
npm run dev
```
Puis ouvrir `http://localhost:3000`. Le frontend Next.js démarre localement. Pour tester la fonction Python exactement comme Vercel, utilise ensuite `vercel dev`.

## Déployer
1. Copier ce projet dans le dépôt GitHub.
2. Importer le dépôt dans Vercel.
3. Framework détecté : Next.js.
4. Aucun secret Vercel requis : les identifiants restent sur l’appareil.

## Étape actuelle
- interface PWA initiale ;
- endpoint `/api/compile` utilisant le parseur Python ;
- endpoints proxy Notion et Intervals prêts ;
- pas encore toute l’interface du logiciel Windows.
