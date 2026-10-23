# Registre des traitements et analyse d'impact de Relay

Tenu par Julien Renaud, responsable du traitement. Établi le 23 octobre 2026 à partir du code de `relay-serveur` (`relay_serveur/`, `deploy/`) et de l'app `relay` (`Coach/`, `CoachCoeur/`). À mettre à jour à chaque changement de ce que le relais stocke, et à relire avec l'avocat en même temps que la politique de confidentialité.

## Responsable du traitement

- Julien Renaud, développeur indépendant, France.
- Adresse : [À COMPLÉTER : adresse postale]
- SIRET : [À COMPLÉTER : SIRET, s'il existe]
- Contact : support@relay-agent.app
- Délégué à la protection des données : aucun (pas d'obligation de désignation identifiée à ce stade ; à confirmer avec l'avocat, l'art. 37.1.c visant le traitement à grande échelle de données de l'art. 9).

## Registre (article 30)

### T1. Transport chiffré des données Santé et des séances

| Rubrique | Contenu |
|---|---|
| Finalité | Transmettre les données Apple Health de l'utilisateur à son propre agent IA, et les séances planifiées par l'agent à l'app, qui les programme sur l'Apple Watch |
| Base légale | Art. 6.1.b (exécution du service) ; art. 9.2.a (consentement explicite : autorisation Santé dans iOS, puis liaison d'un agent) |
| Personnes concernées | Utilisateurs de l'app Relay |
| Données, chiffrées de bout en bout (illisibles par le responsable) | Pas, énergie active et au repos, minutes d'exercice, énergie, protéines, glucides, lipides et eau consommés, poids, taille, VFC, fréquence cardiaque au repos, sommeil par phase, séances (durée, distance, énergie, fréquence cardiaque moyenne, maximale et par minute, événements, tracé GPS échantillonné), état de la synchro (heure, dernier échantillon par type, nom de l'iPhone, 12 dernières lignes du journal de l'app), séances planifiées (`prevu.json`) |
| Données en clair | Identifiant de compte aléatoire (base32, 26 caractères), SHA-256 du jeton, `cree_le`, `vu_le`, nom des blobs (type et mois, ou date et identifiant de séance), taille, date de dépôt |
| Destinataires | Agent de l'utilisateur, seul à détenir la clé ; OVHcloud comme hébergeur (blobs chiffrés) |
| Durée | Blobs de métriques et de séances : 13 mois glissants, retirés par l'app à chaque synchro (`Blobs.horizon`, `Differentiel.aRetirer`). `etat.json` et `prevu.json` : remplacés à chaque dépôt. Compte et blobs : jusqu'à `DELETE /comptes/moi`, ou purge après 365 jours sans requête authentifiée (`__main__.entretien`, toutes les heures) |
| Transfert hors UE | Aucun |
| Sécurité | AES-256-GCM, nonce de 12 octets, `aad = id ‖ nom du blob` ; clé de 32 octets générée sur l'iPhone, trousseau `AfterFirstUnlock`, jamais iCloud ; TLS par Caddy ; quotas 1 000 blobs, 200 Mo, 1 Mo par blob, 600 requêtes par minute |

### T2. Appairage d'un agent

| Rubrique | Contenu |
|---|---|
| Finalité | Remettre à l'agent l'identité du compte (`id`, jeton, clé) sans que l'utilisateur recopie un secret |
| Base légale | Art. 6.1.b |
| Données | Identifiant de session (8 caractères), clés publiques X25519 éphémères de l'agent et de l'app, identité chiffrée (AES-256-GCM, clé dérivée par HKDF-SHA256), `cree_le` ; adresse IP en mémoire |
| Durée | Session inutilisable après 10 minutes (`appairages.DUREE`), supprimée par l'agent à la fin ou par la purge horaire. IP : fenêtre glissante d'une heure en mémoire, perdue au redémarrage |
| Sécurité | Comparaison d'un code à six chiffres des deux côtés ; la clé de l'app ne peut être posée qu'une fois (409) ; 10 sessions par heure et par IP ; corps limité à 4 Ko |

### T3. Réveil de l'iPhone à la demande

| Rubrique | Contenu |
|---|---|
| Finalité | Permettre à l'agent d'obtenir des données fraîches |
| Base légale | Art. 6.1.b |
| Données | Jeton APNs et environnement (`sandbox` ou `production`), dates des réveils |
| Destinataire | Apple (APNs) : jeton de l'appareil et notification vide `content-available` |
| Durée | Jeton : jusqu'à suppression du compte, ou effacé si APNs répond 410. Dates de réveil : celles de plus d'une heure sont effacées au réveil suivant ; toutes avec le compte |
| Limites | 6 réveils par heure, pas de réveil si `etat.json` a moins de 120 s, réservé aux abonnés (402) |

### T4. Abonnement

| Rubrique | Contenu |
|---|---|
| Finalité | Réserver aux abonnés le dépôt de `prevu.json` et le rafraîchissement |
| Base légale | Art. 6.1.b |
| Données | `abonne_jusqu_au`, `transaction_origine` (originalTransactionId) ; l'`appAccountToken` vérifié est un UUID v5 dérivé de l'identifiant de compte |
| Destinataire | Aucun : la signature JWS est vérifiée en local avec les racines Apple. Apple traite le paiement comme responsable distinct |
| Durée | Avec le compte |

### T5. Exploitation et sécurité du relais

| Rubrique | Contenu |
|---|---|
| Finalité | Diagnostiquer, protéger et restaurer le service |
| Base légale | Art. 6.1.f (intérêt légitime : service sûr et disponible) |
| Données | Journal (`limites.debit_et_journal`) : méthode, chemin, code, identifiant de compte, durée ; nom d'exception en cas d'erreur 500. Pas de corps, pas d'IP (uvicorn en `warning`, pas de journal d'accès Caddy configuré, jetons APNs masqués en coupant les lignes INFO de `httpx`). Compteurs du jour (`compteurs.txt`) : date, comptes vus, `etat.json` déposés, sans identifiant |
| Sauvegardes | `sqlite3 .backup` chaque nuit vers 03 h 30, puis restic chiffré vers l'Object Storage OVHcloud EU-WEST-PAR ; rétention 7 quotidiennes et 4 hebdomadaires (environ cinq semaines). Option de sauvegarde automatique du VPS chez OVHcloud en plus |
| Durée | Journal : 30 jours (journald, `MaxRetentionSec=30day`, posé par Ansible). Sauvegardes restic : environ cinq semaines. Sauvegarde OVHcloud du VPS : 7 jours (les sept dernières sauvegardes quotidiennes de l'option). Compteurs : sans limite (anonymes) |
| Destinataire | OVHcloud |

### Sous-traitants

| Sous-traitant | Rôle | Localisation | Garanties |
|---|---|---|---|
| OVH SAS (OVHcloud) | VPS du relais (Debian 13, centre GRA par défaut), Object Storage des sauvegardes (EU-WEST-PAR), DNS | France | Contrat de sous-traitance OVHcloud (art. 28) à archiver : [À COMPLÉTER : référence ou date d'acceptation du DPA OVHcloud] |

Apple n'est pas listé comme sous-traitant : APNs et l'App Store sont des services qu'Apple fournit en responsable de ses propres traitements. À confirmer avec l'avocat.

## Analyse d'impact (AIPD, article 35)

### Pourquoi une AIPD

Relay traite des données de santé (art. 9) et des tracés GPS, à destination d'un nombre d'utilisateurs qui peut croître, avec une technologie peu courante (relais chiffré, agent IA tiers). Deux critères de la liste du CEPD sont remplis (données sensibles, usage innovant) : l'AIPD est requise.

### Description

L'app lit Apple Health, chiffre sur l'iPhone et dépose des blobs opaques sur le relais. Le client `relay-agent`, lancé par l'utilisateur sur sa machine, les déchiffre avec la phrase d'appairage. Le responsable n'a jamais la clé.

### Nécessité et proportionnalité

- Minimisation : le serveur ne garde que ce qu'exigent le routage (identifiant, nom de blob), l'authentification (empreinte du jeton), le réveil (jeton APNs) et l'abonnement (date de fin, transaction d'origine).
- Pas d'email, pas de nom, pas d'IP sur disque.
- Durées bornées : 13 mois glissants pour les blobs, 365 jours d'inactivité pour le compte, 10 minutes pour l'appairage, environ cinq semaines pour les sauvegardes.
- Effacement en un geste depuis l'app, en cascade (`on delete cascade` sur `blobs` et `reveils`).

### Risques et mesures

| Risque | Vraisemblance | Gravité | Mesures en place | Risque résiduel |
|---|---|---|---|---|
| Fuite de la base ou d'une sauvegarde | Limitée | Limitée : blobs illisibles sans la clé | Chiffrement de bout en bout, `aad` liant blob et compte, sauvegardes restic chiffrées, SSH par clé, fail2ban, service systemd durci | Faible. Métadonnées exposées : types de données présents et mois couverts, tailles, dates, fréquence d'usage |
| Accès d'un tiers à un compte | Limitée | Importante | Jeton aléatoire de 256 bits, gardé haché ; limite de débit ; phrase refusée par le client si lisible par d'autres utilisateurs | Faible |
| Interception de l'appairage par le relais ou un tiers | Négligeable | Importante | Comparaison humaine d'un code à six chiffres dérivé de X25519 ; clé de l'app posée une seule fois | Faible |
| Fuite de la phrase chez l'utilisateur (agent, fichier, modèle) | Importante | Importante | Fichier en mode 600 exigé ; pont sans secret pour les agents en bac à sable ; avertissement dans l'app ; régénération possible | Moyen, hors du contrôle du responsable : à expliquer dans la politique (fait, section 9) |
| Données envoyées par l'agent au fournisseur de son modèle | Importante | Importante | Hors du périmètre du responsable ; information claire de l'utilisateur | Moyen, porté par l'utilisateur |
| Réquisition | Négligeable | Limitée | Le responsable ne peut remettre que les métadonnées | Faible |
| Corrélation par les métadonnées (horaires de synchro, présence d'une métrique) | Limitée | Limitée | Noms de blobs sans valeur ; journal sans IP | Faible |
| Données conservées au-delà de 13 mois si l'app ne synchronise plus | Limitée | Limitée | Purge après 365 jours sans requête ; suppression depuis l'app | Faible, mais un agent qui interroge seul garde le compte actif |

### Points à traiter avant la mise en vente

1. Fixer une durée de conservation du journal système (par exemple `MaxRetentionSec=30day` dans journald) et l'écrire dans la politique.
2. Relever la durée de la sauvegarde automatique du VPS chez OVHcloud, ou retirer l'option si restic suffit.
3. Vérifier que le VPS est bien en France : la variable Terraform `vps_datacenter` prévoit `UK` si le stock manque, ce qui contredirait la politique.
4. Archiver le contrat de sous-traitance d'OVHcloud.
5. Si le site est servi par Caddy sur le même VPS, garder le journal d'accès de Caddy désactivé, ou l'ajouter à ce registre.

### Conclusion

Le risque résiduel est faible pour ce que le responsable contrôle, parce qu'il ne détient jamais la clé. Les risques moyens tiennent à ce que fait l'utilisateur de ses données chez son agent, et la politique l'en informe. Le traitement peut démarrer une fois les cinq points ci-dessus traités.
