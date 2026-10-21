# Publier une version de steph

Ce document liste les commandes de publication. **Rien n'est publié automatiquement** :
chaque commande ci-dessous se lance à la main, par le mainteneur.

## État

| Canal | Préparé | Publié | Reste à faire |
|---|---|---|---|
| PyPI | `pyproject.toml` complet, `uv build` vérifié | non | jeton PyPI, nom `steph` à réserver |
| Homebrew | `packaging/homebrew/steph.rb` | non | sha256, blocs `resource`, dépôt du tap |
| Clone git | `curl -fsSL https://steph.lsmdx.com/install \| sh` | oui | rien |

## Limite connue avant publication

Installé depuis PyPI ou Homebrew, steph ne télécharge ni le modèle ni la voix :
`scripts/install.sh` ne fait pas partie du paquet. La formule Homebrew l'explique dans
ses `caveats` ; pour PyPI, le README doit le dire. `steph update` hors clone se limite à
indiquer `uv tool upgrade steph` ou `brew upgrade steph`, et à mettre à jour llama.cpp
quand Homebrew le gère.

## 1. Préparer la version

```sh
# numéro de version dans pyproject.toml ([project] version), puis :
uv run pytest -q tests
rm -rf dist && uv build
```

Contrôler le contenu du wheel : les dossiers `steph/shell/` et `steph/profiles/`
doivent y figurer.

```sh
unzip -l dist/steph-*.whl | grep -E 'shell/|profiles/'
```

Essai dans un venv jetable :

```sh
uv venv /tmp/steph-essai && VIRTUAL_ENV=/tmp/steph-essai uv pip install dist/steph-*.whl
/tmp/steph-essai/bin/steph --help && /tmp/steph-essai/bin/steph profile
rm -rf /tmp/steph-essai
```

## 2. PyPI

Le README contient des liens relatifs (`assets/banner.png`, `LICENSE.md`) : sur PyPI ils
ne s'affichent pas. Les passer en URL absolues GitHub avant la première publication.

```sh
# d'abord sur TestPyPI
uv publish --publish-url https://test.pypi.org/legacy/ --token "$TEST_PYPI_TOKEN"
uv tool install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ steph

# puis pour de vrai
uv publish --token "$PYPI_TOKEN"
```

## 3. Homebrew (tap personnel)

```sh
# une seule fois : créer le dépôt GitHub tutozz/homebrew-steph
brew tap-new tutozz/steph
cp packaging/homebrew/steph.rb "$(brew --repository tutozz/steph)/Formula/steph.rb"

# à chaque version, une fois le sdist publié sur PyPI
shasum -a 256 dist/steph-X.Y.Z.tar.gz          # à reporter dans sha256
brew update-python-resources tutozz/steph/steph # ajoute les blocs resource
brew audit --strict tutozz/steph/steph
brew install --build-from-source tutozz/steph/steph && brew test tutozz/steph/steph

cd "$(brew --repository tutozz/steph)" && git push
```

Installation côté utilisateur :

```sh
brew install tutozz/steph/steph
```

## 4. Git

```sh
git tag vX.Y.Z && git push origin master vX.Y.Z
```
