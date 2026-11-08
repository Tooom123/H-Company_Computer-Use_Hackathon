# Homepage publique — déploiement Netcup

La homepage est servie comme site statique par le proxy Caddy existant du VPS
`62.83.79.254`. Aucun moteur H, dashboard, compte, fichier de traces ou secret
n'est publié. La DA de Tom est conservée ; les prix sont présentés comme
illustratifs et les boutons de démonstration n'appellent aucun backend local.

- Domaine public HTTPS vérifié : **https://hcompanion.help/**.
- `https://www.hcompanion.help/` redirige vers le domaine principal.
- Preview HTTPS vérifiée : **https://hcompanion.62.83.79.254.sslip.io/**.
- La preview envoie `X-Robots-Tag: noindex, nofollow, noarchive`.

## DNS Namecheap

Les enregistrements suivants sont configurés dans Namecheap BasicDNS :

| Type | Hôte | Valeur |
| --- | --- | --- |
| A | `@` | `62.83.79.254` |
| CNAME | `www` | `hcompanion.help` |

Ils remplacent l'ancien parking `www → parkingpage.namecheap.com` et la
redirection de parking de `@`, avec un TTL de 30 minutes. Les serveurs de noms
et les MX/TXT de messagerie sont inchangés. L'utilisateur a confirmé la
vérification de son adresse auprès de Namecheap. Les certificats et la
redirection HTTP vers HTTPS sont gérés par Caddy.

## Release et isolation

Release SHA-256 :
`647060eea65275774aa6fbca996721126327f1a5f08a37cc2a835573b91d5722`.

Les sept fichiers publiés, pour **44 612 octets**, sont `index.html`, `style.css`,
`main.js`, `annotate.js`, `margin.js`, `billing.js` et `favicon.svg`.
Le dossier de tests n'est pas publié.

Dans le conteneur Caddy :
`/data/hcompanion/landing/releases/<digest>/` ; `current` est un lien vers la
release courante. Les blocs Caddy pointent directement vers la release immuable.
Sur l'hôte, ce dossier est dans le volume persistant `dejabu-edge_data`.
Les sauvegardes de configuration et le manifeste de déploiement restent privés
sous `/opt/hcompanion/landing/`.

`scripts/deploy-public-landing.py` utilise une liste fermée de fichiers, vérifie
leur digest, refuse une modification concurrente du Caddyfile et valide la
configuration candidate dans Caddy avant de la charger. Il conserve l'inode du
Caddyfile monté en lecture seule dans le conteneur, puis recharge Caddy sans
recréer ni redémarrer les services. Seul le bloc entre
`BEGIN HCOMPANION PUBLIC LANDING` et `END HCOMPANION PUBLIC LANDING` lui appartient.
Le retour arrière en cas d'échec de reload est conditionné à l'absence d'autre
modification ; il ne restaure pas aveuglément une ancienne configuration.

Pour préparer une nouvelle release, relever le SHA-256 actuel du Caddyfile via
l'accès SSH privé, puis exécuter d'abord le mode descriptif :

```sh
python3 scripts/deploy-public-landing.py \
  --ssh-config /chemin/prive/ssh-config \
  --expect-caddy-sha <sha256-actuel>
```

Ajouter `--apply` pour publier les sept fichiers contrôlés. Le script ne change
pas les DNS. Le SHA du Caddyfile immédiatement après cette première publication
est `52db8bb36f2e564d9de47f1963c655e0e05f787270c60da9f5716f7c9cc1ba6b` ;
ce n'est pas une valeur à réutiliser sans vérifier l'état courant.

## Vérifications effectuées

La preview répond **200 avec un certificat TLS valide**. Les sept assets relus
par HTTPS sont identiques octet par octet à la release locale. `/.env` et
`/test/public-demo.test.mjs` répondent **404**.

Après enregistrement des DNS Namecheap, Caddy a obtenu automatiquement les deux
certificats de production. Le domaine principal répond **200** avec validation
TLS normale ; `www` répond **301** vers `https://hcompanion.help/`, avec un
certificat valide également. Le contrôle `www` a ciblé l'adresse du VPS par
`curl --resolve` pour éviter un ancien cache de parking, sans désactiver TLS.
Les deux serveurs DNS autoritatifs et le résolveur `1.1.1.1` publient les nouvelles
valeurs ; les autres caches peuvent conserver les anciennes valeurs pendant leur TTL.

Les blocs Caddy préexistants ont été conservés, les **19 identifiants de
conteneurs** sont inchangés et les réponses des services existants sont identiques
avant/après : application Bruxelles **200**, caisse Bruxelles **303**, portail
Odoo protégé **401** sans identifiants. Ces contrôles établissent la disponibilité
HTTP et l'absence de recréation de conteneurs ; ils ne remplacent pas une recette
métier Odoo.
