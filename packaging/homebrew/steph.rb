# Formule Homebrew de steph, pour un tap personnel (tutozz/homebrew-steph).
# PRÉPARÉE, NON PUBLIÉE : voir docs/release.md avant toute utilisation.
class Steph < Formula
  include Language::Python::Virtualenv

  desc "Talking terminal for visually impaired people (local LLM + Piper voice)"
  homepage "https://steph.lsmdx.com"
  url "https://files.pythonhosted.org/packages/source/s/steph/steph-0.1.0.tar.gz"
  # À REMPLACER : `shasum -a 256 dist/steph-0.1.0.tar.gz` après `uv build`
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  # PolyForm Noncommercial 1.0.0 n'a pas d'identifiant SPDX
  license :cannot_represent

  depends_on "llama.cpp"
  depends_on "python@3.13"
  depends_on "sox"

  # À GÉNÉRER : `brew update-python-resources packaging/homebrew/steph.rb`
  # ajoute ici un bloc `resource` par dépendance Python (piper-tts, onnxruntime…).

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      steph a besoin d'un modèle (3,2 Go) et d'une voix (61 Mo), téléchargés à part :
        mkdir -p ~/.local/share/steph/models ~/.local/share/steph/voices
        curl -fL -o ~/.local/share/steph/models/gemma-4-E2B_q4_0-it.gguf \\
          https://huggingface.co/google/gemma-4-E2B-it-qat-q4_0-gguf/resolve/main/gemma-4-E2B_q4_0-it.gguf
        #{opt_libexec}/bin/python -m piper.download_voices \\
          --download-dir ~/.local/share/steph/voices fr_FR-siwis-medium
      Puis : steph setup
    EOS
  end

  test do
    assert_match "Terminal parlant", shell_output("#{bin}/steph --help")
  end
end
