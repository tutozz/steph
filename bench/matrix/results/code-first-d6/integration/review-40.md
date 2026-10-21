# D6 intégration : 40 phrases DEV changées tirées au hasard (graine 20261001)

Chaque phrase relue à la main contre la sortie DEV brute complète ; comptes cachés recomptés par script (go test, pytest, tar, ruff, apt, helm, unittest).

| # | Évaluation | Phrase dite en code | Verdict |
|---|---|---|---|
| 1 | `v3-network-0003@fr` | 6 ports en écoute : sshd sur 22, python3 sur 8081, 8082 et 8443, llama-server sur 8894 et 8961. | vraie |
| 2 | `v3-packages-system-0067@en` | 14 packages installed out of 17 listed, including libgtk-3-0t64, libgtk-3-bin and libgtk-3-common. | vraie |
| 3 | `v3-python-0009@en` | Success. 11 packages installed; project inventory 0.3.0 installed. | vraie |
| 4 | `v3-tests-0061@fr` | Échec. 3 tests échoués. Paquet shop, TestPrice qty_08, price_test.go ligne 51 : Price(8,3) = 24, want 25. | vraie |
| 5 | `v3-tests-0101@fr` | Échec. 5 tests échoués, 70 réussis. Premier : test_webhook_list_02, test_webhook.py ligne 10 : AssertionError. | vraie |
| 6 | `v3-vcs-git-0046@en` | 6 commits. Last: feature step 15: extend modules, 1 file changed: module_05.py. | vraie |
| 7 | `v3-rust-go-0018@en` | Failed. Deadlock: all goroutines are asleep. In main, main.go line 8. | vraie |
| 8 | `v3-files-0089@fr` | 1 somme de contrôle ne correspond pas : site_web/index.html. | vraie |
| 9 | `v3-tests-0126@fr` | Échec. 5 tests échoués, 77 réussis. Premier : test_upload_delete_06, test_upload.py ligne 22 : AssertionError. | vraie |
| 10 | `v3-js-node-0003@en` | 24 packages added, no vulnerabilities. Deprecated: react-beautiful-dnd. | vraie |
| 11 | `v3-lint-format-0002@en` | Failed. ESLint found no eslint.config file. | vraie |
| 12 | `v3-files-0045@fr` | 77 éléments archivés dans tree.tgz. | vraie |
| 13 | `v3-infra-0002@fr` | Application terminée : 4 ressources ajoutées. Sorties : app_port 27254, bucket_name staging-elegant-boar. | vraie |
| 14 | `v3-data-0017@fr` | Échec. Base shop_prod inexistante sur localhost. | vraie |
| 15 | `v3-lint-format-0001@fr` | Échec, 10 erreurs et 4 avertissements. basket.js ligne 1 : formatPrice is defined but never used. | vraie |
| 16 | `v3-shell-scripts-0064@en` | Failed. devis.sh line 10: relance.txt: not found. | vraie |
| 17 | `v3-rust-go-0008@en` | Failed. Panic at main.rs line 9: index out of bounds: the len is 3 but the index is 3. | vraie |
| 18 | `v3-lint-format-0027@fr` | Échec. Ruff : 151 erreurs dans tool/runner.py, 1 corrigeable automatiquement. | vraie |
| 19 | `v3-processes-0010@en` | app.log open by tail, PID 38981. | vraie |
| 20 | `v3-lint-format-0011@en` | Failed, 7 errors and 5 warnings. ci.yaml line 4: too many spaces inside brackets. | vraie |
| 21 | `v3-tests-0095@en` | Failed. 5 failed, 77 passed. First: test_rating_delete_16, test_rating.py line 52: ZeroDivisionError, division by zero. | vraie |
| 22 | `v3-network-transfer-0017@fr` | Échec. TLS, expired.badssl.com : certificat expiré. | vraie |
| 23 | `v3-network-transfer-0005@en` | Failed. Host mirror.nonexistent.invalid not found. | vraie |
| 24 | `v3-lint-format-0023@en` | Failed, 140 errors and 35 warnings. widget0.js line 1: w0_0 is defined but never used. | vraie |
| 25 | `v3-packages-system-0065@en` | 87 packages can be upgraded, including at-spi2-common, at-spi2-core and auditd. | vraie |
| 26 | `v3-containers-0024@fr` | Chart storefront rendu pour la release shop, 4 manifestes : ServiceAccount, Service, Deployment et Pod. | vraie |
| 27 | `v3-lint-format-0040@en` | Failed. Ruff: 65 errors in quota/core.py, 5 fixable automatically. | vraie |
| 28 | `v3-tests-0084@en` | Failed. 3 failed, 70 passed. First: test_rating_update_09, test_rating.py line 31: AssertionError. | vraie |
| 29 | `v3-network-0020@fr` | 4 connexions : homenet sur wlp2s0, docker0 sur docker0, lo sur lo et Wired connection 1 inactive. | vraie |
| 30 | `v3-network-transfer-0016@en` | Failed. HTTP 401 Unauthorized on admin. | vraie |
| 31 | `v3-tests-0008@en` | Failed. 1 failed, 3 passed. First: test_refill_after_wait, test_bucket.py line 14: timed out after 2 s. | vraie |
| 32 | `v3-shell-scripts-0057@fr` | Échec. abonnements.sh ligne 11 : variable MONTANT_TOTAL non définie. Dernier message : Bilan : 72 lignes traitées, total 3453. | vraie |
| 33 | `v3-lint-format-0001@en` | Failed, 10 errors and 4 warnings. basket.js line 1: formatPrice is defined but never used. | vraie |
| 34 | `v3-rust-go-0013@en` | Success. Build of logscan finished, no warnings, 15 packages locked. | vraie |
| 35 | `v3-tests-0042@en` | 2 packages passed: codec and store. No tests: kvctl and version. | vraie |
| 36 | `v3-disk-memory-0035@fr` | Mémoire totale 31,0 Go, libre 1,8 Go. | vraie ; convention de free : Kio convertis et dits « Go » |
| 37 | `v3-shell-scripts-0057@en` | Failed. abonnements.sh line 11: unbound variable MONTANT_TOTAL. | vraie |
| 38 | `v3-rust-go-0013@fr` | Succès. Compilation de logscan terminée, sans avertissement, 15 paquets verrouillés. | vraie |
| 39 | `v3-tests-0115@en` | Failed. 3 failures out of 67 tests, including test_catalog_00, test_catalog.py line 5. | vraie |
| 40 | `v3-tests-0016@en` | Failed. 2 failures and 1 error out of 9 tests, including test_port_default, loader.py line 19: KeyError, port. | vraie |

**Fausses : 0 sur 40.**
