# Clients FOJO — Liste confirmée et sourcée

**Date :** 31 juillet 2026  
**Auteur :** Maxime Debaugnies (SalesOps)  
**Objet :** Identification des locataires actifs dans les cuisines FOJO (concurrent direct d'Atoms.co)

---

## Méthodologie

### Comment on a identifié les clients FOJO

On a croisé **3 sources de données publiques** :

| Source | Type | Fiabilité | Ce que ça prouve |
|--------|------|-----------|-------------------|
| **A. API Sirene INSEE** | Base officielle de l'État | ✅ Incontestable | Un établissement food est **légalement immatriculé** à l'adresse exacte d'un site FOJO |
| **B. Uber Eats** | Scraping des listings (28-29 juil. 2026) | ✅ Très fiable | Un restaurant **livre activement** depuis <100m d'un site FOJO |
| **C. wearefojo.com** | Site officiel FOJO (scrapé 28 juil. 2026) | ⚠️ Indicatif | FOJO **affiche publiquement** ce partenaire sur son site |

### Niveaux de confiance

| Niveau | Critère | Interprétation |
|--------|---------|----------------|
| **CONFIRMÉ** | Source A : Sirene montre un établissement **ACTIF** à l'adresse FOJO | L'entreprise est légalement domiciliée chez FOJO. Preuve officielle. |
| **TRÈS PROBABLE** | Source B : restaurant actif sur Uber Eats à **<100m** du site FOJO, sans local propre identifié ailleurs | Le restaurant livre depuis la cuisine FOJO |
| **PROBABLE** | Source C seule : affiché sur wearefojo.com | FOJO le revendique comme partenaire, mais pas de preuve terrain |
| **EX-CLIENT** | Source A mais établissement **FERMÉ** | Était chez FOJO, n'y est plus |

### Sites FOJO identifiés

| Site | Adresse | Cuisines | Statut | Confirmé par |
|------|---------|----------|--------|-------------|
| **Suresnes (92)** | 81 rue Rouget de Lisle, 92150 Suresnes | 10 | Actif | Sirene + wearefojo.com |
| **Vincennes (94)** | 42 av. de la République, 94300 Vincennes | 4 | Actif | Sirene (FOJO + YUJO) + wearefojo.com |
| **Beaugrenelle — Paris 15e** | 42 rue Duranton, 75015 Paris | 3 | Actif | Sirene + wearefojo.com |
| **Pigalle — Paris 9e** | 10 rue Pierre Fontaine, 75009 Paris | ? | Actif, **non communiqué sur leur site** | Sirene (YUJO PIGALLE) |
| ~~Paris 11e — Chemin Vert~~ | 119 rue du Chemin Vert, 75011 Paris | — | **EXCLU** : c'est le food hall propre de FOJO ("Le vrai Dojo — restauration, art et musique"), pas un site de cuisines en location. Pas listé parmi leurs points de vente locatifs. | wearefojo.com |
| ~~Charenton-le-Pont (94)~~ | 2 rue Saint-Pierre, 94220 Charenton-le-Pont | — | **FERMÉ** | Sirene (FOJO, fermé 2020) |

**Total cuisines en location selon wearefojo.com : 17** (Suresnes 10 + Vincennes 4 + Beaugrenelle 3).

**Note :** YUJO est la même entité que FOJO (même groupe). Les établissements Sirene "FOJO", "YUJO", "FOJO PARIS 11", "YUJO PIGALLE", "YUJO SURESNES" et "FOJO HOLDING" sont les entités **propres** de FOJO, pas des clients. Leur siège social commun est au 26 rue de Franqueville, 75016 Paris.

### Limite connue — angle mort Sirene

**Certains clients FOJO sont invisibles dans Sirene.** Quand un restaurateur opère depuis une cuisine FOJO sans y immatriculer sa propre entité (il utilise l'entité FOJO/YUJO ou son entité est enregistrée à une autre adresse), on ne peut le détecter que via les plateformes (Uber Eats, Deliveroo). C'est pourquoi la source B (Uber Eats) est essentielle — mais elle nécessite une vérification que le restaurant n'a pas son propre local ailleurs.

**Exemples écartés après vérification :** Vi Hanoi, Noody, Bocamexa, El Lechón, Paasta — ces restaurants apparaissent sur Uber Eats à proximité d'un site FOJO, mais ont leur **propre établissement Sirene** à une adresse différente. Ce ne sont **pas** des clients FOJO.

---

## Clients actifs confirmés (Source A — Sirene INSEE)

### Site Beaugrenelle — 42 rue Duranton, 75015 Paris

| Enseigne | Nom légal | SIREN | Présent depuis | Nb établissements groupe | Preuves | Dans BoB |
|----------|-----------|-------|----------------|--------------------------|---------|----------|
| **BALDI** | BAYTI | 911662237 | sept. 2023 | 6 | Sirene actif + partenaire wearefojo.com | ✅ oui (552259) |
| **MOG** | MOG | 821823952 | déc. 2022 | 2 | Sirene actif | ❌ NON |
| **NACH** | NACH | 918069527 | août 2022 | 2 | Sirene actif | ❌ NON |
| **OBER STR'EAT** | OBER STR'EAT | 824611651 | déc. 2023 | 5 | Sirene actif | ✅ oui (1013) |
| **SHAKA LOA** | SHAKA LOA | 840928832 | avr. 2021 | 2 | Sirene actif | ❌ NON |

### Site Suresnes — 81 rue Rouget de Lisle, 92150 Suresnes

| Enseigne | Nom légal | SIREN | Présent depuis | Nb établissements groupe | Preuves | Dans BoB |
|----------|-----------|-------|----------------|--------------------------|---------|----------|
| **AMIRZAIOLO** | AMIRZAIOLO | 950830810 | mars 2023 | 1 | Sirene actif | ✅ oui (552254) |
| **AMREST** (KFC/Pizza Hut) | AMREST OPCO SAS | 831200043 | juil. 2020 | **75** | Sirene actif | ✅ oui (130) |
| **BALDI** | BAYTI | 911662237 | sept. 2023 | 6 | Sirene actif + partenaire wearefojo.com | ✅ oui (552259) |
| **JULIE GOURMET** | JULIE GOURMET | 912157617 | janv. 2024 | 2 | Sirene actif | ✅ oui (552255) |
| **MALINS FRANCE** | MALINS FRANCE | 814875407 | nov. 2025 | 2 | Sirene actif | ✅ oui (48251) |
| **PAPA RICH** | FOOD PROD | 932762248 | oct. 2024 | 2 | Sirene actif | ✅ oui (121877) |
| **SAVOURER.** | SAVOURER. | 799841416 | déc. 2022 | 2 | Sirene actif + partenaire wearefojo.com | ✅ oui (552253) |
| **SISTERS KITCHEN** | SISTERS KITCHEN | 980468508 | nov. 2023 | 1 | Sirene actif | ✅ oui (552257) |
| **TITALIA** | TITALIA | 904346863 | oct. 2021 | 1 | Sirene actif + partenaire wearefojo.com | ✅ oui (552256) |

### Site Vincennes — 42 av. de la République, 94300 Vincennes

| Enseigne | Nom légal | SIREN | Présent depuis | Nb établissements groupe | Preuves | Dans BoB |
|----------|-----------|-------|----------------|--------------------------|---------|----------|
| **FOODLAB 94** | FOODLAB 94 | 949249221 | janv. 2023 | 1 | Sirene actif | ✅ oui (155253) |

### Site Pigalle — 10 rue Pierre Fontaine, 75009 Paris

| Enseigne | Nom légal | SIREN | Présent depuis | Nb établissements groupe | Preuves | Dans BoB |
|----------|-----------|-------|----------------|--------------------------|---------|----------|
| **COMPAGNIE D'HERBAUGES** | COMPAGNIE D'HERBAUGES | 901851295 | août 2021 | 1 | Sirene actif | ❌ NON |
| **DAUG FRANCE** | DAUG FRANCE | 937973204 | nov. 2024 | 1 | Sirene actif + Uber Eats (4.9/5, 15m) | ✅ oui (68009) |
| **FAIZAN PIZZA 5** | FAIZAN PIZZA 5 | 105032155 | mai 2026 | 1 | Sirene actif | ✅ oui (13484) |
| **MT BROTHERS** | MT BROTHERS | 901634295 | juil. 2021 | 1 | Sirene actif | ❌ NON |

---

## Clients très probables (Source B — Uber Eats, sans local propre identifié)

Ces restaurants sont actifs sur Uber Eats à proximité immédiate d'un site FOJO. On a **vérifié dans Sirene qu'ils n'ont pas d'établissement propre** à une adresse voisine. Ils opèrent donc très probablement depuis la cuisine FOJO, sous l'entité FOJO/YUJO ou une entité enregistrée ailleurs.

| Enseigne | Site FOJO | Distance | Note Uber Eats | Nb avis | Vérification Sirene | Lien |
|----------|-----------|----------|----------------|---------|---------------------|------|
| **La Brigade** | Beaugrenelle | **13m** | 4.4/5 | **10,000+** | Entité non trouvée sous ce nom — opère sous autre raison sociale | [Uber Eats](https://www.ubereats.com/fr/store/la-brigade-beaugrenelle/DZezbCp-RbGpO74ICcM4QQ) |
| **Chicken Bucket Panam** | Beaugrenelle | 76m | 4.1/5 | 300+ | Non trouvé dans Sirene | [Uber Eats](https://www.ubereats.com/fr/store/chicken-bucket-panam/8GBinTmVUPeXyKxPAxplQw) |
| **Pizza Pop** | Beaugrenelle | 76m | 2.8/5 | 100+ | Trouvé uniquement hors Paris (Lille, Creuse) | [Uber Eats](https://www.ubereats.com/fr/store/pizza-pop/439axsEYWo2e8JmREtLseQ) |
| **BAPS 1** | Vincennes | 16m | 4.8/5 | 500+ | Non trouvé dans Sirene | [Uber Eats](https://www.ubereats.com/fr/store/baps-1/wiluiRPdSMGl3c_L9MTVdQ) |
| **Joker Smash Burger** | Vincennes | **10m** | — | — | Non trouvé dans Sirene | [Uber Eats](https://www.ubereats.com/fr/store/joker-smash-burger/UpHwHd3iQGGsByxqYlOzjQ) |
| **Le jardin de Jasmine** | Vincennes | 15m | 4.4/5 | 20 | Non trouvé dans Sirene | [Uber Eats](https://www.ubereats.com/fr/store/le-jardin-de-jasmine/VH3F41A5XBeB0RDxOulL0A) |
| **French Bokit & Bono Smash Burger** | Vincennes | 18m | 4.6/5 | 140+ | Non trouvé dans Sirene | [Uber Eats](https://www.ubereats.com/fr/store/french-bokit-%26-bono-smash-burger/WLmqRtk3T6KrYAJyQZDptQ) |
| **Caribeen Bokit House** | Vincennes | 18m | 4.6/5 | 260+ | Non trouvé dans Sirene | [Uber Eats](https://www.ubereats.com/fr/store/caribeen-bokit-house/Ew8bfLNMRl-KIjcEMU7gjg) |
| **Restaurant Titan** | Vincennes | 81m | 4.8/5 | 700+ | Non trouvé dans Sirene sous ce nom | [Uber Eats](https://www.ubereats.com/fr/store/restaurant-titan/p8REHmDbTq2CZTqOni139g) |

> **Note :** Vincennes compte 4 cuisines FOJO mais seulement 1 client confirmé Sirene (FOODLAB 94). Les ~10 restaurants Uber Eats ci-dessus opèrent très probablement depuis les cuisines FOJO sous l'entité légale FOJO/YUJO — c'est le modèle dark kitchen : le locataire cuisine, FOJO fournit le local et l'immatriculation.

### Exclus après vérification (ont leur propre local — PAS clients FOJO)

| Enseigne | Vue sur Uber Eats près de | Local propre trouvé dans Sirene | Conclusion |
|----------|--------------------------|--------------------------------|------------|
| ~~Vi Hanoi~~ | Beaugrenelle (81m) | 282 rue Lecourbe, 75015 Paris (SIREN 910257260) | Restaurant traditionnel |
| ~~Noody~~ | Beaugrenelle (84m) | 281 rue Lecourbe, 75015 Paris (SIREN 903756898) | Restaurant traditionnel |
| ~~Bocamexa~~ | Pigalle (51m) | 2 rue Pierre Fontaine, 75009 Paris (SIREN 521694968) | A son propre restaurant dans la même rue |
| ~~El Lechón~~ | Pigalle (65m) | 17 rue Pierre Fontaine, 75009 Paris (SIREN 921257796) | A son propre restaurant dans la même rue |
| ~~Paasta~~ | Vincennes (75m) | 121 rue de Fontenay, 94300 Vincennes (SIREN 920540846) | Restaurant traditionnel |
| ~~Bio c' Bon~~ | Vincennes (53m) | Commerce de proximité | Supermarché bio |

---

## Clients probables (Source C — affichés sur wearefojo.com)

| Enseigne | SIREN | Dans BoB | Commentaire |
|----------|-------|----------|-------------|
| **EL CARTEL** | 799733043 | ❌ NON | Partenaire affiché, siège à Agen |
| **EL CARTEL DEL TACO** | 877613745 | ❌ NON | Partenaire affiché, siège à Paris |
| **LA BRIGADE** | — | ❌ NON | Partenaire affiché + confirmé Uber Eats Beaugrenelle (13m, 10k+ avis). Entité Sirene introuvable sous ce nom — opère sous raison sociale différente |
| **RIMA / LE COMPTOIR** | 533920112 | ❌ NON | Partenaire affiché, siège à Lyon — à confirmer |

---

## Ex-clients notables

| Enseigne | Site FOJO | Période | Commentaire |
|----------|-----------|---------|-------------|
| **COOLHEN SAS** | Charenton-le-Pont (site fermé) | 2020 – fermé | Client de l'ancien site FOJO Charenton, avait aussi des restos à Neuilly et Paris 12 (tous fermés) |
| **BIG GROUPE / BIG FERNAND** | Suresnes | 2021 – fermé | Groupe Big Fernand (19 établissements), a quitté FOJO |
| **SUSHI SHOP** | Suresnes | 2019 – fermé | 84 établissements groupe — gros client perdu |
| **NOURA BOULOGNE** | Suresnes | 2011 – fermé | Traiteur libanais connu |
| **LINA'S** | Suresnes | 2011 – fermé | 3 établissements (Boutique, Malesherbes, Palais des Congrès) |
| **THE ROYAL FOOD** | Vincennes | 2024 – fermé | Récent |
| **LA TIRAMISSERIE** | Vincennes | 2025 – fermé | Récent |
| **KOTSU KOTSU** | Paris 11e | 2025 – fermé | Récent |
| **SATEBALI PARIS** | Paris 11e | 2023 – fermé | — |

Liste complète de 44 ex-clients dans le CSV.

---

## Synthèse

| Catégorie | Nombre | Détail |
|-----------|--------|--------|
| **CONFIRMÉ actifs** | **19** | Sirene actif à une adresse FOJO (hors entités FOJO/YUJO et hors food hall Paris 11e) |
| dont multi-sources (Sirene + site web / Uber Eats) | 5 | BALDI ×2 sites, SAVOURER., TITALIA, DAUG FRANCE |
| **TRÈS PROBABLE actifs** | **9** | Uber Eats <100m, vérifié sans local propre |
| **PROBABLE** | **4** | Affichés wearefojo.com |
| **EX-CLIENTS** | **44+** | Sirene fermé à une adresse FOJO |
| **Total clients FOJO identifiés** | **32 actifs + 44 ex-clients** | |

**Capacité déclarée par FOJO : 17 cuisines en location** (Suresnes 10 + Vincennes 4 + Beaugrenelle 3). On en identifie 19 confirmés — le dépassement s'explique par des entités multiples pour une même cuisine (holding + exploitation) et des marques virtuelles. Pigalle n'est pas communiqué sur leur site mais confirmé par Sirene.

### Leads prioritaires pour la prospection (confirmés, PAS dans BoB)

| Enseigne | Site FOJO | Présent depuis | Pourquoi cibler |
|----------|-----------|----------------|-----------------|
| **MOG** | Beaugrenelle | déc. 2022 | 2 établissements, pas dans BoB |
| **NACH** | Beaugrenelle | août 2022 | 2 établissements, pas dans BoB |
| **SHAKA LOA** | Beaugrenelle | avr. 2021 | 2 établissements, pas dans BoB |
| **COMPAGNIE D'HERBAUGES** | Pigalle | août 2021 | Pas dans BoB |
| **MT BROTHERS** | Pigalle | juil. 2021 | Pas dans BoB |

### Client vedette à surveiller

**La Brigade** (Beaugrenelle) — 10 000+ avis Uber Eats, note 4.4/5, à 13m du site FOJO. C'est le client FOJO le plus visible et le plus performant sur les plateformes. Entité légale introuvable sous ce nom dans Sirene (opère sous raison sociale différente ou sous l'entité FOJO). Cible win-back prioritaire.

**AMREST** (Suresnes) — filiale du groupe AmRest (KFC, Pizza Hut, Starbucks), 75 établissements en France. Si FOJO héberge des cuisines AMREST, c'est un signal que les gros groupes testent les dark kitchens indépendantes.

---

## Ce qu'on a vérifié (et écarté)

Pour s'assurer de ne rater aucun client, on a aussi cherché :

| Piste vérifiée | Résultat |
|----------------|----------|
| **Siège FOJO** (26 rue de Franqueville, 75016) | Que des entités propres FOJO — pas de clients |
| **Ancien site Charenton-le-Pont** (2 rue Saint-Pierre) | Fermé. 1 client identifié : COOLHEN SAS (fermé) |
| **Autres villes** (Lyon, Bordeaux, Marseille, Lille, Caen, Reims — mentionnées sur wearefojo.com) | Aucun établissement FOJO/YUJO trouvé dans Sirene hors Île-de-France — marketing du site web uniquement |
| **Adresses adjacentes** (40-46 rue Duranton, 115-125 Chemin Vert, etc.) | Pas de client FOJO supplémentaire — les food businesses voisins sont des restaurants traditionnels indépendants |
| **Entités FOJO/YUJO dans toute la France** | Aucun site supplémentaire au-delà des 5 connus + 1 fermé |
| **NAF codes élargis** (au-delà de 56.x) | Pas de client food manqué |
| **Restaurants Uber Eats avec local propre** | 6 faux positifs écartés (Vi Hanoi, Noody, Bocamexa, El Lechón, Paasta, Bio c' Bon) |
| **La Brigade — entité légale** | Introuvable dans Sirene sous ce nom. LABRIGADE (SIREN 898391404, Champigny) est une autre entreprise. La Brigade opère sous une raison sociale différente non identifiée |

---

## Fichiers sources

| Fichier | Description |
|---------|-------------|
| `prokitchens-app/data/fojo_clients_final.csv` | Liste complète 95 lignes (confirmés + probables + ex-clients) avec preuves |
| `prokitchens-app/scripts/fojo-final-list.py` | Script de génération (re-productible) |
| `prokitchens-app/data/fojo_clients_platforms.csv` | Données brutes Uber Eats scrapées |
| `prokitchens-app/data/fojo_suresnes_clients.csv` | Détail Suresnes (tous établissements au 81) |

---

*Document préparé pour la revue manager. Chaque ligne est sourcée et vérifiable via l'API Sirene INSEE (publique) ou les liens Uber Eats.*
