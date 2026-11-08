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
release courante. Depuis l'installation de la CD, les blocs Caddy servent
`/data/hcompanion/landing/current` : une publication bascule ce lien atomiquement,
sans recharger Caddy.
Sur l'hôte, ce dossier est dans le volume persistant `dejabu-edge_data`.
Les sauvegardes de configuration et le manifeste de déploiement restent privés
sous `/opt/hcompanion/landing/`.

L'ancien script d'installation `scripts/deploy-public-landing.py` utilise une liste fermée de fichiers, vérifie
leur digest, refuse une modification concurrente du Caddyfile et valide la
configuration candidate dans Caddy avant de la charger. Il conserve l'inode du
Caddyfile monté en lecture seule dans le conteneur, puis recharge Caddy sans
recréer ni redémarrer les services. Seul le bloc entre
`BEGIN HCOMPANION PUBLIC LANDING` et `END HCOMPANION PUBLIC LANDING` lui appartient.
Le retour arrière en cas d'échec de reload est conditionné à l'absence d'autre
modification ; il ne restaure pas aveuglément une ancienne configuration.

Ce script a servi à la première installation. **Ne pas le relancer pour une
publication courante** : il repointerait Caddy vers une release fixe et
court-circuiterait le lien utilisé par la CD. Sa commande historique était :

```sh
python3 scripts/deploy-public-landing.py \
  --ssh-config /chemin/prive/ssh-config \
  --expect-caddy-sha <sha256-actuel>
```

Ajouter `--apply` pour publier les sept fichiers contrôlés. Le script ne change
pas les DNS. Le SHA du Caddyfile immédiatement après cette première publication
est `52db8bb36f2e564d9de47f1963c655e0e05f787270c60da9f5716f7c9cc1ba6b` ;
ce n'est pas une valeur à réutiliser sans vérifier l'état courant.

## Déploiement continu après merge

Le workflow `.github/workflows/deploy-landing.yml` publie depuis **main uniquement**,
après modification de `landing/**`, du client de publication ou du workflow.
Un lancement manuel est également possible depuis GitHub Actions sur main.
La règle du dépôt reste PR + revue par un coéquipier avant fusion.

1. Les cinq tests de la homepage doivent passer.
2. `scripts/landing_cd.py` transmet exclusivement les sept assets autorisés.
3. Le récepteur vérifie les noms, tailles et SHA-256, crée une release immuable,
   puis remplace `current` atomiquement. Les anciennes releases sont conservées.
4. Le client relit les sept fichiers par HTTPS, avec validation TLS, et compare
   leur contenu octet par octet. Le job échoue si une vérification diffère.

Le compte VPS `hcompanion-deploy` utilise une clé distincte du compte opérateur.
La clé est enregistrée dans le secret GitHub **LANDING_DEPLOY_KEY** ; la clé
publique du serveur, vérifiée via l'accès opérateur existant, est épinglée dans
**LANDING_KNOWN_HOSTS**. Aucun secret ne figure dans le dépôt.

La clé SSH ne permet que la commande `deploy`, sans terminal ni transfert de
ports. Elle appelle un récepteur Python détenu par root via une entrée sudo
limitée à cette commande exacte. Elle ne peut modifier ni ce récepteur, ni sa
propre autorisation, ni Caddy. Le récepteur refuse les fichiers supplémentaires,
chemins arbitraires, liens symboliques et contenus dont le digest diffère.

L'installation opérateur est `scripts/install_landing_cd.py` : elle exige le
SHA courant du Caddyfile, une clé **publique**, et l'accès SSH privé de l'opérateur.
Elle conserve les autres blocs et l'inode du fichier monté dans Caddy. Le SHA
après installation le 8 novembre est
`a8d960f386a574f0d57d46a8cba712e13efb09521c869fc37bd5e8e848ead632`.
Les sauvegardes restent privées sous `/opt/hcompanion/landing-cd/`.

Retour arrière : restaurer les fichiers de la release voulue dans une PR vers
main, puis fusionner après revue. Le workflow republie ce contenu et réutilise
sa release si elle existe déjà. En urgence, l'opérateur peut remplacer `current`
par un lien vers une release existante ; cette opération ne nécessite pas de
redémarrage de services.

### État de validation de la CD

Installation autorisée par Edouard et réalisée ; secrets GitHub configurés.
Une publication réelle utilisant la clé restreinte a réussi, avec vérification
HTTPS des sept fichiers. Une commande libre `id` avec cette même clé est refusée
(code 1, aucune sortie). Les neuf tests du récepteur et les cinq tests de la
homepage passent. Les autres blocs Caddy et identifiants de conteneurs sont
inchangés ; le portail Odoo reste protégé (401 sans identifiants).

La PR #10 a ensuite été fusionnée sur main (`b751d80`). Le premier
[run GitHub Actions](https://github.com/Tooom123/H-Company_Computer-Use_Hackathon/actions/runs/42448143936)
est **success** : tests et publication suivie des vérifications HTTPS terminés.
Le déclenchement après merge est donc confirmé, en plus du test SSH manuel.

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
