# Workout Sync — PWA v0.4

## Corrections

- compilation automatique dès qu’une séance est sélectionnée ;
- bouton de régénération conservé pour les modifications manuelles ;
- diagnostic visible de l’appel `/api/compile` ;
- erreur explicite si l’API renvoie du HTML, une réponse vide ou aucun script ;
- `moving_time` repris depuis le parseur Python ;
- lancement local corrigé avec `py -3 -m api.local_server`.

## Lancement

```powershell
py -3 -m pip install -r requirements.txt
npm.cmd install
npm.cmd run dev
```

Puis ouvrir `http://127.0.0.1:3000`.
